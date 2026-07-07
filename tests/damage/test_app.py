"""damage/app.py — FastAPI routes, with call_openrouter monkeypatched.

No network / OpenRouter API key is needed: `damage.app.call_openrouter` is
patched per-test to return a canned verdict dict, so we exercise only the
service's own bin-sorting policy and response shaping.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from damage import app as damage_app_module

client = TestClient(damage_app_module.app)


def _request(**overrides):
    body = {"images_b64": ["abc"]}
    body.update(overrides)
    return body


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "damage"
    assert body["status"] == "ok"
    assert "reference_dir" in body
    assert "api_key_present" in body


def test_inspect_ok_verdict_goes_to_ok_bin(monkeypatch):
    monkeypatch.setattr(
        damage_app_module,
        "call_openrouter",
        lambda settings, messages: {"verdict": "ok", "confidence": 0.95, "issues": [], "reasoning": "clean"},
    )

    resp = client.post("/inspect", json=_request())
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "ok"
    assert body["damaged"] is False
    assert body["bin"] == "ok_bin"
    assert body["confidence"] == 0.95


def test_inspect_damaged_verdict_goes_to_reject_bin(monkeypatch):
    monkeypatch.setattr(
        damage_app_module,
        "call_openrouter",
        lambda settings, messages: {
            "verdict": "damaged",
            "confidence": 0.8,
            "issues": ["crack"],
            "reasoning": "visible crack",
        },
    )

    resp = client.post("/inspect", json=_request())
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "damaged"
    assert body["damaged"] is True
    assert body["bin"] == "reject_bin"
    assert body["issues"] == ["crack"]


def test_inspect_uncertain_verdict_goes_to_reject_bin(monkeypatch):
    monkeypatch.setattr(
        damage_app_module,
        "call_openrouter",
        lambda settings, messages: {"verdict": "uncertain", "confidence": 0.5, "reasoning": "hard to tell"},
    )

    resp = client.post("/inspect", json=_request())
    body = resp.json()
    assert body["verdict"] == "uncertain"
    assert body["damaged"] is False
    assert body["bin"] == "reject_bin"


def test_inspect_confidence_is_clamped_above_one(monkeypatch):
    monkeypatch.setattr(
        damage_app_module,
        "call_openrouter",
        lambda settings, messages: {"verdict": "ok", "confidence": 5.0, "reasoning": "x"},
    )

    resp = client.post("/inspect", json=_request())
    assert resp.json()["confidence"] == 1.0


def test_inspect_confidence_is_clamped_below_zero(monkeypatch):
    monkeypatch.setattr(
        damage_app_module,
        "call_openrouter",
        lambda settings, messages: {"verdict": "ok", "confidence": -3.0, "reasoning": "x"},
    )

    resp = client.post("/inspect", json=_request())
    assert resp.json()["confidence"] == 0.0


def test_inspect_missing_confidence_defaults_to_zero(monkeypatch):
    monkeypatch.setattr(
        damage_app_module,
        "call_openrouter",
        lambda settings, messages: {"verdict": "ok", "reasoning": "x"},
    )

    resp = client.post("/inspect", json=_request())
    assert resp.json()["confidence"] == 0.0


def test_inspect_bad_verdict_string_becomes_uncertain_and_rejected(monkeypatch):
    monkeypatch.setattr(
        damage_app_module,
        "call_openrouter",
        lambda settings, messages: {"verdict": "definitely-fine", "confidence": 0.9, "reasoning": "x"},
    )

    resp = client.post("/inspect", json=_request())
    body = resp.json()
    assert body["verdict"] == "uncertain"
    assert body["damaged"] is False
    assert body["bin"] == "reject_bin"


def test_inspect_missing_verdict_defaults_to_uncertain_and_rejected(monkeypatch):
    monkeypatch.setattr(
        damage_app_module,
        "call_openrouter",
        lambda settings, messages: {"confidence": 0.9, "reasoning": "x"},
    )

    resp = client.post("/inspect", json=_request())
    body = resp.json()
    assert body["verdict"] == "uncertain"
    assert body["bin"] == "reject_bin"


def test_inspect_merges_inline_and_disk_references(monkeypatch, tmp_path):
    ok_dir = tmp_path / "housing" / "ok"
    ok_dir.mkdir(parents=True)
    (ok_dir / "ref.png").write_bytes(b"diskref")

    monkeypatch.setattr(damage_app_module.settings, "reference_dir", str(tmp_path))

    captured = {}

    def fake_call_openrouter(settings, messages):
        captured["messages"] = messages
        return {"verdict": "ok", "confidence": 0.9, "reasoning": "x"}

    monkeypatch.setattr(damage_app_module, "call_openrouter", fake_call_openrouter)

    resp = client.post(
        "/inspect",
        json=_request(part_class="housing", reference_ok_b64=["inline_ok"]),
    )
    assert resp.status_code == 200

    content = captured["messages"][1]["content"]
    urls = [p["image_url"]["url"] for p in content if p["type"] == "image_url"]
    assert any("inline_ok" in u for u in urls)
    import base64

    disk_b64 = base64.b64encode(b"diskref").decode()
    assert any(disk_b64 in u for u in urls)
