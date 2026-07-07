"""Load per-class reference images from disk.

Layout:  <reference_dir>/<part_class>/ok/*.{jpg,png}
         <reference_dir>/<part_class>/damaged/*.{jpg,png}

Optional — if the directory is absent, returns empty lists and the request must
carry its own inline references (or run reference-free).
"""

from __future__ import annotations

import base64
from pathlib import Path

_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def _load_dir_b64(path: Path) -> list[str]:
    if not path.is_dir():
        return []
    out: list[str] = []
    for f in sorted(path.iterdir()):
        if f.suffix.lower() in _EXTS and f.is_file():
            out.append(base64.b64encode(f.read_bytes()).decode())
    return out


def load_reference(reference_dir: str, part_class: str | None) -> tuple[list[str], list[str]]:
    """Return (ok_b64, damaged_b64) for the class, or ([], []) if unavailable."""
    if not part_class:
        return [], []
    base = Path(reference_dir) / part_class
    return _load_dir_b64(base / "ok"), _load_dir_b64(base / "damaged")
