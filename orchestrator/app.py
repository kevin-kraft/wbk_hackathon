"""Thin FastAPI wrapper around the orchestrator (:8000).

`POST /run` executes a full disassembly loop and returns the collected events +
summary. `GET /events/run` runs the same loop but **streams** each `LoopEvent`
live over Server-Sent Events (SSE) — this is what the frontend dashboard consumes
to narrate the loop in real time. `dry_run=true` uses mocks (no services/hardware)
— handy for a smoke test or the demo; a real run drives the live perception/pose/
damage services and the teammate-owned Jetson movement + grip-sensor endpoints.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .auth import require_token
from .config import OrchestratorConfig
from .factory import build_orchestrator
from .models import LoopEvent

app = FastAPI(title="orchestrator")


def _config_for(
    target: str | None,
    pose_pipeline: str | None = None,
    localization: str | None = None,
) -> OrchestratorConfig:
    """Base env config, with the robot target / pose pipeline / localization mode
    optionally overridden per-run so the dashboard can flip real/sim/both, 6DoF/2D,
    or pose/slots localization without restarting."""
    config = OrchestratorConfig()
    if target:
        config.robot_target = target.strip().lower()
    if pose_pipeline:
        config.pose_pipeline = pose_pipeline.strip().lower()
    if localization:
        config.localization_mode = localization.strip().lower()
    return config

# The dashboard is a separate static app that may be served from any host, so it
# hits this API cross-origin. Allow all origins (a demo/control-plane on a trusted
# LAN); tighten to the known frontend origin(s) if this is ever exposed wider.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _event_dict(event: LoopEvent) -> dict:
    return {"step": event.step, "state": event.state, "message": event.message, "data": event.data}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "orchestrator"}


@app.post("/run", dependencies=[Depends(require_token)])
def run(
    dry_run: bool = False,
    target: str | None = None,
    product: str | None = None,
    pose_pipeline: str | None = None,
    localization: str | None = None,
) -> dict:
    """Run a full loop and return all events + the final stats at once (no streaming).

    `target` (real|sim|both) picks which robot the loop drives, overriding
    ROBOT_TARGET for this run only. `product` switches to a plan-driven run:
    the PlanProvider generates an ordered disassembly plan for that product and
    the loop executes it step by step (see GET /products for the choices).
    `pose_pipeline` (rgbd|rgb|2d) overrides the pose stage for this run — '2d' is
    the CAD-free planar pose (GigaPose), useful when 6DoF templates are missing.
    """
    events: list[dict] = []
    config = _config_for(target, pose_pipeline, localization)
    orchestrator = build_orchestrator(config=config, dry_run=dry_run, on_event=lambda e: events.append(_event_dict(e)))
    stats = orchestrator.run(product=product)
    return {
        "stats": stats,
        "target": config.robot_target,
        "product": product,
        "pose_pipeline": config.pose_pipeline,
        "localization": config.localization_mode,
        "events": events,
    }


@app.get("/products", dependencies=[Depends(require_token)])
def products() -> dict:
    """Operator-selectable products from the (mock-)ERP dataset, for the dashboard."""
    from .clients.erp import load_products

    config = OrchestratorConfig()
    items = [
        {
            "id": pid,
            "name": entry.get("name", pid),
            "description": entry.get("description"),
            "parts": [p["part"] for p in entry.get("parts", [])],
        }
        for pid, entry in sorted(load_products(config.erp_products_path).items())
    ]
    return {"products": items}


@app.get("/plan", dependencies=[Depends(require_token)])
def plan_preview(product: str, dry_run: bool = False) -> dict:
    """Generate (but do not execute) the disassembly plan for a product — lets the
    operator review the LLM/ERP plan before starting a run."""
    from fastapi import HTTPException

    config = OrchestratorConfig()
    if dry_run:
        from .mocks import MockPlanProvider

        provider = MockPlanProvider()
    else:
        from .factory import _build_plan_provider

        provider = _build_plan_provider(config)
    try:
        plan = provider.get_plan(product)
    except ValueError as exc:  # unknown product
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "product": plan.product,
        "source": plan.source,
        "rationale": plan.rationale,
        "steps": [
            {"index": s.index, "part": s.part, "action": s.action, "notes": s.notes}
            for s in plan.steps
        ],
    }


@app.get("/slots/layout", dependencies=[Depends(require_token)])
def slots_layout() -> dict:
    """The current tray slot layout (pixel centres + base poses) for calibration
    + visualization on the dashboard Slots page."""
    from .slots import load_slot_layout

    config = OrchestratorConfig()
    return load_slot_layout(config.slot_layout_path).to_dict()


@app.post("/slots/layout", dependencies=[Depends(require_token)])
def save_slots_layout(layout: dict) -> dict:
    """Persist an edited slot layout (dashboard calibration: re-placed pixels,
    measured base poses). Overwrites SLOT_LAYOUT_PATH."""
    from .slots import layout_from_dict, save_slot_layout

    config = OrchestratorConfig()
    parsed = layout_from_dict(layout)  # validates shape before writing
    save_slot_layout(config.slot_layout_path, parsed)
    return {"status": "saved", "slots": len(parsed.slots), "path": config.slot_layout_path}


@app.post("/slots/occupancy", dependencies=[Depends(require_token)])
def slots_occupancy(body: dict) -> dict:
    """Score every slot's occupancy for a given RGB frame — the introspection
    behind slot localization. Body: {image_b64, mask_source?}. Returns per-slot
    {filled, detected_class, fill_score, identity_ok, ...}."""
    from fastapi import HTTPException

    from .clients.http_perception import HttpPerception
    from .clients.slot_perception import SlotPerception
    from .models import SceneFrame

    image_b64 = body.get("image_b64")
    if not image_b64:
        raise HTTPException(status_code=422, detail="image_b64 is required")
    config = OrchestratorConfig()
    if body.get("mask_source"):
        config.slot_mask_source = str(body["mask_source"]).strip().lower()
    slot_perception = SlotPerception(config, HttpPerception(config))
    frame = SceneFrame(rgb_b64=image_b64)
    statuses = slot_perception.occupancy(frame)
    return {
        "mask_source": slot_perception.mask_source,
        "image_size": list(slot_perception.layout.image_size) if slot_perception.layout.image_size else None,
        "filled": sum(1 for s in statuses if s.filled),
        "slots": [s.to_dict() for s in statuses],
    }


def _sse(data: dict, event: str | None = None) -> str:
    """Format one Server-Sent Event frame."""
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {json.dumps(data)}\n\n"


@app.get("/events/run", dependencies=[Depends(require_token)])
async def events_run(
    dry_run: bool = False, delay: float = 0.0, target: str | None = None, product: str | None = None,
    pose_pipeline: str | None = None, localization: str | None = None,
) -> StreamingResponse:
    """Run a loop and stream each stage event as it happens (SSE).

    `delay` (seconds) paces emission so the live demo is watchable — mocks
    otherwise run to completion in milliseconds. `target` (real|sim|both) picks
    which robot the loop drives for this run. `product` switches to a
    plan-driven run (see POST /run). The loop runs in a worker thread (it is
    synchronous/blocking) and pushes events through a thread-safe queue that
    the async SSE generator drains.
    """
    q: queue.Queue = queue.Queue()
    sentinel = object()
    config = _config_for(target, pose_pipeline, localization)

    def on_event(event: LoopEvent) -> None:
        q.put(("event", _event_dict(event)))
        if delay:
            time.sleep(delay)  # pace the loop for the live demo (runs in the worker thread)

    def worker() -> None:
        try:
            orchestrator = build_orchestrator(config=config, dry_run=dry_run, on_event=on_event)
            stats = orchestrator.run(product=product)
            q.put(("summary", stats))
        except Exception as exc:  # surface failures to the UI instead of a silent hang
            q.put(("error", {"error": str(exc)}))
        finally:
            q.put(sentinel)

    threading.Thread(target=worker, name="orchestrator-run", daemon=True).start()

    async def stream():
        loop = asyncio.get_event_loop()
        yield _sse({"status": "started", "dry_run": dry_run, "target": config.robot_target,
                    "product": product}, event="start")
        while True:
            item = await loop.run_in_executor(None, q.get)
            if item is sentinel:
                break
            kind, payload = item
            yield _sse(payload, event=kind)
        yield _sse({"status": "done"}, event="end")

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
