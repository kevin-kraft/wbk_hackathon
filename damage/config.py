"""Environment-driven configuration for the damage-inspection service."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    api_key: str = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY", ""))
    base_url: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    )
    # OpenRouter model slug. Must match OpenRouter's catalog — override as needed.
    # Defaults to a capable, fast vision model for QC.
    model: str = field(default_factory=lambda: os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-5"))
    # Optional attribution headers OpenRouter recommends.
    referer: str = field(default_factory=lambda: os.getenv("OPENROUTER_REFERER", "https://github.com/kevin-kraft/wbk_hackathon"))
    app_title: str = field(default_factory=lambda: os.getenv("OPENROUTER_TITLE", "wbk-disassembly-damage"))
    # Per-class reference images: <reference_dir>/<class>/ok/*  and  /<class>/damaged/*
    reference_dir: str = field(default_factory=lambda: os.getenv("REFERENCE_DIR", "/reference"))
    request_timeout_s: float = field(default_factory=lambda: float(os.getenv("DAMAGE_TIMEOUT_S", "60")))
