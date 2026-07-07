"""damage/prompts.py — build_messages() ordering and shape."""

from __future__ import annotations

from damage.prompts import RESPONSE_INSTRUCTION, SYSTEM_PROMPT, _image_part, build_messages
from damage.schemas import DamageRequest


def _image_urls(content: list[dict]) -> list[str]:
    return [part["image_url"]["url"] for part in content if part["type"] == "image_url"]


def test_image_part_adds_data_uri_prefix_when_missing():
    part = _image_part("YWJj")
    assert part == {"type": "image_url", "image_url": {"url": "data:image/png;base64,YWJj"}}


def test_image_part_leaves_existing_data_uri_untouched():
    uri = "data:image/jpeg;base64,YWJj"
    part = _image_part(uri)
    assert part["image_url"]["url"] == uri


def test_build_messages_has_system_message_first():
    req = DamageRequest(images_b64=["target1"])
    messages = build_messages(req, ref_ok=[], ref_damaged=[])

    assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert messages[1]["role"] == "user"


def test_build_messages_references_appear_before_target_images():
    req = DamageRequest(images_b64=["target1", "target2"])
    messages = build_messages(req, ref_ok=["ok1"], ref_damaged=["bad1"])

    content = messages[1]["content"]
    urls = _image_urls(content)

    # ok1, bad1 (references) must precede target1, target2 in the flattened list.
    assert urls.index("data:image/png;base64,ok1") < urls.index("data:image/png;base64,target1")
    assert urls.index("data:image/png;base64,bad1") < urls.index("data:image/png;base64,target1")
    assert urls.index("data:image/png;base64,target1") < urls.index("data:image/png;base64,target2")


def test_build_messages_correct_number_of_image_parts():
    req = DamageRequest(images_b64=["t1", "t2", "t3"])
    messages = build_messages(req, ref_ok=["ok1", "ok2"], ref_damaged=["bad1"])

    content = messages[1]["content"]
    image_parts = [p for p in content if p["type"] == "image_url"]

    assert len(image_parts) == 3 + 2 + 1  # targets + ok refs + damaged refs


def test_build_messages_no_references_omits_reference_headers():
    req = DamageRequest(images_b64=["t1"])
    messages = build_messages(req, ref_ok=[], ref_damaged=[])

    content = messages[1]["content"]
    text_parts = [p["text"] for p in content if p["type"] == "text"]

    assert not any("KNOWN-GOOD" in t for t in text_parts)
    assert not any("KNOWN-DAMAGED" in t for t in text_parts)


def test_build_messages_appends_response_instruction_last():
    req = DamageRequest(images_b64=["t1"])
    messages = build_messages(req, ref_ok=[], ref_damaged=[])

    content = messages[1]["content"]
    assert content[-1] == {"type": "text", "text": RESPONSE_INSTRUCTION}


def test_build_messages_includes_notes_when_present():
    req = DamageRequest(images_b64=["t1"], notes="check the flange")
    messages = build_messages(req, ref_ok=[], ref_damaged=[])

    content = messages[1]["content"]
    text_parts = [p["text"] for p in content if p["type"] == "text"]
    assert any("check the flange" in t for t in text_parts)


def test_build_messages_includes_part_class_in_header():
    req = DamageRequest(images_b64=["t1"], part_class="housing")
    messages = build_messages(req, ref_ok=[], ref_damaged=[])

    content = messages[1]["content"]
    header = content[0]["text"] if content[0]["type"] == "text" else None
    assert header is not None
    assert "housing" in header
