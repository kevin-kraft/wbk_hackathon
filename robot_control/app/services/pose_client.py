from __future__ import annotations

import time

import requests

from app import env


def infer_image(image_path: str, *, base: str | None = None, pipeline: str | None = None, timeout_s: float | None = None) -> dict:
    base = (base or env.KIP_API_BASE).rstrip("/")
    pipeline = pipeline or env.KIP_PIPELINE
    timeout_s = timeout_s or env.KIP_POLL_TIMEOUT_S

    with open(image_path, "rb") as image:
        response = requests.post(
            f"{base}/real/infer_async",
            files={"image": image},
            data={"pipeline": pipeline},
            timeout=30,
        )
    response.raise_for_status()
    job = response.json()["job"]

    deadline = time.time() + timeout_s
    while True:
        status_response = requests.get(f"{base}/real/job/{job}", timeout=15)
        status_response.raise_for_status()
        status = status_response.json()
        if "error" in status and "pct" not in status:
            raise RuntimeError(f"job {job} error: {status['error']}")
        pct = status.get("pct", 0)
        if pct < 0:
            raise RuntimeError(f"job {job} failed: {status.get('phase')}")
        if pct >= 100:
            break
        if time.time() > deadline:
            raise RuntimeError(f"job {job} timed out at pct={pct}")
        time.sleep(env.KIP_POLL_INTERVAL_S)

    result_response = requests.get(f"{base}/real/result/{job}", timeout=30)
    result_response.raise_for_status()
    return result_response.json()


def select_instance(pose_result: dict, *, part: str | None = None, instance_id: int | None = None, min_conf: float | None = None) -> dict:
    min_conf = env.MIN_CONFIDENCE if min_conf is None else min_conf
    candidates = []
    for result in pose_result.get("results", []):
        if part is not None and result["part"] != part:
            continue
        if instance_id is not None and result["instance_id"] != instance_id:
            continue
        if result["confidence"] < min_conf:
            continue
        candidates.append(result)
    if not candidates:
        raise ValueError(
            f"no instance matched (part={part}, id={instance_id}, min_conf={min_conf}); "
            f"{len(pose_result.get('results', []))} total in result"
        )
    return max(candidates, key=lambda item: item["confidence"])
