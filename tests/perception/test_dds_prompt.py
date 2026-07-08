"""Unit tests for the DDS adapter's prompt-building and capability guards.

These exercise pure request->api_body logic only — no network, no cloud SDK.
The SDK is imported lazily inside `infer()`/`_build_visual_images()` (after the
cheap validation covered here), so these tests run without `dds-cloudapi-sdk`
installed.
"""

from __future__ import annotations

import pytest

from services.dds.model import _ENDPOINTS, DdsBackend
from services.shared.config import Settings
from services.shared.schemas import BBox, DdsRequest, VisualPrompt


def _backend() -> DdsBackend:
    return DdsBackend(Settings())


def _req(**kw) -> DdsRequest:
    kw.setdefault("image_b64", "abc")
    return DdsRequest(**kw)


def test_text_prompt_shape_for_dino_family():
    b = _backend()
    p = b._build_prompt(_req(text="gear . screw"), "GroundingDino-1.6-Pro")
    assert p == {"type": "text", "text": "gear . screw"}


def test_text_prompt_rejected_for_trex():
    b = _backend()
    with pytest.raises(ValueError, match="does not accept text"):
        b._build_prompt(_req(text="gear"), "T-Rex-2.0")


def test_prompt_free_is_dinox_only():
    b = _backend()
    assert b._build_prompt(_req(prompt_free=True), "DINO-X-1.0") == {"type": "universal"}
    with pytest.raises(ValueError, match="universal"):
        b._build_prompt(_req(prompt_free=True), "GroundingDino-1.6-Pro")


def test_visual_prompt_rejected_for_text_only_models():
    b = _backend()
    vp = VisualPrompt(rect=BBox(x1=1, y1=1, x2=2, y2=2))
    with pytest.raises(ValueError, match="visual prompts"):
        b._build_prompt(_req(visual_prompts=[vp]), "GroundingDino-1.6-Pro")


def test_empty_request_raises():
    b = _backend()
    with pytest.raises(ValueError, match="needs one of"):
        b._build_prompt(_req(), "DINO-X-1.0")


def test_infer_without_token_raises_runtime_error():
    b = _backend()  # no DDS_API_TOKEN in Settings default -> not loaded
    b.load()
    assert b.loaded is False
    with pytest.raises(RuntimeError, match="DDS_API_TOKEN"):
        b.infer(_req(text="gear"))


def test_all_models_have_endpoints():
    # Every model the guards reference must map to a real V2 endpoint.
    assert set(_ENDPOINTS) == {
        "DINO-X-1.0",
        "DINO-XSeek-1.0",
        "GroundingDino-1.6-Pro",
        "T-Rex-2.0",
    }
