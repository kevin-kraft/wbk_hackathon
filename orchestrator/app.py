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


def _config_for(target: str | None) -> OrchestratorConfig:
    """Base env config, with the robot target optionally overridden per-run so the
    dashboard can flip real/sim/both without restarting the service."""
    config = OrchestratorConfig()
    if target:
        config.robot_target = target.strip().lower()
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
def run(dry_run: bool = False, target: str | None = None) -> dict:
    """Run a full loop and return all events + the final stats at once (no streaming).

    `target` (real|sim|both) picks which robot the loop drives, overriding
    ROBOT_TARGET for this run only.
    """
    events: list[dict] = []
    config = _config_for(target)
    orchestrator = build_orchestrator(config=config, dry_run=dry_run, on_event=lambda e: events.append(_event_dict(e)))
    stats = orchestrator.run()
    return {"stats": stats, "target": config.robot_target, "events": events}


def _sse(data: dict, event: str | None = None) -> str:
    """Format one Server-Sent Event frame."""
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {json.dumps(data)}\n\n"


@app.get("/events/run", dependencies=[Depends(require_token)])
async def events_run(dry_run: bool = False, delay: float = 0.0, target: str | None = None) -> StreamingResponse:
    """Run a loop and stream each stage event as it happens (SSE).

    `delay` (seconds) paces emission so the live demo is watchable — mocks
    otherwise run to completion in milliseconds. `target` (real|sim|both) picks
    which robot the loop drives for this run. The loop runs in a worker thread
    (it is synchronous/blocking) and pushes events through a thread-safe queue
    that the async SSE generator drains.
    """
    q: queue.Queue = queue.Queue()
    sentinel = object()
    config = _config_for(target)

    def on_event(event: LoopEvent) -> None:
        q.put(("event", _event_dict(event)))
        if delay:
            time.sleep(delay)  # pace the loop for the live demo (runs in the worker thread)

    def worker() -> None:
        try:
            orchestrator = build_orchestrator(config=config, dry_run=dry_run, on_event=on_event)
            stats = orchestrator.run()
            q.put(("summary", stats))
        except Exception as exc:  # surface failures to the UI instead of a silent hang
            q.put(("error", {"error": str(exc)}))
        finally:
            q.put(sentinel)

    threading.Thread(target=worker, name="orchestrator-run", daemon=True).start()

    async def stream():
        loop = asyncio.get_event_loop()
        yield _sse({"status": "started", "dry_run": dry_run, "target": config.robot_target}, event="start")
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
