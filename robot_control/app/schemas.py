"""Local request/response models.

`RobotCommand` was originally imported from an out-of-repo `shared.jetson`
module (the Jetson project root on the LARA5 PC). It's vendored here so the
service is self-contained and container-buildable.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RobotCommand(BaseModel):
    """A raw call forwarded to the robot socket server."""

    function_name: str
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)
