"""Builds a FastAPI app with the boilerplate every service shares:
a startup lifespan that loads the model once, a /health probe, a root info
route, and uniform error handling. Each service adds its own typed /infer route.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .model_base import BasePerceptionModel
from .schemas import HealthResponse


def create_service_app(*, service_name: str, model: BasePerceptionModel) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        model.load()  # download + load weights onto the GPU, once
        yield
        model.unload()

    app = FastAPI(title=f"perception-{service_name}", lifespan=lifespan)

    # Allow the dashboard (served from another origin) to poll /health and call
    # /infer from the browser. Token auth still gates the routes.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok" if model.loaded else "loading",
            service=service_name,
            model=model.name,
            device=model.device,
            loaded=model.loaded,
        )

    @app.get("/")
    def root() -> dict:
        return {
            "service": service_name,
            "model": model.name,
            "endpoints": ["/health", "/infer", "/docs"],
        }

    @app.exception_handler(Exception)
    async def on_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": type(exc).__name__, "detail": str(exc)},
        )

    return app
