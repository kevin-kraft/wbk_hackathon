"""app/schemas.py — the vendored RobotCommand model.

RobotCommand was inlined from an out-of-repo `shared.jetson` module so the
service is self-contained; these tests just pin down its field defaults and
required field.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import RobotCommand


def test_defaults_are_empty_list_and_dict():
    cmd = RobotCommand(function_name="get_tcp_pose")
    assert cmd.function_name == "get_tcp_pose"
    assert cmd.args == []
    assert cmd.kwargs == {}


def test_default_containers_are_independent_per_instance():
    # Field(default_factory=...) must not share a mutable default across
    # instances (the classic `args: list = []` bug this vendoring avoids).
    a = RobotCommand(function_name="a")
    b = RobotCommand(function_name="b")
    a.args.append(1)
    a.kwargs["x"] = 1
    assert b.args == []
    assert b.kwargs == {}


def test_function_name_is_required():
    with pytest.raises(ValidationError):
        RobotCommand()


def test_accepts_explicit_args_and_kwargs():
    cmd = RobotCommand(function_name="move_linear", args=[1, "a"], kwargs={"speed": 0.1})
    assert cmd.args == [1, "a"]
    assert cmd.kwargs == {"speed": 0.1}
