"""Slot-based 2D localization — the depth-free alternative to the pose stage.

The new arm + camera setup has no 3D. Instead of estimating a 6DoF pose and
back-projecting a grasp point (see clients/naive_grasp.py), we exploit a fixed
tray whose slots have **known, pre-measured base-frame coordinates**:

    SAM3 masks --(which slot centre does a mask cover?)--> filled slots
    filled slot --(lookup)--> the slot's measured base pose --> grasp

The camera is static (eye-to-hand), so each slot projects to a fixed pixel. A
slot is "filled" when its centre pixel (a small disk around it) is covered by an
object mask; the object's identity is fixed by the slot (`expected_class`), and
its real-world coordinate is the slot's stored base pose — the mask is used ONLY
for occupancy, never to compute the coordinate. No intrinsics, no depth.

The layout (pixel centres + base poses) is calibrated once against a real frame
and stored as JSON (see data/slot_layout.json); the dashboard's Slots page edits
it interactively. This module owns the schema, the loader, and the occupancy
engine; numpy is imported lazily so the pure-python loader/pose math runs (and is
tested) with no heavy deps.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field


def pose4x4_from_xyz_yaw(xyz: list[float], yaw_deg: float) -> list[list[float]]:
    """A top-down grasp pose in the base frame from a slot's (x,y,z) + yaw.

    Orientation matches the pose stage's planar convention (pose/shared/planar.py):
    R = Rz(yaw) @ Rx(pi), i.e. the tool z-axis points straight down (-base z) and
    yaw rotates about the base z-axis. Pure python (no numpy) so the loader stays
    dependency-free.
    """
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    # Rz(yaw) @ Rx(pi): columns are tool x=(c,s,0), y=(s,-c,0), z=(0,0,-1).
    x, y, z = (list(xyz) + [0.0, 0.0, 0.0])[:3]
    return [
        [c, s, 0.0, x],
        [s, -c, 0.0, y],
        [0.0, 0.0, -1.0, z],
        [0.0, 0.0, 0.0, 1.0],
    ]


@dataclass
class SlotSpec:
    """One tray slot: where it is in the image, what part it holds, and where
    that part is in the robot base frame."""

    id: str
    expected_class: str
    pixel: tuple[float, float]  # (u, v) centre in the calibration image
    base_xyz_m: tuple[float, float, float]  # grasp point, base frame, metres
    yaw_deg: float = 0.0
    radius_px: int | None = None  # occupancy disk radius; None -> layout default

    @property
    def base_pose(self) -> list[list[float]]:
        """4x4 top-down grasp pose in the base frame (T_base_grasp)."""
        return pose4x4_from_xyz_yaw(list(self.base_xyz_m), self.yaw_deg)


@dataclass
class SlotLayout:
    slots: list[SlotSpec] = field(default_factory=list)
    image_size: tuple[int, int] | None = None  # (width, height) the pixels were calibrated at
    radius_px: int = 22  # default occupancy disk radius (px, at calibration size)
    fill_frac: float = 0.35  # disk coverage fraction to call a slot filled
    mask_source: str = "sam3"  # "sam3" | "yoloseg"
    name: str = "default"

    def slot(self, slot_id: str) -> SlotSpec | None:
        return next((s for s in self.slots if s.id == slot_id), None)

    @property
    def classes(self) -> list[str]:
        """Distinct expected classes, in first-seen order (one SAM3 prompt each)."""
        seen: list[str] = []
        for s in self.slots:
            if s.expected_class not in seen:
                seen.append(s.expected_class)
        return seen

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "image_size": list(self.image_size) if self.image_size else None,
            "mask_source": self.mask_source,
            "defaults": {"radius_px": self.radius_px, "fill_frac": self.fill_frac},
            "slots": [
                {
                    "id": s.id,
                    "expected_class": s.expected_class,
                    "pixel": [s.pixel[0], s.pixel[1]],
                    "base_xyz_m": list(s.base_xyz_m),
                    "yaw_deg": s.yaw_deg,
                    **({"radius_px": s.radius_px} if s.radius_px is not None else {}),
                }
                for s in self.slots
            ],
        }


def layout_from_dict(data: dict) -> SlotLayout:
    defaults = data.get("defaults", {})
    size = data.get("image_size")
    slots = [
        SlotSpec(
            id=str(s["id"]),
            expected_class=str(s["expected_class"]),
            pixel=(float(s["pixel"][0]), float(s["pixel"][1])),
            base_xyz_m=tuple(float(v) for v in (list(s.get("base_xyz_m", [0, 0, 0])) + [0, 0, 0])[:3]),
            yaw_deg=float(s.get("yaw_deg", 0.0)),
            radius_px=(int(s["radius_px"]) if s.get("radius_px") is not None else None),
        )
        for s in data.get("slots", [])
    ]
    return SlotLayout(
        slots=slots,
        image_size=(int(size[0]), int(size[1])) if size else None,
        radius_px=int(defaults.get("radius_px", 22)),
        fill_frac=float(defaults.get("fill_frac", 0.35)),
        mask_source=str(data.get("mask_source", "sam3")).lower(),
        name=str(data.get("name", "default")),
    )


def load_slot_layout(path: str) -> SlotLayout:
    with open(path) as f:
        return layout_from_dict(json.load(f))


def save_slot_layout(path: str, layout: SlotLayout) -> None:
    with open(path, "w") as f:
        json.dump(layout.to_dict(), f, indent=2)
        f.write("\n")


# --------------------------------------------------------------------------- #
# Occupancy engine (numpy — lazy import so the loader/pose math stay dep-free)
# --------------------------------------------------------------------------- #


@dataclass
class SlotStatus:
    slot_id: str
    expected_class: str
    filled: bool
    detected_class: str | None  # class whose mask covered the centre (== expected when identity holds)
    fill_score: float  # best disk-coverage fraction across classes [0..1]
    pixel: tuple[float, float]  # centre, in the ACTUAL image (scaled from calibration)
    identity_ok: bool  # filled AND detected_class == expected_class
    base_pose: list[list[float]]  # T_base_grasp (4x4) for the slot

    def to_dict(self) -> dict:
        return {
            "slot_id": self.slot_id,
            "expected_class": self.expected_class,
            "filled": self.filled,
            "detected_class": self.detected_class,
            "fill_score": round(self.fill_score, 4),
            "pixel": [self.pixel[0], self.pixel[1]],
            "identity_ok": self.identity_ok,
            "base_pose": self.base_pose,
        }


def decode_mask(mask_b64: str):
    """Decode a base64 mask PNG (the 0/255 single-channel format every service
    emits, imaging.encode_mask_png_b64) into a boolean HxW numpy array."""
    import base64

    import numpy as np

    raw = mask_b64.split(",", 1)[-1]  # tolerate a data-URI prefix
    buf = np.frombuffer(base64.b64decode(raw), dtype=np.uint8)
    try:
        import cv2

        img = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError("cv2 could not decode mask PNG")
    except Exception:
        import io

        from PIL import Image

        img = np.array(Image.open(io.BytesIO(base64.b64decode(raw))).convert("L"))
    return img > 127


def compute_occupancy(
    masks: list[tuple[str, "object"]],
    layout: SlotLayout,
) -> list[SlotStatus]:
    """Decide, for each slot, whether it is filled and by what.

    `masks` is a list of (class_name, boolean HxW array). Slot pixels calibrated
    at `layout.image_size` are scaled to the actual mask resolution, so a capture
    at a different size than the calibration frame still lines up.
    """
    import numpy as np

    statuses: list[SlotStatus] = []
    # Infer the actual image size from the masks (all services emit full-res masks).
    actual_hw = next((m.shape for _, m in masks), None)
    if actual_hw is not None:
        act_h, act_w = actual_hw
    elif layout.image_size:
        act_w, act_h = layout.image_size
    else:
        act_h = act_w = 0
    if layout.image_size and act_w and act_h:
        sx = act_w / layout.image_size[0]
        sy = act_h / layout.image_size[1]
    else:
        sx = sy = 1.0

    for slot in layout.slots:
        u, v = slot.pixel[0] * sx, slot.pixel[1] * sy
        r = int(round((slot.radius_px or layout.radius_px) * (sx + sy) / 2))
        r = max(r, 1)
        best_class: str | None = None
        best_score = 0.0
        disk_total = 0
        if act_h and act_w:
            u0, u1 = max(0, int(u - r)), min(act_w, int(u + r) + 1)
            v0, v1 = max(0, int(v - r)), min(act_h, int(v + r) + 1)
            if u1 > u0 and v1 > v0:
                yy, xx = np.mgrid[v0:v1, u0:u1]
                disk = (xx - u) ** 2 + (yy - v) ** 2 <= r * r
                disk_total = int(disk.sum())
                for cls, m in masks:
                    if m is None or m.shape[0] < v1 or m.shape[1] < u1:
                        continue
                    covered = int((m[v0:v1, u0:u1] & disk).sum())
                    score = covered / disk_total if disk_total else 0.0
                    if score > best_score:
                        best_score, best_class = score, cls
        filled = disk_total > 0 and best_score >= layout.fill_frac
        detected = best_class if filled else None
        statuses.append(
            SlotStatus(
                slot_id=slot.id,
                expected_class=slot.expected_class,
                filled=filled,
                detected_class=detected,
                fill_score=best_score,
                pixel=(u, v),
                identity_ok=bool(filled and detected == slot.expected_class),
                base_pose=slot.base_pose,
            )
        )
    return statuses
