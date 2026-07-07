"""Damage-inspection service — FastAPI app on :8006.

The arm holds a just-disassembled part up to the inspection webcam; the webcam's
multi-angle shots are POSTed here. A VLM (via OpenRouter) compares them against
known-good / known-damaged references and returns a verdict. The `bin` field
tells the arm where to place the part: `ok_bin` or `reject_bin`.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .client import call_openrouter
from .config import Settings
from .prompts import build_messages
from .reference import load_reference
from .schemas import DamageHealth, DamageRequest, DamageVerdict

settings = Settings()
app = FastAPI(title="damage-inspection")


@app.get("/health", response_model=DamageHealth)
def health() -> DamageHealth:
    return DamageHealth(
        status="ok",
        service="damage",
        model=settings.model,
        api_key_present=bool(settings.api_key),
        reference_dir=settings.reference_dir,
    )


@app.post("/inspect", response_model=DamageVerdict)
def inspect(req: DamageRequest) -> DamageVerdict:
    # Merge inline references with any on disk for this class.
    disk_ok, disk_damaged = load_reference(settings.reference_dir, req.part_class)
    ref_ok = req.reference_ok_b64 + disk_ok
    ref_damaged = req.reference_damaged_b64 + disk_damaged

    messages = build_messages(req, ref_ok, ref_damaged)
    raw = call_openrouter(settings, messages)

    verdict = str(raw.get("verdict", "uncertain")).lower()
    if verdict not in {"ok", "damaged", "uncertain"}:
        verdict = "uncertain"
    damaged = verdict == "damaged"

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    return DamageVerdict(
        verdict=verdict,  # type: ignore[arg-type]
        damaged=damaged,
        confidence=max(0.0, min(1.0, confidence)),
        # Sorting policy: only a clean "ok" goes to the good bin; damaged AND
        # uncertain are rejected so a bad part never reaches the working bin.
        bin="ok_bin" if verdict == "ok" else "reject_bin",
        issues=[str(i) for i in raw.get("issues", []) if i],
        reasoning=str(raw.get("reasoning", "")),
        model=settings.model,
        part_class=req.part_class,
    )


@app.exception_handler(Exception)
async def on_error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"error": type(exc).__name__, "detail": str(exc)})
