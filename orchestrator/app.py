"""Thin FastAPI wrapper around the orchestrator (:8000).

`POST /run` executes a full disassembly loop and returns the collected events +
summary. `dry_run=true` uses mocks (no services/hardware) — handy for a smoke
test or the demo. A real run drives the live perception/pose/damage services and
the teammate-owned Jetson movement + grip-sensor endpoints.
"""

from __future__ import annotations

from fastapi import FastAPI

from .factory import build_orchestrator
from .models import LoopEvent

app = FastAPI(title="orchestrator")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "orchestrator"}


@app.post("/run")
def run(dry_run: bool = False) -> dict:
    events: list[dict] = []

    def collect(event: LoopEvent) -> None:
        events.append({"step": event.step, "state": event.state, "message": event.message, "data": event.data})

    orchestrator = build_orchestrator(dry_run=dry_run, on_event=collect)
    stats = orchestrator.run()
    return {"stats": stats, "events": events}
