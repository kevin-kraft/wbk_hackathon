"""CAD-free planar ('2d') pose from a segmentation mask + camera intrinsics.

The 2D mode is a fast, template-free fallback for the 6DoF estimators: it does
NOT need GigaPose/FoundationPose templates or the model at all — just the mask,
K, and (optionally) depth. It back-projects the mask centroid to a 3D point and
builds a top-down grasp orientation whose in-plane yaw follows the mask's
principal axis. Inspired by the KIP seminar's `detect_and_move` (centroid +
depth -> world point, top-down), enriched with the in-plane orientation.

Output is the SAME contract as the 6DoF estimators: T_cam_obj, a 4x4 row-major
object->camera transform in the OpenCV camera frame (x right, y down, +z
forward), in metres — so 2D mode is a drop-in for the orchestrator/frontend.

Orientation convention: R = Rz(theta) @ Rx(pi), which gives
  object +x -> image principal axis (aligns the gripper with the part's long axis)
  object +z -> back toward the camera (top-down approach)
Downstream `obj_T_grasp` (hand-eye chain) still refines the actual grip.
"""

from __future__ import annotations

import numpy as np

# Rx(pi): flips object +z to point back toward the camera (top-down approach).
_TOP_DOWN = np.diag([1.0, -1.0, -1.0])


def _rz(theta: float) -> np.ndarray:
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def _principal_axis_angle(xs: np.ndarray, ys: np.ndarray) -> float:
    """In-plane angle (rad) of the mask's major axis, image coords (x right, y down).

    PCA on the mask pixel coordinates; returns atan2(major_y, major_x).
    """
    if xs.size < 2:
        return 0.0
    pts = np.stack([xs.astype(np.float64), ys.astype(np.float64)])  # 2xN
    pts -= pts.mean(axis=1, keepdims=True)
    cov = pts @ pts.T
    evals, evecs = np.linalg.eigh(cov)  # ascending eigenvalues
    major = evecs[:, int(np.argmax(evals))]  # (vx, vy)
    return float(np.arctan2(major[1], major[0]))


def planar_pose(
    K: np.ndarray,
    mask: np.ndarray,
    depth: np.ndarray | None,
    plane_z: float | None = None,
    default_z: float = 0.5,
) -> tuple[np.ndarray, float, str]:
    """Mask -> (T_cam_obj 4x4, score, stage).

    depth is HxW metres (or None). z for the centroid is the median valid depth
    over the mask; if depth is absent/invalid, `plane_z` (camera-frame table
    depth, metres) is used, else `default_z`. `stage` records which was used.
    `score` is the mask's fill ratio of its bounding box (a rough quality proxy).
    """
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        raise ValueError("planar_pose: empty mask")

    u = float(xs.mean())
    v = float(ys.mean())

    stage = "2d"
    z: float | None = None
    if depth is not None:
        d = depth[ys, xs]
        d = d[np.isfinite(d) & (d > 0.0)]
        if d.size:
            z = float(np.median(d))
    if z is None:
        if plane_z is not None:
            z, stage = float(plane_z), "2d-plane"
        else:
            z, stage = float(default_z), "2d-defaultz"

    fx, fy = float(K[0, 0]), float(K[1, 1])
    cx, cy = float(K[0, 2]), float(K[1, 2])
    t = np.array([(u - cx) / fx * z, (v - cy) / fy * z, z])

    theta = _principal_axis_angle(xs, ys)
    R = _rz(theta) @ _TOP_DOWN

    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = t

    bw = int(xs.max() - xs.min()) + 1
    bh = int(ys.max() - ys.min()) + 1
    score = float(xs.size) / float(bw * bh)
    return T, score, stage
