# Changelog (`.agent/` documentation)

Newest first.

- 2026-07-08 — Perception debugging session + durable GPU-server redeploy
  captured (commits `fcc2773`, `2485997`, `7f12f41` — these landed *after*
  the previous capture entry below despite predating it in this changelog's
  reading order; the previous capture task's scope didn't cover them).
  **Sim-to-real fixes (`fcc2773`):** gray-world white balance on the Zivid
  RGB (`scene_camera/imaging.py:white_balance_grayworld`,
  `SCENE_WHITE_BALANCE=grayworld` default, zivid-backend only) — channel
  means shifted ~R106/G109/B82 → R94/G92/B96 on a captured frame; YOLO-Det
  went from 0 boxes @0.25 conf to a `buerstenhalter_tray` detection @0.93
  (and, on a separate frame per the commit message, 0→3 boxes @0.94/0.79).
  Frontend detection default conf lowered 0.25→0.10 (`runYolo()`/
  `runYoloSeg()`, `frontend/src/lib/api.ts`) as a companion stopgap for the
  same gap. Added `Decisions/0017-grayworld-white-balance-sim-to-real.md`
  (ADR: both changes, why gray-world is sufficient for this rig, why lower
  conf is a stopgap not a fix, the still-open durable fix — fine-tuning on
  real labelled frames, no dataset exists yet). **Two bug fixes found in the
  same debugging pass:** `locateanything`'s `.generate()` call was missing
  `use_cache=True`, which the custom `nvidia/LocateAnything-3B` model's own
  `generate()` asserts — every `/infer` 500'd
  (`perception/services/locateanything/model.py`); and the shared
  `app_factory.py` catch-all exception handler runs in Starlette's
  `ServerErrorMiddleware`, above the CORS middleware, so its 500 responses
  never carried `Access-Control-Allow-Origin` — the browser reported an
  opaque network error instead of an inspectable HTTP 500, which is what
  made the `locateanything` bug harder to diagnose than a normal 500. Both
  fixed; documented as gotcha paragraphs (not ADRs — bug fixes, not
  decisions with alternatives) in `System/architecture.md` (Stage 1
  Perception) and `System/integration_points.md` (the model-adapter
  pattern section). **Also in `fcc2773`:** SAM3/LocateAnything's `anker`
  part prompt corrected from the German name `"anker"` (0 masks — didn't
  match either open-vocab model's training distribution) to the English
  open-vocab concept `"copper part"` (12 masks) — `frontend/src/lib/parts.ts`;
  documented in `System/dashboard.md`'s PartSelector bullet.
  **Pose pipeline exposed as a run option (`2485997`):** closes the wiring
  gap [ADR 0016](./Decisions/0016-gigapose-2d-planar-pose-mode.md) flagged
  as still-open — `OrchestratorConfig` gained `pose_pipeline` (env
  `POSE_PIPELINE`, default `rgbd`) and `gigapose_url` (env `GIGAPOSE_URL`);
  `HttpPose.estimate()` now sends `pipeline` (+ `plane_z` for `2d`) and
  routes `2d`/`rgb` to `gigapose_url`, `rgbd` to `pose_url`; `POST /run` and
  `GET /events/run` take a new `pose_pipeline` query param (per-run
  override, same shape as `?target=`), echoed back in the `/run` response.
  Dashboard: a new Pose selector in `RunControls` (6DoF / 6DoF·RGB / 2D), a
  persisted default in Settings → Run defaults, threaded through
  `RunContext` → `useRunStream` → `runStreamUrl` as `&pose_pipeline=`; new
  `PosePipeline` type (`lib/types.ts`); dry runs omit the param (mocks).
  `docker-compose.yml`/`docker-compose.remote-gpu.yml` gained `GIGAPOSE_URL`
  wiring. Added an "Update" section to ADR 0016 documenting the closed gap.
  Added a new "Pose pipeline selection" section to `System/orchestrator.md`
  (mirroring the existing "Robot target selection" section) and a new "Pose
  pipeline selector" section to `System/dashboard.md`; updated both docs'
  Config/Entry-points/Related-Docs and the four-pages/Settings-row
  descriptions. Updated `System/architecture.md`'s Stage 2 `pipeline='2d'`
  paragraph and "Not yet built" (the orchestrator-wiring bullet is now
  "real-robot grasp success unverified", not "not wired at all") and
  `System/integration_points.md`'s Contract 2 paragraph accordingly.
  **Durable `wbk-perception` redeploy (`7f12f41`):** the running
  `wbk-perception` container had baked-in code (hotfixed via ephemeral
  `docker cp`, lost on any recreate), `--restart no` (doesn't survive a
  reboot), and a redundant `sam3` process wasting GPU memory alongside the
  already-working standalone `wbk-sam3`. `deploy/perception/redeploy-wbk-perception.sh`
  (+ `deploy/perception/README.md`) recreates it durably: canonical source
  bind-mounted from `/mnt/vss-data/kip/perception` (same tree
  `wbk-yoloseg` already uses), `--restart unless-stopped`, a dedicated
  `supervisord.wbk-perception.conf` running only `yolo`+`locateanything`
  (written onto the canonical source), and a `supervisorctl` control socket
  so either program restarts independently
  (`docker exec wbk-perception supervisorctl -c
  .../supervisord.wbk-perception.conf restart locateanything`). Idempotent;
  sanity-checks the canonical source carries the `use_cache`/CORS fixes
  before proceeding. Added `Decisions/0018-durable-wbk-perception-redeploy.md`
  (ADR: the three problems, why bind-mount+restart-policy+trimmed-config+
  control-socket, rejected full-image-rebuild alternative, consequences —
  now only two services, canonical-source parity with `wbk-yoloseg`).
  Rewrote `SOP/deploy_perception_gpu_server.md`'s container topology
  section (dedicated config, bind-mounted source, restart policy) and added
  a new "Redeploying `wbk-perception`" section with the script invocation
  and the no-rebuild code-update procedure; added a clarifying note on the
  HF-cache mount's actual server-side path
  (`/mnt/vss-data/kip/weights/hf-cache`). **No new test coverage** for any
  of the three commits (204 pytest / 30 Vitest counts unchanged) — all
  verification was manual against the live rig/deployed services; noted
  explicitly in `System/architecture.md`'s Test suite section. Updated
  `README.md`'s `System/architecture.md`, `System/integration_points.md`,
  `System/orchestrator.md`, `System/dashboard.md`, and
  `SOP/deploy_perception_gpu_server.md` one-liners; added ADR 0017 and ADR
  0018 to the Decisions index.
- 2026-07-08 — GigaPose gains a CAD-free 2D (planar) pose mode (commit
  `79f9ffa`, deploy script `f2a5da8`), and a mask-encoding bug that was
  blanking YOLO-Seg masks got fixed (commit `4b6d1d3`). **2D pose mode:**
  new `pipeline="2d"` on GigaPose's `POST /pose`
  (`pose/gigapose_svc/app.py`) — CAD-free, model-free: back-projects the
  mask centroid to a 3D point (depth priority: per-mask median depth →
  caller `plane_z` → built-in default; `stage` in `{2d, 2d-plane,
  2d-defaultz}`) and builds a top-down grasp orientation whose in-plane yaw
  follows the mask's PCA principal axis, in new module
  `pose/shared/planar.py` (`planar_pose()`, numpy-only). Returns the same
  `T_cam_obj` contract (ADR 0004) — a drop-in for the orchestrator/frontend.
  `pose/shared/schemas.py`'s `PoseRequest.pipeline` gains `'2d'` plus an
  optional `plane_z` field. Inspired by the KIP seminar's `detect_and_move`
  (centroid+depth→world point, fixed top-down), enriched with in-plane
  orientation. Startup now degrades gracefully: `gigapose_svc/app.py`'s
  lifespan wraps `GigaPoseRunner.load()` in try/except, so a missing/failed
  6DoF model no longer blocks startup — the service just serves
  `pipeline='2d'`, and a `'rgb'`/`'rgbd'` request then 503s with an explicit
  message. This matters because the deployed `wbk-gigapose` has **no CAD
  templates for this project's parts** (`GET /health`'s `classes: []`), so
  6DoF pose can't run against real parts today — 2D mode is the only
  currently-working real-part pose path. Verified end-to-end against real
  YOLO-Seg masks: 3 poses in 55ms, distinct per-part yaw, `stage=2d-plane`.
  Note: the orchestrator does **not** yet call `pipeline='2d'` —
  `HttpPose.estimate()` never sets `pipeline` (defaults to `'rgbd'`) and
  `pose_url` defaults to FoundationPose, not GigaPose — wiring the loop to
  use 2D mode is follow-up work, flagged in `System/architecture.md`'s "Not
  yet built". Added `Decisions/0016-gigapose-2d-planar-pose-mode.md` (ADR:
  why a CAD-free/model-free mode, the seminar inspiration, the
  graceful-degrade design, rejected alternatives — blocking on CAD/template
  production, a parallel response schema, hard-fail startup). **Deployment
  reality captured for the first time:** the pose services
  (`wbk-gigapose`, `wbk-foundationpose`) run on **podman, not docker**, on
  the same shared GPU server as perception — invisible to `docker ps`,
  root-managed under a custom store
  (`sudo podman --root /mnt/vss-data/kip/podman/storage --runroot
  /run/containers/storage`). The `wbk-gigapose` image bakes pose code at
  `/svc`; only the GigaPose repo is bind-mounted. Deployed via new
  `training/deploy_gigapose_2d.sh`: `podman cp` the three changed files into
  `/svc` + `podman restart` (preserves the container's existing GPU/mount/env
  config; durable across restart, lost on `podman rm`). Also newly
  documented: the deployed pose services **require** `WBK_API_TOKEN`
  (unlike perception, where it's currently unset) — a footgun for anyone
  assuming one auth posture across the whole GPU server. Added new SOP
  `SOP/deploy_pose_podman.md` covering all of the above (topology, auth,
  the `classes: []` reality, the `podman cp`+restart deploy pattern and its
  durability caveat, reaching pose from a local orchestrator). **Mask fix:**
  `perception/services/shared/imaging.py`'s `encode_mask_png_b64` skipped
  its 0/255 binarization for any already-`uint8` input, but Ultralytics
  `result.masks.data` is a uint8 `{0,1}` tensor — so YOLO-Seg masks went out
  at `{0,1}`, and every consumer's `> 127` threshold read them as **empty**:
  the dashboard's YOLO-Seg overlay rendered blank, and `gigapose
  pipeline='2d'` raised "empty mask" against real masks (this is what
  surfaced the bug, while wiring 2D mode against real YOLO-Seg output).
  Fixed to always binarize (`(mask > 0) * 255`, idempotent for already-0/255
  inputs); redeployed `wbk-yoloseg`. Note: `sam3` uses the same encoder from
  a separate image (`wbk-sam3`) and only picks up the fix on its next
  rebuild/redeploy. Extended `System/architecture.md`: Stage 2 Pose section
  rewritten with a new "GigaPose `pipeline='2d'`" subsection (mode
  description, the no-CAD-templates reality, the graceful-degrade startup
  change, the not-yet-wired orchestrator gap), a new mask-encoding gotcha
  paragraph under Stage 1's `yoloseg` description, a new "Not yet built"
  bullet for the orchestrator↔2D-mode wiring gap, Related Docs gained ADR
  0016 and the new SOP. Extended `System/integration_points.md`: Contract 2
  gained the `plane_z` field and a `pipeline='2d'` paragraph, Contract 1
  gained the mask-encoding gotcha paragraph (general — applies to any
  mask-producing service, not just `yoloseg`), Related Docs gained ADR 0016
  and the new SOP. Extended `SOP/running_services.md`: Related Docs gained
  the new SOP and ADR 0016, and fixed a stale "in progress, not yet running"
  claim about the (already-deployed) perception GPU-server SOP left over
  from an earlier pass. Added ADR 0016 and the new SOP to `README.md`'s
  indices; updated the `System/architecture.md`/`System/integration_points.md`
  one-liners.
- 2026-07-08 — New `yoloseg` perception service documented (commit `27fee6c`,
  "Add YOLO-Seg service + manual image upload; wire trained parts models
  into dashboard"). `perception/services/yoloseg/` (`model.py`/`main.py`)
  serves the trained `parts_seg_v1` instance-segmentation model — boxes +
  per-instance masks + part labels in one pass, closed-vocab over the same
  18 disassembly-part classes as the `yolo` detector, via Ultralytics
  `predict(..., retina_masks=True)` for full-res masks. New
  `YoloSegRequest`/`SegInstance`/`YoloSegResponse` schemas and
  `yolo_seg_weights`/`YOLO_SEG_WEIGHTS` config
  (`perception/services/shared/{schemas,config}.py`); registered as a
  fourth `supervisord` program (port 8007) and in `docker-compose.yml`
  locally. On the GPU server, deployed instead as a **third sidecar
  container**, `wbk-yoloseg` (host port `6770`, `--gpus device=1`,
  `training/deploy_yolo_seg.sh`) — because the already-running
  `wbk-perception:blackwell` image predates the `yoloseg` service dir, the
  script runs it from that same image with the current `perception/`
  source bind-mounted over `/app/perception` (rsync'd from the laptop
  first) instead of rebuilding. Added
  `Decisions/0015-yoloseg-sidecar-container-no-rebuild.md` (ADR: mounted-source
  sidecar over image rebuild, why, and the consequence that
  `wbk-perception`'s own baked-in source is now stale relative to the repo
  — harmless, since only `wbk-yoloseg` needs the new code). Documented an
  **important host-port gotcha** explicitly: on the GPU server, this
  project's perception ports are `6767`/`6768`/`6769`/`6770`
  (yolo/sam3/locate/yoloseg) — host port `8001` belongs to a different
  team's service, not this project's `yolo`; container-internal ports
  `8001`/`8002`/`8003`/`8007` never appear on the host's port space. SSH
  tunnel extended with `18007→6770`. Also noted: `yoloseg` is **not**
  consumed by the orchestrator (`docker-compose.remote-gpu.yml` has no
  `PERCEPTION_YOLOSEG_URL`) — it's dashboard-only, for manual inspection on
  the Perception page. Frontend: `yolo` relabeled `YOLO-Det` and the stale
  "COCO-80 won't recognise parts" copy removed (the detector has served
  trained `parts_detmask` weights since `training/`'s YOLO pass); new
  `YOLO-Seg` model option added and made the **default** selected model on
  the Perception page (was `sam3`); `yoloseg` wired through `ServiceKey`
  (`lib/types.ts`), `SERVICE_KEYS`/`localhostDefaults()`/`envDefaults()`
  (`config/runtime.ts`, new `VITE_YOLOSEG_URL`), `runYoloSeg()` (`lib/api.ts`),
  `ServiceHealthStrip` (`yolo·det`/`yolo·seg` short labels), `SettingsPage`
  labels, and the gitignored `deploy-local/config.json` (points `yoloseg`
  at `http://127.0.0.1:18007`, the local tunnel end). Also shipped in the
  same commit: a **manual image upload** debug aid on the Perception page
  (`uploadImage()` — `FileReader` → base64 straight into scene state,
  `SceneCapture.backend="upload"`) so detection/segmentation can be
  exercised against an arbitrary local image with no sim/Zivid/camera
  running; works with all four perception models. Verified end-to-end
  against a real dataset frame: YOLO-Det 7 boxes @0.99-1.0, YOLO-Seg 8
  masks @0.96-0.99 with valid full-res PNG masks. **No new frontend test
  coverage** for either addition — Vitest suite stays at 30 tests; `npm run
  build` passes. Extended `System/architecture.md`: Stage 1 Perception
  section gained the `yoloseg` service row/description and a link to ADR
  0015; Related Docs gained the new ADR. Extended `System/training.md`:
  new "Deployment: `deploy_yolo_seg.sh`" section (mirrors the existing
  `deploy_yolo_weights.sh` section), results table's `parts_seg_v1` row
  marked **deployed**, Related Docs gained ADR 0015. Rewrote
  `SOP/deploy_perception_gpu_server.md`'s container topology (two → three
  containers), added the host-port gotcha paragraph, the "not consumed by
  the orchestrator" note, the tunnel port-map update, and a condensed
  "Deploying the trained YOLO-Seg model" section pointing to
  `System/training.md` for the full script breakdown (same
  SOP-condenses/System-details pattern as the existing YOLO-weights
  section). Extended `System/dashboard.md`: new "YOLO-Seg + manual image
  upload" section, Perception page row rewrite, Related Docs gained ADR
  0015, Test suite section's "no new coverage" note extended to cover this
  same-day follow-up commit. Added ADR 0015 to `README.md`'s Decisions
  index; updated the `System/dashboard.md`, `System/training.md`, and
  `SOP/deploy_perception_gpu_server.md` one-liners (three containers, the
  host-port gotcha, the YOLO-Seg deploy script).
- 2026-07-08 — Robot target selection (`real|sim|both`) and the Isaac Sim
  digital-twin integration documented (working tree at capture time, not yet
  committed; developed concurrently with, and touching some of the same
  files as, the ERP/LLM planning-head feature captured below — the two are
  independent capabilities). `orchestrator/config.py` gained `ROBOT_TARGET`
  (env, default `real`) plus `MOVEMENT_SIM_URL`/`GRIP_SIM_URL`;
  `orchestrator/factory.py:_build_robot()` resolves it to `HttpMovement`+
  `HttpGrip` (`real`), `IsaacSimMovement`+`SimGrip`/`HttpGrip`
  (`sim` — `clients/sim_movement.py`, a dedicated adapter for the Isaac
  backend's async submit/poll command bus, since it doesn't speak the
  synchronous `contracts/movement_api.md` shape), or `TeeMovement` (`both`
  — `clients/tee_movement.py`: real arm primary/authoritative, sim mirrored
  concurrently and best-effort, mirror faults reported as a new `SIM_WARN`
  `LoopEvent`, never raised). Overridable per-run via the existing
  `?target=` query param on `POST /run`/`GET /events/run` — no restart.
  `IsaacSimMovement` maps `move_to_pose`/`move_named`/`set_gripper` onto the
  sim's `move_tcp`/`move_joint`/`open_gripper`/`close_gripper` actions
  (rotation→quaternion via Shepperd's method) and carries its own
  named-pose teach table (`SIM_NAMED_POSES`/`SIM_NAMED_POSES_FILE`,
  `deploy/sim_named_poses.example.json` — placeholder positions, not
  measured). New contracts `contracts/simulation_api.md` (the command-bus
  surface, named-pose gap) and `contracts/sim_scene_capture.md` (draft,
  unimplemented — `GET_ZIVID_DATA` isn't wired up on the sim side yet, so
  `sim`/`both` runs still need the real Zivid for perception input). 22 new
  tests (`tests/orchestrator/test_robot_target.py`,
  `test_sim_movement.py`), included in the still-204 pytest total (these
  files already existed in the working tree when that count was last
  recorded). Frontend: `RunControls` gained a Real/Sim/Both toggle
  (disabled during dry-run/while running, sim options greyed out until a
  simulator endpoint is configured) and an `activeTarget` badge fed by a
  new `start` SSE listener in `useRunStream.ts`; new `SourceToggle`/
  `PartSelector`/`SceneView` components and a full rewrite of
  `PerceptionPage.tsx` (was a static stub; now capture→infer→overlay
  against YOLO/SAM 3/LocateAnything, real Zivid or sim-rendered scenes);
  `lib/api.ts` gained `captureScene`/`generateScenePreview` (both
  normalizing a sim `404`/`501` into a `SIM_NOT_IMPLEMENTED` sentinel with a
  friendly "not implemented yet" message) and `runYolo`/`runSam3`/
  `runLocate`; `lib/types.ts` gained a `ConfigPatch` type (replacing ad hoc
  `Partial<RuntimeConfig>` casts) and `SourceMode`/`RobotTarget`/`SIM_WARN`;
  `frontend/public/config.json`'s committed perception/pose ports moved to
  `localhost:1800{1-5}` and movement/grip to `localhost:9000`/`9001`
  (previously a hardcoded Jetson IP), matching the SSH-tunnel convention in
  [SOP: deploying perception to a remote GPU server](./SOP/deploy_perception_gpu_server.md).
  **No new frontend test coverage** for the sim UI components/PerceptionPage
  rewrite — Vitest suite stays at 30 tests; `npm run build` (type-check)
  passes. Verified together: `uv run pytest` (204 collected) and `npm run
  build` both pass on the full working tree (this feature + the
  concurrently-developed planning head). Added
  `Decisions/0014-robot-target-real-sim-both.md` (ADR: why sim is a
  mirrored digital twin, not a peer, with `TeeMovement`'s primary/mirror
  trust asymmetry as the safety mechanism; why `IsaacSimMovement` is a
  dedicated adapter rather than a second `HttpMovement`; rejected
  alternatives — a second orchestrator instance, real/sim voting). Extended
  `System/orchestrator.md`: new "Robot target selection" section
  (`factory.py:_build_robot`, the sim command-bus mapping table, the
  named-pose teach-table gap), Protocol seam table's `MovementClient`/
  `GripSensor` rows, Config section, Tests section. Extended
  `System/architecture.md`: pipeline diagram gained the sim mirror branch,
  stage table gained a Simulator (digital twin) row and an updated Grip
  detection row, two new "Not yet built" bullets (sim scene capture, the
  named-pose teach table), a test-suite cross-reference. Extended
  `System/dashboard.md`: new "Sim / digital-twin UI" section, pages table,
  components list, runtime-config section (new service keys, `ConfigPatch`,
  `config.json` port changes), `useRunStream`/`runContext` prose, Test
  suite section (the coverage-gap note). Note: ADR numbers 0012/0013 were
  already claimed by a concurrently-run YOLO-training documentation pass
  (see the entry below) by the time this ADR was written — this feature's
  ADR was numbered 0014 to avoid collision; no other renumbering was
  needed. Added the new ADR and updated the `System/orchestrator.md`/
  `System/dashboard.md` one-liners in `README.md`'s indices.
- 2026-07-08 — New YOLOv26 training pipeline (`training/`) documented, and the
  GPU-server perception deployment (previously "in progress, not yet running"
  in this doc set) confirmed **deployed and running**. `training/` converts
  Isaac-Sim Replicator (SDG) synthetic renders into Ultralytics YOLO datasets
  (`isaac_to_yolo.py`, three task modes — `det`/`detmask`/`seg`, class =
  instance∩semantic majority vote, cv2-validated, deterministic split,
  images symlinked) and trains `yolo26m`/`yolo26m-seg` on the shared GPU
  server (`train.py`: crash-resumable via `--resume`, rolling last-5
  checkpoints via an `on_model_save` prune callback, `--amp false` required,
  `--extra k=v` passthrough; `train_supervised.sh` auto-restart supervisor;
  `run_probes.sh` timing-probe → epoch budget calculator; `clean_dataset.py`
  parallel cv2 repair tool; `env.sh` redirects all caches off the ~97%-full
  root disk onto the network drive; `setup_server.sh` provisions the venv
  reusing the server's system Blackwell torch). Trained a 18-class part
  detector+segmenter: `parts_detmask_v1` (mAP50 0.99/recall 0.99) and
  `parts_seg_v1` (0.984 box/0.966 mask); an earlier `parts_det_v1` trained on
  the sparse `bbox_2d` annotator (mAP50 0.64/recall 0.56) was retired.
  `deploy_yolo_weights.sh` deployed `parts_detmask_v1/weights/best.pt` to the
  GPU server's `wbk-perception` container (`YOLO_WEIGHTS` mount, container
  recreated with the same image/ports/GPU device, health-checked). Discovered
  along the way: `wbk-perception`'s bundled `sam3` process fails to load on
  this server (not root-caused) — SAM3 is served instead by a second,
  standalone `wbk-sam3` container on the GPU-server deployment only (local
  single-host `docker-compose.yml` is unaffected). The perception stage is
  now reachable from a local orchestrator via `ssh -N gpu-server` (tunnels
  `18001-18005`→`6767-6769`/`8004`/`8005`, `6006`→`6772` for TensorBoard) plus
  `docker compose -f docker-compose.yml -f docker-compose.remote-gpu.yml up
  -d orchestrator dashboard damage`. Added `System/training.md` (architecture
  of the whole training pipeline — converter task modes, trainer flags,
  server env quirks, deployment script, current results table). Added
  `Decisions/0012-mask-derived-detection-labels.md` (ADR: `--task detmask`
  over `--task det` — the `bbox_2d` annotator under-tags prims, ~2.8x fewer
  boxes than the mask-derived count, and the recall gap tracked it exactly)
  and `Decisions/0013-amp-disabled-blackwell-training.md` (ADR: AMP off is a
  documented convention, not a code default, on the RTX PRO 6000 Blackwell +
  torch 2.12 training stack — validation crashes with AMP on). Extended
  `Decisions/0001-perception-shared-container-pose-split-containers.md` with
  an "Update" note on the `wbk-sam3` workaround (deployment reality, not a
  reversal of the one-shared-container decision). Rewrote
  `SOP/deploy_perception_gpu_server.md` end to end: status flipped from "in
  progress" to "deployed and running", added the two-container
  (`wbk-perception`/`wbk-sam3`) topology table, the actual tunnel port map,
  the `docker-compose.remote-gpu.yml` local-side bring-up command, and the
  weight-deployment procedure (cross-linked to `System/training.md`).
  Extended `System/architecture.md`: Related Docs gained `System/training.md`
  and both new ADRs; Stage 1 Perception section now states the `yolo`
  service serves the custom-trained `parts_detmask.pt` (not the stock
  default) and that the GPU-server deployment is live, not pending; the
  "Not yet built" YOLO-tuning bullet rewritten to "trained and deployed" (the
  orchestrator's separate mock-`next_part` path for dry-runs/tests is
  unaffected and called out explicitly so the two aren't conflated). Updated
  `README.md`'s System, Decisions, and SOP indices for all of the above. Not
  covered by this update (pre-existing, unrelated in-flight work already
  present in the working tree at capture time — see the entry immediately
  below): the ERP/LLM planning head and the `ROBOT_TARGET` real/sim/both
  Isaac-Sim integration.
- 2026-07-08 — The ERP-driven, LLM-orchestrated disassembly vision
  (previously `Tasks/active/llm_orchestrated_disassembly_plan.md`, "vision
  captured, not yet scoped") is now **implemented** (working tree at capture
  time, not yet committed): 204 pytest tests green (24 new in
  `tests/orchestrator/test_plan.py`), 30 frontend Vitest tests green (4 new
  in `derive.test.ts`), `npm run build` clean. Summary: `orchestrator/models.py`
  gained `Plan`/`PlanStep`/`ArmAction`; `orchestrator/clients/base.py` gained
  `PlanProvider`/`ActionSynthesizer` Protocols and
  `PerceptionClient.locate()`; `orchestrator/loop.py`'s `run(product=None)`
  dispatches to `_run_fixed()` (unchanged original behavior) or
  `_run_planned(product)` (new — plan-driven, perception shifts from
  sequencer to grounder/verifier, a step whose part isn't in the scene SKIPs,
  a step that can't be grasped BLOCKS the run); new `PLAN_GENERATED`/`STEP`/
  `GUARDRAIL` `LoopEvent` states. Planning head:
  `orchestrator/data/erp_products.json` (mock ERP, ships in the image),
  `StaticPlanProvider` (`clients/erp.py`, stdlib-only ERP order) and
  `LlmPlanProvider` (`clients/llm_planner.py`, OpenRouter re-ordering,
  permutation-guardrailed, falls back to static on any error);
  `PLANNER_MODE=auto|llm|static`. Action synthesis (the safety-critical
  piece): `orchestrator/actions.py`'s constrained vocabulary (`move_to_pose`
  by `pose_ref` only — never coordinates; `move_named` restricted to
  `home`/`clearance` in grasp context; `gripper` open/close) with
  `validate_actions()` rejecting any violation before a `MovementClient` call
  and `scripted_grasp_sequence()` (identical to the pre-existing loop motion)
  as the fallback; `ACTION_SYNTHESIS=scripted|llm`, opt-in, `scripted` is the
  default (no LLM in the motion path at all).
  `orchestrator/clients/openrouter.py` is a new shared LLM-provider wrapper
  (mirrors `damage/client.py`'s pattern deliberately — provider reuse, not a
  second integration) used by both the planner and the action synthesizer.
  New endpoints `GET /products` and `GET /plan`; `product` param added to
  `POST /run` and `GET /events/run`. Frontend: `ProductSelector` (product
  dropdown from `GET /products`) and `PlanProgress` (live plan checklist
  derived from `derivePlan()` in `lib/derive.ts`) components; new
  `LoopState`s threaded through `types.ts`/`stages.ts`; `product` param
  threaded through `lib/api.ts`/`useRunStream`/`runContext`. Added
  `Decisions/0011-llm-action-selector-constrained-vocabulary.md` (ADR: why
  the action-synthesis LLM is a selector over a small fixed vocabulary, never
  a free-form command generator; alternatives considered and rejected —
  free-form matrices, schema-only validation without pose indirection; the
  ADR 0010 movement-adapter gap remains the reason plan-driven runs still
  can't drive the **real** arm, only sim/mocks). Moved
  `Tasks/active/llm_orchestrated_disassembly_plan.md` to
  `Tasks/archive/llm_orchestrated_disassembly_plan.md`, rewritten with status
  "implemented" and all four PRD open questions resolved (1: reuse
  OpenRouter; 2: mock ERP as static JSON behind `PlanProvider`; 3:
  constrained vocabulary per ADR 0011; 4: the plan replaces the sequencer
  only — `LOCATE`/`POSE`/`INSPECT`/`SORT` machinery is unchanged between
  modes) plus the still-open ADR 0010 prerequisite noted explicitly. Extended
  `System/orchestrator.md`: new "Two loop modes" / "Plan mode" sections
  (loop diagram, planning head, constrained vocabulary, `clients/openrouter.py`),
  Protocol seam table (`PlanProvider`/`ActionSynthesizer` rows,
  `PerceptionClient.locate`), mocks list (`MockPlanProvider`/
  `MockActionSynthesizer`), Config table (6 new planning-head fields), Entry
  points (`/products`, `/plan`, `product` param), Data model (`Plan`/
  `PlanStep`/`ArmAction`), Tests section (`test_plan.py`, count 105 → 204).
  Extended `System/architecture.md`: pipeline diagram gained the planning
  head, stage table gained a Planning head row, "Not yet built" section
  clarified the planning-head vision is now shipped (distinct from the
  still-unimplemented "two future VLM roles") and real-ERP-vs-mock is
  explicitly out of scope, Test suite section counts updated (105 → 204
  pytest, 26 → 30 Vitest). Extended `System/dashboard.md`: new "Plan mode
  UI" section (`ProductSelector`, `PlanProgress`, `derivePlan`), pages table,
  components list, stage-mapping section (new states), test suite section
  (30 tests, `derivePlan` coverage). Added ADR 0011 and the archived PRD to
  `README.md`'s indices; updated the `System/orchestrator.md` one-liner. Not
  covered by this update (explicitly out of scope — a separate, unrelated
  in-flight feature also present in the working tree): the `ROBOT_TARGET`
  real/sim/both robot selection, `TeeMovement`, `IsaacSimMovement`,
  `contracts/simulation_api.md`/`sim_scene_capture.md`, and the frontend's
  `SceneView`/`SourceToggle`/`PartSelector`/`lib/parts.ts` — these touch the
  same files (`config.py`, `factory.py`, `app.py`, `loop.py`) but are a
  distinct capability; document them in a separate pass when that work is
  ready to capture.
- 2026-07-08 — Captured a team vision for a head-of-pipeline + closer-of-loop
  extension: an operator selects a part in an ERP system, an LLM generates an
  ordered disassembly plan from the ERP data, the orchestrator executes the
  plan step by step (querying the existing perception/pose endpoints per
  step), an LLM synthesizes arm command(s) per step from the step's
  instruction + the part's 6DoF pose + the movement-API documentation, and
  (as today) a post-removal VLM fault check sorts each part into an OK or
  reject bin. No code exists yet — this is vision only. Added
  `Tasks/active/llm_orchestrated_disassembly_plan.md`: maps each of the four
  articulated pieces onto current architecture (perception/pose queries and
  the damage-VLM OK/reject sort are largely already built and reusable;
  ERP-selection + plan-generation, and the runtime LLM command-synthesis
  step that would replace the orchestrator's hardcoded `PLAN`/`GRASP`
  sequencing, are wholly new) and records four explicitly open questions
  without answering them: LLM/provider choice, ERP mock-vs-real scope,
  guardrails on LLM-generated movement commands before they reach a real
  robot arm (flagged safety-critical), and how plan steps map onto the
  orchestrator's existing `LoopEvent` state model and SSE narration. No
  implementation detail invented beyond what was stated. Added the new PRD
  to `README.md`'s Tasks index (previously "no in-flight PRDs yet").
- 2026-07-08 — Operational lesson from tonight's Jetson deployment (no code
  changed; ops knowledge only). `robot_control` and `scene_camera` were
  deployed to the lab's Jetson (`lara5@172.22.192.166`, ssh alias `jetson`)
  via a native `python3 -m venv` + `nohup` path, **not** the documented
  `deploy/robot-control/docker-compose.yml` path — that path is blocked on
  this device by two infra gaps: (1) `.github/workflows/publish-images.yml`'s
  `docker/build-push-action@v6` step has no `platforms:` key, so the
  published GHCR image is amd64-only while the Jetson is arm64; (2) the
  `lara5` account has no docker-group membership and no passwordless sudo,
  so `docker compose` can't run under it at all. Added
  `SOP/deploy_jetson_native.md`: the working clone→venv→nohup procedure for
  both services, the `scene_camera` `--system-site-packages` requirement
  (reuses the system Zivid SDK 2.17.1 bindings) plus its `numpy<2` +
  `opencv-python-headless<5` pin (opencv 4.11 + numpy 1.26.4 verified
  working — opencv≥5 needs numpy≥2, conflicting with the Zivid/nptyping
  stack's numpy 1.x requirement), the `python -m uvicorn` invocation needed
  because a `--system-site-packages` venv doesn't get its own `uvicorn`
  entry point, the update (`git pull --ff-only` + kill/re-nohup) procedure,
  and current limitations (no process supervision/no reboot survival, the
  LARA5 robot socket server was not running at deploy time so
  `/robot/probe` returned `Errno 111`, `WBK_API_TOKEN` unset so auth is
  off, shared-device etiquette). Also lists what closing both infra gaps
  above would take, for whoever revisits the compose path later. Extended
  `System/robot_control.md`: new "Current on-device status (2026-07-08)"
  subsection under "Deployment" stating the compose path is not what's
  actually running, with a link to the new SOP; added the SOP to Related
  Docs. Added the new SOP to `README.md`'s SOP index.
- 2026-07-07 — `robot_control/` (Group 2's Jetson movement bridge) documented
  as the repo's **movement** stage (commits `604733a` "Merge robot_control
  service from robot_control branch (Group 2)", `361fe9a` "Wire robot_control
  into the containerized microservices architecture", `4e5213d` "docs:
  document robot_control (movement) service in README + deploy guide"). Added
  `System/robot_control.md`: the TCP-socket bridge to the LARA5/NEURA robot
  socket server (`ROBOT_HOST:ROBOT_PORT`, default `127.0.0.1:65432`,
  JSON `{function,args,kwargs}` protocol via `robot_socket_client`); the four
  routers (`commands`, `robot_commands` with its `READ_COMMANDS`/`MOTION_COMMANDS`
  allow-list, `robot_workflows`, `joint_states`); hover planning's five
  lettered safety gates (A confidence, B/D workspace box, C calibration
  residuals, F max TCP jump) and the `confirmation=="yes"` exact-match gate
  on `/robot/hover/execute`; the Umeyama-rigid world↔base calibration solve
  and its `session.json`/`base_world.json` artifacts (a separate calibration
  from the orchestrator's own eye-to-hand `T_base_cam`, ADR 0006); the full
  `app/env.py` config table; deployment (Dockerfile pinned to port `9000` to
  match `MOVEMENT_URL`, dev compose entry, standalone `deploy/robot-control/`
  with `network_mode: host` to run **on** the Jetson, the GHCR publish-images
  CI matrix entry). Added `Decisions/0010-robot-control-integration.md` (ADR:
  why only `robot_control/` was cherry-picked from the external branch; the
  vendored `RobotCommand` in `app/schemas.py` replacing the out-of-repo
  `shared.jetson` import and why that was preferred over pulling in more
  branch content; why the container is pinned to port `9000` instead of the
  code's own `8000` default; adding `app/auth.py` as a fifth copy of the
  ADR-0009 shared-token pattern, since the merged branch had no auth of its
  own; and the **open gap** — `HttpMovement` still speaks the draft
  `contracts/movement_api.md` shape and cannot drive this service yet,
  because the robot's `[x,y,z,rx,ry,rz]` + `tool_down_rpy` pose convention
  vs. the orchestrator's 4x4 `base_T_grasp` matrices is unconfirmed and must
  not be guessed since it drives real robot motion). Extended
  `System/architecture.md`: pipeline diagram, stage table's Movement row
  (now "service built + deployed, adapter TODO" instead of pure external
  placeholder), the paragraph below the table, and the "Not yet built"
  section (split the old combined "movement + grip" bullet into a
  service-landed movement-adapter bullet and a still-fully-external
  grip-sensor bullet); added `System/robot_control.md` and ADR 0010 to
  Related Docs. Extended `System/orchestrator.md`: "Teammate-owned contracts"
  section rewritten to reflect the movement service landing (`robot_control/`
  is a real FastAPI app over a TCP-socket robot connection, not a NeuraPy-
  wrapping REST service as originally guessed; its actual routes vs. the
  draft contract), added `System/robot_control.md`/ADR 0010 to Related Docs.
  Added both new docs to `README.md`'s System and Decisions indices. (Root
  `README.md`/`deploy/README.md` were updated by the calling task directly,
  commit `4e5213d` — not duplicated here; see those files.)
- 2026-07-07 — Remote GPU-server deployment of perception documented as
  **in progress** (commit `5fbacdf`, "perception: parametrize base image via
  BASE_IMAGE build-arg", plus uncommitted `perception/README.md` additions
  at the time of this doc update). Added
  `SOP/deploy_perception_gpu_server.md`: the `ARG BASE_IMAGE` override
  needed for Blackwell GPUs (sm_120, e.g. RTX PRO 6000 →
  `pytorch/pytorch:2.8.0-cuda12.8-cudnn9-devel`, verified `torch
  2.8.0+cu128`/`transformers 4.57.1`/`ultralytics 8.4.90`), why
  `requirements.txt` omits torch, the rsync-instead-of-redownload weights
  recipe for a server with no HF auth (gated SAM 3 + LocateAnything-3B),
  running the container bound to `127.0.0.1:6767-6769` on the server, and
  the SSH port-forward tunnel (`-L 8001:localhost:6767` etc.) that lets the
  orchestrator's existing `PERCEPTION_*_URL` defaults
  (`http://localhost:800{1,2,3}`) keep working unchanged. Documented the
  intended split — orchestrator + damage + dashboard local, perception +
  pose on the GPU server — and the shared-Docker-daemon
  no-isolation-from-co-tenants caveat (secrets stay off the box). Explicitly
  flagged as **not yet a working deployment**: image built + weights
  rsync'ing, container not yet started, tunnel not yet established, pose not
  started. Extended `System/architecture.md`'s Stage 1 Perception section
  with the `ARG BASE_IMAGE` parametrization and a link to the new SOP (also
  added to that doc's Related Docs). Extended
  `SOP/running_services.md`'s perception section with the Blackwell
  build-arg override and a pointer to the new SOP (also added to its
  Related Docs). Added the new SOP to `README.md`'s SOP index, marked
  in-progress.
- 2026-07-07 — Shared-token auth (`WBK_API_TOKEN`) documented as **implemented**
  (commit `749b179`, "feat(auth): shared-token gate on work + robot
  endpoints") — previously only anticipated as a gap in ADR 0008's
  "Consequences". Added `Decisions/0009-shared-token-auth.md` (ADR: optional
  bearer token via a `require_token` FastAPI dependency copy-pasted into
  each of the four deployable packages — `perception/services/shared/auth.py`,
  `pose/shared/auth.py`, `damage/auth.py`, `orchestrator/auth.py` —
  unset-token = disabled; protects perception `POST /infer`, pose `POST
  /pose`, damage `POST /inspect`, orchestrator `POST /run`/`GET /events/run`;
  `GET /health` always open; header or `?token=` query transport, the latter
  for browser `EventSource`; alternatives rejected — CORS as a control, IP
  allowlisting, a real OAuth/JWT system; explicit **trusted-LAN-only** caveat
  — blocks network-only outsiders, not same-host co-tenants who can read the
  token from env/`.env`/`docker inspect`/`/proc`, nor a browser-embedded
  token visible in devtools; mitigation is service placement, revisited
  later). Extended `System/integration_points.md`: new auth bullet in the
  shared design-conventions list, a token-requirement note under each of
  Contracts 1–3, and the SSE contract's `?token=` transport explained under
  Contract 4. Extended `System/orchestrator.md`: new "Auth" section
  (`orchestrator/auth.py` enforces on `/run`+`/events/run`;
  `OrchestratorConfig.auth_headers` attaches the same token to
  `HttpPerception`/`HttpPose`/`HttpDamage`, explicitly **not**
  `HttpMovement`/`HttpGrip`); entry-point bullets and the Tests section
  updated. Extended `System/dashboard.md`: new "Auth token" section for the
  `apiToken` runtime-config field (`lib/api.ts`'s `authHeaders()` vs.
  `runStreamUrl()`'s `?token=`), Settings-page table row, and the Test suite
  paragraph. Updated Python test count 86 → 105 everywhere it was cited
  (`System/architecture.md`, `System/orchestrator.md`,
  `SOP/running_tests.md`, incl. the previously-stale "81 tests" in that
  SOP's `uv run pytest` comment) and added the new `test_auth.py` files (4
  each in `tests/{perception,pose,damage}/`, 7 in `tests/orchestrator/`) —
  plus a previously-missing `tests/orchestrator/` block — to
  `SOP/running_tests.md`'s Layout tree. Updated frontend test count 23 → 26
  everywhere it was cited (`System/architecture.md`, `System/dashboard.md`)
  for the new `frontend/src/lib/api.test.ts`. Added a `WBK_API_TOKEN` auth
  note (curl `-H` flag, opt-in default) to `SOP/running_services.md`. Added
  ADR 0009 to the `README.md` index and to the Related-Docs cross-links in
  `System/architecture.md`, `System/integration_points.md`,
  `System/orchestrator.md`, `System/dashboard.md`, and
  `SOP/running_services.md`/`SOP/running_tests.md`.
- 2026-07-07 — Correction: frontend now has a test suite. A Vitest unit
  suite landed in `frontend/` (`npm test` → `vitest run`, jsdom env,
  `frontend/vitest.config.ts`, `src/**/*.test.ts` — 23 tests across 3 files,
  all passing), and the event-reducer logic was extracted from components
  into pure functions in `frontend/src/lib/derive.ts` (`tallyBins`,
  `deriveInspections`, `deriveGrip`, `currentPart`) specifically to make it
  testable without rendering; `BinTally`/`GripTelemetry`/`InspectionPage`/
  `DashboardPage` now consume those. `.github/workflows/tests.yml`'s
  `frontend` job now runs `npm test` before `npm run build`, so unit tests +
  type-check + build all gate every push/PR (the `pytest` job is unchanged
  at 86 tests). Updated `System/architecture.md`'s "Test suite" section
  (previously said the frontend had no test framework and wasn't in CI —
  both now false) and `System/dashboard.md` (previously said "no test
  framework installed"; replaced with a new "Test suite" section detailing
  the Vitest setup, what each of the 3 test files covers, and the
  `lib/derive.ts` pure-reducer extraction). No README index changes needed —
  the existing one-liners for those two docs were generic and didn't assert
  the missing-test-framework state.
- 2026-07-07 — Dashboard (`frontend/`) and the orchestrator's SSE live-run
  endpoint documented (uncommitted working-tree changes as of this doc
  update: new `frontend/` tree, modified `orchestrator/app.py`,
  `docker-compose.yml`, root `README.md`). Added `System/dashboard.md`
  (React 19 + Vite 6 + TS + Tailwind v4 static SPA; the four pages; the
  four-layer runtime endpoint config `localStorage > config.json > VITE_* >
  localhost` in `frontend/src/config/runtime.ts`; `useRunStream`'s SSE
  consumption and the must-close-on-`end` gotcha; deployment via
  `frontend/Dockerfile` + nginx + the `dashboard` compose service; no test
  framework installed, `npm run build` is the only current gate and it is
  not in CI). Added `Decisions/0008-frontend-separate-static-app.md` (ADR:
  the dashboard is a separate static app, not served by the orchestrator —
  headless/CI-testable control plane vs. re-pointable-per-host browser app;
  the only coupling is the read-only `GET /events/run` SSE stream; CORS
  consequence). Extended `System/orchestrator.md` ("Entry points"): new
  `GET /events/run?dry_run=<bool>&delay=<seconds>` SSE endpoint (worker
  thread + `queue.Queue` bridging into an async generator, frame sequence,
  `delay` pacing) and the new permissive CORS middleware, both cross-linked
  to ADR 0008. Extended `System/integration_points.md`: new "Contract 4 —
  Orchestrator live loop `GET /events/run` (SSE)" section (full frame-type
  table, the close-on-`end` consumer contract, the CORS note). Updated
  `System/architecture.md`: pipeline diagram gained the dashboard as a
  read-only SSE observer, stage table gained a `Dashboard (UI)` row
  (`frontend/`, `:5173`, nginx), and the Test suite section now notes the
  86-pytest count is Python-only (`frontend/` has no test framework; `npm
  run build` is clean but not wired into `.github/workflows/tests.yml`).
  Updated `README.md`'s `System/integration_points.md` and
  `System/orchestrator.md` lines, added the `System/dashboard.md` and
  `Decisions/0008` lines. (Root-level `README.md`/`docker-compose.yml`
  changes were made by the calling task directly and are not duplicated
  here — see repo-root `README.md`.)
- 2026-07-07 — Movement/grip REST approach confirmed by hardware teammate:
  the Jetson-side interface will be an HTTP-adapter microservice wrapping
  NeuraPy (NEURA's Python SDK), to be uploaded to the repo shortly. This
  resolves an earlier doubt (Jetson controller found running NeuraPy with no
  REST API, only a read-only joint-state TCP publisher on `:5005` + a
  localhost MJPEG stream) about whether the existing `HttpMovement`/
  `HttpGrip` clients and `contracts/movement_api.md`/`contracts/grip_api.md`
  were the right shape — they are, and will be aligned to the adapter's real
  routes once it lands. Updated `System/orchestrator.md` ("Teammate-owned
  contracts" section) and `Decisions/0005-mock-first-interface-seam-integration.md`
  (new "Update" consequence bullet). No new files; `README.md` unchanged.
- 2026-07-07 — Hand-eye calibration seam + motor-current grip sensing documented (commits `6994503` "Prep hand-eye calibration seam in the grasp chain", `e0a1b13` "Update grip contract for motor-current sensing"). Extended `System/orchestrator.md`: new "Hand-eye calibration & the grasp chain" section (the `base_T_grasp = T_base_cam @ cam_T_obj @ obj_T_grasp` SE(3) composition, `T_base_cam`/`obj_T_grasp`/`grasp_approach_dist` config fields, mm→m unit conversion via `_load_matrix()`); updated "Config" summary; updated the "Teammate-owned contracts" bullets for `grip_api.md` (now motor-current-based: `grasped`+`current`+`width`) and `movement_api.md` (`/gripper` close must block until stall); updated "Two future VLM roles" item 2 (grip sensor is now analog, not binary, ahead of the deferred VLM check); added a one-line note in the loop diagram's GRASP step. Added `Decisions/0006-eye-to-hand-static-calibration.md` (ADR: eye-to-hand → single static `T_base_cam`, never recomposed per frame; `obj_T_grasp` separates object pose from grasp point; explicit mm/m unit handling; identity defaults are deliberately wrong, not safe). Added `Decisions/0007-grip-motor-current-sensing.md` (ADR: motor current over a binary pad; the end-stop false-positive pitfall and its width-based disambiguation; steady-state read timing; no `loop.py`/Protocol changes needed). Updated `README.md`'s `System/orchestrator.md` line and added the two new ADR lines.
- 2026-07-07 — Orchestrator module documented (commit `3abc923`, "Add orchestrator (disassembly state machine) + integration contracts"). Added `System/orchestrator.md` (loop states, `_grasp_with_retry` rectify logic, the Protocol client seam, config, entry points, teammate-owned `contracts/`, the two not-yet-built VLM seams). Added `Decisions/0005-mock-first-interface-seam-integration.md` (ADR: build/demo the full loop against mocks now, swap real clients behind Protocols with no loop changes, as YOLO tuning/Jetson movement/grip sensor land). Added `SOP/running_orchestrator_dry_run.md` (`python -m orchestrator.dry_run`, running the orchestrator service, running just its tests). Updated `System/architecture.md`: pipeline diagram and service table now show the orchestrator plus grasp-planning (naive placeholder, built) and movement/grip (proposed contracts + real HTTP clients, external endpoints still teammate-owned/in-progress) instead of listing them as pure "future"; test count 81 → 86 (5 new orchestrator loop tests). Updated `README.md` and `SOP/running_services.md` with cross-links to the new docs.
- 2026-07-07 — Documentation initialized. Scanned `perception/`, `pose/`, `damage/`, `tests/`, `docker-compose.yml`, and `.github/workflows/tests.yml` at commit `7cf5211`. Created `System/architecture.md`, `System/integration_points.md`, four ADRs in `Decisions/` (perception-vs-pose containerization, perception model stack, damage fail-safe sort policy, pose contract reuse from KIP `kip-pose-viewer`), and two runbooks in `SOP/` (running the services, running the tests). No `Tasks/active` or `Tasks/archive` entries yet — no PRDs exist in the repo at this point.
