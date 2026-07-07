# Robot Backend ==> Jetson PC  - Gruppe 2

FastAPI bridge that runs on the Jetson and talks to the LARA5 / NEURA robot
socket server.

The backend now contains two control levels:

- low-level robot command forwarding for maximum v1 flexibility
- higher-level KIP pose -> calibrated hover planning/execution

The old CLI prototype in `../../toimplementintojestonb/robot` was used as the
reference, but the production implementation lives here in `jetson_backend`.

## Start

```bash
cd ki_robotik_cv_seminar/jetson_backend
pip install -r requirements.txt
PYTHONPATH=..:. python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The deployment script already sets `PYTHONPATH`:

```bash
../deploy/start_jetson_backend.sh
```

Important environment variables:

```bash
ROBOT_HOST=127.0.0.1
ROBOT_PORT=65432
SOCKET_TIMEOUT=2.0

KIP_API_BASE=https://max-utils.com/KIP/api
KIP_PIPELINE=gdrnpp

JETSON_DATA_DIR=./data
ALLOW_RAW_ROBOT_COMMANDS=true
```

Calibration files are stored under:

```text
jetson_backend/data/calibration/session.json
jetson_backend/data/calibration/base_world.json
```

## Existing Endpoints

```text
GET  /health
POST /command
POST /robot/execute/
WS   /ws/joint_states
```

`/command` and `/robot/execute/` are kept for compatibility with the existing
frontend/simulation code.

## Raw Robot Commands

```text
POST /robot/raw
```

For v1 this is the freedom endpoint. It forwards any robot socket function name
with positional and keyword arguments.

Example:

```json
{
  "function_name": "get_tcp_pose",
  "args": [],
  "kwargs": {}
}
```

Motion example:

```json
{
  "function_name": "move_linear",
  "args": [],
  "kwargs": {
    "speed": 0.05,
    "acceleration": 0.05,
    "target_pose": [
      [0.4, 0.2, 0.3, 3.14, 0.0, 1.9],
      [0.45, 0.25, 0.25, 3.14, 0.0, 1.9]
    ],
    "current_joint_angles": [0, 0, 0, 0, 0, 0]
  }
}
```

Set `ALLOW_RAW_ROBOT_COMMANDS=false` to disable this endpoint.

## Probe

```text
GET /robot/probe
```

Reads telemetry without issuing motion:

- `get_tcp_pose`
- `get_current_joint_angles`
- `get_errors`
- `motion_status`
- `program_status`

## Calibration

Add a world/base correspondence:

```text
POST /robot/calibration/points
```

If `q_base` is omitted, the backend reads the current TCP pose and uses its XYZ.

```json
{
  "p_world": [0.5, 0.35, 0.0],
  "q_base": [0.42, 0.18, 0.11],
  "table_origin": [0.4, 0.3, 0.0],
  "meta": {
    "part": "Anker_Lang",
    "confidence": 0.9
  }
}
```

Solve and save `base_world.json`:

```text
POST /robot/calibration/solve
```

```json
{
  "tool_down_from_tcp": true
}
```

or:

```json
{
  "tool_down_rpy": [3.1415, 0.0, 1.9]
}
```

Read the current saved calibration:

```text
GET /robot/calibration
```

## Hover Planning

```text
POST /robot/hover/plan
```

Computes the hover target and returns all safety gates. It does not move the
robot.

Use a pose result directly:

```json
{
  "pose_result": {
    "meta": {
      "table_origin": [0.4, 0.3, 0.0]
    },
    "results": [
      {
        "instance_id": 0,
        "part": "Anker_Lang",
        "confidence": 0.9,
        "t_world": [0.1, 0.05, 0.0]
      }
    ]
  },
  "part": "Anker_Lang",
  "hover_clearance": 0.1
}
```

Or let the backend call the KIP pose API for a local image path on the Jetson:

```json
{
  "image_path": "/home/lara5/images/shot.png",
  "part": "Anker_Lang"
}
```

Safety gates:

- A: selected instance confidence is high enough
- B: world XY point is inside `WORKSPACE_BOX`
- C: calibration residuals are below threshold and `tool_down_rpy` exists
- D: target is inside the taught base workspace box
- F: target is within `MAX_TCP_JUMP_M` of the current TCP

## Hover Execution

```text
POST /robot/hover/execute
```

Runs the same plan and moves only if all gates pass and `confirmation` is exactly
`"yes"`.

```json
{
  "pose_result": {
    "meta": {
      "table_origin": [0.4, 0.3, 0.0]
    },
    "results": [
      {
        "instance_id": 0,
        "part": "Anker_Lang",
        "confidence": 0.9,
        "t_world": [0.1, 0.05, 0.0]
      }
    ]
  },
  "part": "Anker_Lang",
  "hover_z_abs": 0.15,
  "speed": 0.05,
  "confirmation": "yes"
}
```

Execution path:

1. Compute and validate hover plan.
2. Serialize motion with a backend lock.
3. Move to a safe intermediate Z.
4. Move linearly to the hover target.
5. Return final TCP pose.

Speed and acceleration are hard-clamped by `SPEED_CAP_MS` and `ACCEL_CAP`.
