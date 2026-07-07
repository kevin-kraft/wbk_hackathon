"""damage/reference.py — disk-backed per-class reference image loader."""

from __future__ import annotations

import base64

from damage.reference import load_reference


def test_load_reference_returns_empty_when_dir_missing(tmp_path):
    ok, damaged = load_reference(str(tmp_path / "does-not-exist"), "housing")
    assert ok == []
    assert damaged == []


def test_load_reference_returns_empty_when_part_class_is_none(tmp_path):
    ok, damaged = load_reference(str(tmp_path), None)
    assert ok == []
    assert damaged == []


def test_load_reference_picks_up_ok_and_damaged_files_by_extension(tmp_path):
    ok_dir = tmp_path / "housing" / "ok"
    damaged_dir = tmp_path / "housing" / "damaged"
    ok_dir.mkdir(parents=True)
    damaged_dir.mkdir(parents=True)

    (ok_dir / "a.png").write_bytes(b"okpng")
    (ok_dir / "b.jpg").write_bytes(b"okjpg")
    (ok_dir / "ignore.txt").write_text("not an image")
    (damaged_dir / "c.webp").write_bytes(b"damagedwebp")

    ok, damaged = load_reference(str(tmp_path), "housing")

    assert sorted(ok) == sorted(
        [base64.b64encode(b"okpng").decode(), base64.b64encode(b"okjpg").decode()]
    )
    assert damaged == [base64.b64encode(b"damagedwebp").decode()]


def test_load_reference_is_scoped_to_part_class(tmp_path):
    (tmp_path / "housing" / "ok").mkdir(parents=True)
    (tmp_path / "housing" / "ok" / "a.png").write_bytes(b"data")
    (tmp_path / "bracket" / "ok").mkdir(parents=True)

    ok, damaged = load_reference(str(tmp_path), "bracket")

    assert ok == []
    assert damaged == []
