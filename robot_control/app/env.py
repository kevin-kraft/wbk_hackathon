import os
from pathlib import Path


def get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    return float(value)


def get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}

ROBOT_HOST = os.getenv("ROBOT_HOST", "127.0.0.1")
ROBOT_PORT= int(os.getenv("ROBOT_PORT", "65432"))

API_HOST= os.getenv("API_HOST", "0.0.0.0")
API_PORT=int(os.getenv("API_PORT", "8000"))

SOCKET_TIMEOUT=get_float("SOCKET_TIMEOUT", 2.0)
JOINT_STREAM_DT=get_float("JOINT_STREAM_DT", 0.05)

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("JETSON_DATA_DIR", BASE_DIR / "data"))
CALIBRATION_DIR = DATA_DIR / "calibration"
CALIBRATION_SESSION_PATH = CALIBRATION_DIR / "session.json"
CALIBRATION_PATH = CALIBRATION_DIR / "base_world.json"

KIP_API_BASE = os.getenv("KIP_API_BASE", "https://max-utils.com/KIP/api")
KIP_PIPELINE = os.getenv("KIP_PIPELINE", "gdrnpp")
KIP_POLL_INTERVAL_S = get_float("KIP_POLL_INTERVAL_S", 0.4)
KIP_POLL_TIMEOUT_S = get_float("KIP_POLL_TIMEOUT_S", 180.0)

WORKSPACE_BOX = ((-0.25, 1.07), (-0.12, 0.72))

CALIB_RMS_MAX_M = get_float("CALIB_RMS_MAX_M", 0.005)
CALIB_MAX_ERR_M = get_float("CALIB_MAX_ERR_M", 0.010)
CALIB_MIN_POINTS = int(os.getenv("CALIB_MIN_POINTS", "3"))

MIN_CONFIDENCE = get_float("MIN_CONFIDENCE", 0.5)
HOVER_CLEARANCE_M = get_float("HOVER_CLEARANCE_M", 0.10)
MAX_TCP_JUMP_M = get_float("MAX_TCP_JUMP_M", 0.60)
SPEED_CAP_MS = get_float("SPEED_CAP_MS", 0.05)
ACCEL_CAP = get_float("ACCEL_CAP", 0.05)
WORKSPACE_BASE_MARGIN_M = get_float("WORKSPACE_BASE_MARGIN_M", 0.05)
ALLOW_RAW_ROBOT_COMMANDS = get_bool("ALLOW_RAW_ROBOT_COMMANDS", True)
