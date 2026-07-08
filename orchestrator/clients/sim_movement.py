"""Adapter — drive the KIT Isaac Sim backend behind the MovementClient Protocol.

The simulator (Group 2's `ki_robotik_cv_seminar/simulation_backend`, port 8100)
does NOT speak our clean movement contract. It is an async **command bus**:

    POST /simulation/actions/execute {type, params}   -> {id, status:"queued"}
    (an Isaac worker polls the queue, runs the action, reports back)
    GET  /simulation/debug/commands/{id}              -> {status, error, result}

This adapter hides that so `robot_target=sim|both` drives the sim like any other
arm — it submits the matching sim action and blocks by polling the command to a
terminal status. See contracts/simulation_api.md for the full surface.

Mapping (orchestrator primitive -> sim action):
  move_to_pose(4x4)      -> move_tcp {position:[x,y,z], orientation_quat:[w,x,y,z]}
  set_gripper(closed)    -> close_gripper / open_gripper   (sim has no width/force)
  move_named(name)       -> a configured entry from the named-pose table
                            (the sim has no named poses; see NAMED_POSES below).

Assumptions (documented, override-able): the orchestrator plans in the robot BASE
frame and the sim's IK target is in robot-root coordinates — taken to be the same
frame. Positions are metres. Quaternions are [w, x, y, z] (the sim's convention).
"""

from __future__ import annotations

import json
import math
import os
import time

import httpx

from ..config import OrchestratorConfig

# --------------------------------------------------------------------------- #
# Named-pose table
#
# The sim has NO named poses, so each of the orchestrator's named waypoints must
# map to a concrete sim action. Entries are {"type": <sim action>, "params": {}}.
# Two shapes are supported per entry:
#   joint-space: {"type": "move_joint", "params": {"joints": [j1..j6, gL, gR]}}
#   cartesian:   {"type": "move_tcp",   "params": {"position": [...],
#                                                   "orientation_quat": [w,x,y,z]}}
# Override the whole table via env SIM_NAMED_POSES (inline JSON) or
# SIM_NAMED_POSES_FILE (path to a JSON file) — no code change to re-teach.
#
# Representation: CARTESIAN (move_tcp) — chosen with the operator. Each waypoint is
# a TCP pose (position [x,y,z] metres, base frame; orientation_quat [w,x,y,z]).
#
# The built-in defaults are PLACEHOLDERS (a rough top-down workspace layout) so a
# sim run won't crash on an unmapped name — they are NOT measured teach points and
# must be replaced with real poses (fill deploy/sim_named_poses.example.json and
# point SIM_NAMED_POSES_FILE at it, or set SIM_NAMED_POSES inline). Per-entry the
# adapter also accepts {"type":"move_joint","params":{"joints":[j1..j6,gL,gR]}} if
# a given waypoint is easier to store in joint space.
# --------------------------------------------------------------------------- #
_TOOL_DOWN = [0.0, 1.0, 0.0, 0.0]  # quat [w,x,y,z]: tool pointing straight down


def _tcp(position: list[float]) -> dict:
    return {"type": "move_tcp", "params": {"position": position, "orientation_quat": list(_TOOL_DOWN)}}


_DEFAULT_NAMED_POSES: dict[str, dict] = {
    "home": _tcp([0.40, 0.00, 0.55]),
    "clearance": _tcp([0.40, 0.00, 0.65]),   # lift straight up off the assembly
    "ok_bin": _tcp([0.30, -0.35, 0.45]),
    "reject_bin": _tcp([0.30, 0.35, 0.45]),
    # inspect_* poses are placeholders too; the sim camera path is deferred.
    "inspect_0": _tcp([0.45, 0.00, 0.50]),
    "inspect_1": _tcp([0.45, 0.10, 0.50]),
    "inspect_2": _tcp([0.45, -0.10, 0.50]),
}

_TERMINAL = {"succeeded", "failed", "rejected"}


def _load_named_poses() -> dict[str, dict]:
    raw = os.getenv("SIM_NAMED_POSES")
    if not raw and os.getenv("SIM_NAMED_POSES_FILE"):
        with open(os.environ["SIM_NAMED_POSES_FILE"], encoding="utf-8") as f:
            raw = f.read()
    if not raw:
        return dict(_DEFAULT_NAMED_POSES)
    table = json.loads(raw)
    if not isinstance(table, dict):
        raise ValueError("SIM_NAMED_POSES must be a JSON object of name -> {type, params}")
    # Overlay onto defaults so a partial table still resolves every waypoint.
    merged = dict(_DEFAULT_NAMED_POSES)
    merged.update(table)
    return merged


def _mat_to_pos_quat(pose_4x4: list[list[float]]) -> tuple[list[float], list[float]]:
    """4x4 row-major homogeneous transform -> ([x,y,z], [w,x,y,z]).

    Rotation->quaternion via Shepperd's method (numerically stable across all
    branches). Position is the translation column, taken verbatim (metres).
    """
    R = pose_4x4
    pos = [float(R[0][3]), float(R[1][3]), float(R[2][3])]
    m00, m01, m02 = R[0][0], R[0][1], R[0][2]
    m10, m11, m12 = R[1][0], R[1][1], R[1][2]
    m20, m21, m22 = R[2][0], R[2][1], R[2][2]
    tr = m00 + m11 + m22
    if tr > 0.0:
        s = math.sqrt(tr + 1.0) * 2.0
        w = 0.25 * s
        x = (m21 - m12) / s
        y = (m02 - m20) / s
        z = (m10 - m01) / s
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        w = (m21 - m12) / s
        x = 0.25 * s
        y = (m01 + m10) / s
        z = (m02 + m20) / s
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        w = (m02 - m20) / s
        x = (m01 + m10) / s
        y = 0.25 * s
        z = (m12 + m21) / s
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
        w = (m10 - m01) / s
        x = (m02 + m20) / s
        y = (m12 + m21) / s
        z = 0.25 * s
    n = math.sqrt(w * w + x * x + y * y + z * z) or 1.0
    return pos, [w / n, x / n, y / n, z / n]


class IsaacSimMovement:
    """MovementClient that drives the Isaac sim command bus."""

    def __init__(
        self,
        config: OrchestratorConfig,
        base_url: str | None = None,
        *,
        http: httpx.Client | None = None,
    ) -> None:
        self.c = config
        self.base_url = base_url or config.movement_sim_url
        self._http = http or httpx.Client(timeout=config.http_timeout_s)
        self.named_poses = _load_named_poses()
        self.steps = int(os.getenv("SIM_MOVE_STEPS", "60"))
        self.poll_interval_s = float(os.getenv("SIM_POLL_INTERVAL_S", "0.2"))
        self.cmd_timeout_s = float(os.getenv("SIM_CMD_TIMEOUT_S", "60"))

    # --- MovementClient Protocol -------------------------------------------- #
    def move_to_pose(self, pose_4x4: list[list[float]]) -> None:
        pos, quat = _mat_to_pos_quat(pose_4x4)
        self._execute("move_tcp", {"position": pos, "orientation_quat": quat, "steps": self.steps})

    def move_named(self, name: str) -> None:
        entry = self.named_poses.get(name)
        if entry is None:
            raise KeyError(
                f"no sim mapping for named pose {name!r}; add it to SIM_NAMED_POSES"
            )
        params = dict(entry.get("params", {}))
        params.setdefault("steps", self.steps)
        self._execute(entry["type"], params)

    def set_gripper(self, closed: bool, width: float | None = None) -> None:
        # The sim gripper has fixed open/closed positions and no force model, so
        # `width` is not applicable — the real-arm path is where width matters.
        self._execute("close_gripper" if closed else "open_gripper", {})

    # --- command bus -------------------------------------------------------- #
    def _execute(self, action_type: str, params: dict) -> dict:
        r = self._http.post(
            f"{self.base_url}/simulation/actions/execute",
            json={"type": action_type, "params": params},
            headers=self.c.auth_headers,
        )
        r.raise_for_status()
        cmd = r.json()
        cmd_id = cmd.get("id")
        if not cmd_id:
            raise RuntimeError(f"sim returned no command id for {action_type}: {cmd}")
        return self._await_command(cmd_id, action_type)

    def _await_command(self, cmd_id: str, action_type: str) -> dict:
        deadline = time.monotonic() + self.cmd_timeout_s
        while True:
            r = self._http.get(f"{self.base_url}/simulation/debug/commands/{cmd_id}")
            r.raise_for_status()
            cmd = r.json()
            status = (cmd.get("status") or "").lower()
            if status in _TERMINAL:
                if status != "succeeded":
                    raise RuntimeError(
                        f"sim {action_type} command {cmd_id} {status}: {cmd.get('error')}"
                    )
                return cmd
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"sim {action_type} command {cmd_id} still {status!r} after "
                    f"{self.cmd_timeout_s}s (is the Isaac worker running?)"
                )
            time.sleep(self.poll_interval_s)


class SimGrip:
    """Grip sensor for a sim run. The Isaac backend exposes no grip endpoint and
    has no force model, so grasp is assumed to succeed (the rectify/retry path is
    exercised against the real arm's current-based sensor). If a sim grip endpoint
    is ever added, set GRIP_SIM_URL and the factory uses HttpGrip instead."""

    def __init__(self, config: OrchestratorConfig) -> None:
        self.c = config
        self.always = os.getenv("SIM_GRIP_ALWAYS", "1").strip().lower() not in ("0", "false", "no")

    def is_grasped(self) -> bool:
        return self.always
