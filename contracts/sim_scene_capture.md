# Proposed contract — simulator scene capture / preview

*Draft for Group 2 (the Isaac `simulation_backend`). The dashboard already calls
these; until they exist it degrades gracefully (shows "not implemented yet").*

The `simulation_backend` has **no way to produce an image** — no viewport/render
route, and `GET_ZIVID_DATA` raises `NotImplementedError`. These two endpoints
close that gap so the frontend's Sim mode can preview the scene and feed the
perception/pose stack the same way the real Zivid does.

## The rendering plumbing already EXISTS — this is a wiring job, not a build

The functions needed are already implemented and working on the box, just not in
`simulation_backend`. **Reuse these instead of writing rendering from scratch:**

- **`isaacsim.zivid`** — a full Isaac Sim extension modelling the Zivid camera
  (mount, hand-eye calibration, structured-light depth, even a GUI *Capture*
  button). Source: `Desktop/Gruppe3/trainingsdatengenerierung/src/zivid-isaac-sim/
  source/isaacsim.zivid`. `assembler/mount_camera.py::assemble_zivid_casing_on_robot(...)`
  mounts a `/World/Zivid` prim at a calibration pose.
- **`trainingsdatengenerierung.rendering.Renderer`** (`Gruppe3/.../src/trainingsdatengenerierung/rendering.py`)
  — creates an `omni.replicator.core` render product on a camera prim, attaches
  annotators, and `capture()` returns `{rgb: ndarray, depth: (H,W) float32 metres
  (NaN=invalid), semantic_seg, instance_seg, bbox_2d}`. Pair with
  `camera.build_zivid_camera(...)` for realistic structured-light depth and
  `camera.compute_intrinsics/read_intrinsics` for the `K` matrix.
- **`closingr2s/sim_capture.py`** (`Gruppe5/.../src/closingr2s/`) — a headless
  single-shot capture (the GUI Capture button's CLI twin): enable the extension,
  find the `is_zivid_camera` prim, warm up, capture RGB + depth (XYZ mm). This is
  the closest thing to "capture one frame like a Zivid" and the best template.

**Integration sketch (in the Isaac worker, which already holds the SimulationApp):**
boot with `enable_cameras: True`; `enable_extension("isaacsim.zivid")`; ensure a
`/World/Zivid` prim exists in the loaded stage (mount via the extension if not);
build a `Renderer("/World/Zivid", W, H, ["rgb","depth"], zivid_camera=...)` once;
on a capture command call `Renderer.capture()`, encode `rgb`→PNG and
`depth` (metres→uint16-mm PNG, NaN/0=no-data), and return the JSON below.
Caveats: a render product needs `enable_cameras:True` at SimulationApp boot and
adds VRAM/GPU load (the box GPU is already shared/constrained); two SimulationApps
can't coexist, so import `Renderer` in-process rather than running the SDG
orchestrator (which boots its own).

Base URL = the sim backend (`MOVEMENT_SIM_URL`, e.g. `:8100`). Both may be
synchronous (render the viewport and return inline) — a render is fast enough
that the command-bus round-trip isn't required; if you'd rather enqueue them as
`SimulationCommand`s, tell us and the client will poll instead.

## `POST /simulation/scene/preview`

A **frontal, slightly-elevated overview** of the arm + table — a human-facing
"what's in the scene" shot, not a metric capture. RGB only.

```jsonc
// request: {} (optional camera hints later)
// response
{ "image_b64": "<base64 PNG, RGB>" }
```

## `POST /simulation/scene/capture`

The **Zivid-equivalent** capture from the simulated scene camera — same viewpoint
and output shape as the real `scene_camera` service (`contracts/scene_camera_api.md`),
so it drops into the orchestrator's `SceneCamera` seam behind `SCENE_CAMERA_URL`
with no other changes, and the dashboard can run detection on it.

```jsonc
// request: {}
// response  (superset of the orchestrator SceneFrame)
{
  "rgb_b64":   "<base64 PNG>",       // RGB, true colour (see channel note)
  "depth_b64": "<base64 16-bit PNG>", // depth in millimetres, 0 = no data; null if not rendered
  "K":         [fx,0,cx, 0,fy,cy, 0,0,1],  // flat-9 intrinsics of the sim camera
  "width":  1920,
  "height": 1200,
  "backend": "isaac"
}
```

Notes:
- **Camera pose:** match the real Zivid mount (roughly top-down over the table) so
  poses/masks transfer between sim and real. The hand-eye extrinsic the
  orchestrator holds (`T_BASE_CAM`) assumes that mount.
- **Depth:** 16-bit millimetre PNG, `0` = no return — identical to
  `scene_camera`'s `encode_depth_mm_b64`.
- **Channel order caveat:** the perception `/infer` services and browsers expect
  **true RGB**. (The real `scene_camera` stores BGR-ordered PNG tuned for the
  pose stage's cv2 decoder — please emit **true RGB** here, or flag it, so
  detection colours aren't swapped.)
- **Auth/CORS:** the dashboard sends `Authorization: Bearer` if a token is set and
  calls cross-origin — keep CORS permissive like the other routers.
- Return **404 or 501** while unimplemented; the client shows a friendly
  "not available yet" state on those.
