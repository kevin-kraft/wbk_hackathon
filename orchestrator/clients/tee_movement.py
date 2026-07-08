"""Fan a single movement command out to several backends at once.

Used by `robot_target="both"`: the real Jetson arm and the simulator move in
lock-step so the sim is a live digital twin of the real run. One backend is the
**primary** (the real arm) — its errors propagate and fail the step. The others
are **mirrors** (the sim): best-effort, so a sim hiccup can never break a run
that is actually driving hardware. Each command is dispatched to all backends
concurrently, so mirroring adds no serial latency to the loop.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from .base import MovementClient


class TeeMovement:
    def __init__(
        self,
        primary: MovementClient,
        mirrors: list[MovementClient],
        *,
        on_mirror_error: Callable[[str, Exception], None] | None = None,
    ) -> None:
        self.primary = primary
        self.mirrors = mirrors
        self._on_mirror_error = on_mirror_error
        # One worker per mirror so all backends move concurrently, not serially.
        self._pool = ThreadPoolExecutor(max_workers=max(1, len(mirrors)), thread_name_prefix="tee-mirror")

    def _fan(self, call: Callable[[MovementClient], None]) -> None:
        # Kick off the mirrors first (async), run the primary inline, then join —
        # the primary's exception surfaces, the mirrors' are caught and reported.
        futures = [self._pool.submit(call, m) for m in self.mirrors]
        try:
            call(self.primary)  # authoritative: its failure fails the step
        finally:
            for fut in futures:
                try:
                    fut.result()
                except Exception as exc:  # a sim fault must never break a real run
                    if self._on_mirror_error:
                        self._on_mirror_error("mirror", exc)

    def move_to_pose(self, pose_4x4: list[list[float]]) -> None:
        self._fan(lambda m: m.move_to_pose(pose_4x4))

    def move_named(self, name: str) -> None:
        self._fan(lambda m: m.move_named(name))

    def set_gripper(self, closed: bool, width: float | None = None) -> None:
        self._fan(lambda m: m.set_gripper(closed, width))
