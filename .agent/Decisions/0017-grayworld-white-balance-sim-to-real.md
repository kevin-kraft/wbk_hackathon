# ADR 0017: Gray-world white balance on the Zivid RGB + lowered detection confidence, as sim-to-real mitigations

## Related Docs
- [System: Architecture](../System/architecture.md) — Stage 1 Perception, the `yolo`/`yoloseg` closed-vocab detectors this fix targets
- [System: Training](../System/training.md) — the synthetic Isaac-Sim training domain these real captures are compared against
- [System: Robot Control](../System/robot_control.md) — where `scene_camera/` (the Zivid capture service this ADR's fix lives in) is deployed
- [System: Dashboard](../System/dashboard.md) — the Perception page's lowered default confidence and the SAM3/LocateAnything prompt fix
- [ADR 0012: mask-derived detection labels](./0012-mask-derived-detection-labels.md) — the training-side decision that produced the `parts_detmask`/`parts_seg` models this fix is trying to make usable on real frames
- [SOP: deploying perception to the GPU server](../SOP/deploy_perception_gpu_server.md) — where the fixed models are actually served from

## Status
Accepted (2026-07-08, commit `fcc2773`).

## Context

Debugging the live rig against the deployed `parts_detmask`/`parts_seg`
models (18-class, mAP50 0.99 on synthetic validation data — see
[ADR 0012](./0012-mask-derived-detection-labels.md)) surfaced a stark
sim-to-real gap: a real Zivid RGB capture returned **0 YOLO-Det boxes at the
0.25 default confidence threshold**, despite the same model scoring near-
perfect on synthetic renders. Two independent contributors were found:

1. **Color cast.** The Zivid camera's RGB output carries a strong green
   tint relative to the neutral, evenly-lit domain `training/isaac_to_yolo.py`
   renders (see [System: Training](../System/training.md)) — the models have
   never seen anything like it during training.
2. **Confidence miscalibration.** Even once color was closer to the training
   domain, the models' confidence on real frames sits well below their
   synthetic-validation scores — a well-known symptom of a train/test domain
   gap, not a bug in the detector itself.

## Decision

Two changes, shipped together as the highest-value fixes found this session:

1. **Gray-world white balance** on the Zivid RGB capture, in `scene_camera/`:
   `scene_camera/imaging.py:white_balance_grayworld()` computes per-channel
   means over non-black/non-saturated pixels (`5 < luminance < 250`, so
   no-return black and blown highlights don't skew the estimate; falls back
   to the unmodified image if fewer than 100 qualifying pixels exist), then
   scales each channel so its mean equals the average of all three —
   equalizing the color cast toward neutral gray. Gated by
   `SCENE_WHITE_BALANCE` (`scene_camera/config.py`, default `"grayworld"`,
   set `"off"` to disable) and only applied when `backend.name == "zivid"`
   (`scene_camera/app.py:capture()`) — the file/static dev backend is
   untouched. Verified end-to-end: channel means shifted from roughly
   R106/G109/B82 (green-cast) to R94/G92/B96 (neutral) on a captured frame;
   YOLO-Det went from 0 boxes at 0.25 conf to a `buerstenhalter_tray`
   detection at 0.93 conf on that frame, and from 0 boxes at 0.25 conf to 3
   boxes at 0.94/0.79 conf on a separate frame (per the commit message).
2. **Lowered the frontend's default detection confidence**, 0.25 → 0.10, for
   both `runYolo()` and `runYoloSeg()` (`frontend/src/lib/api.ts`) — a
   stopgap acknowledging that even color-corrected real frames still score
   lower than the training distribution. Backend request schemas
   (`perception/services/shared/schemas.py`) keep their own default of
   `0.25`/`0.2` unchanged; this is a frontend-only UX default, overridable
   per-request like any other `conf` value.

## Why

- **White balance is the highest-leverage, lowest-risk fix available today.**
  It needs no retraining, no new data, and no service redeploy beyond
  `scene_camera` itself — a few lines of numpy running once per capture. The
  durable fix for the sim-to-real gap is fine-tuning the detector on real
  labelled frames (not yet done — no real-frame dataset exists yet), but
  that's a training-pipeline effort with its own lead time; white balance
  closes most of the gap immediately.
- **Gray-world is robust enough for this rig without being over-engineered.**
  It assumes the *average* scene content is roughly neutral gray, which
  holds for this workbench (varied part colors, no single dominant hue
  filling the frame) — a more sophisticated per-scene or learned color-
  correction model was judged unnecessary complexity for what a 20-line
  channel-equalization function already fixes. The masking of near-black/
  near-saturated pixels before computing channel means is what keeps the
  gray-world assumption from breaking on this rig's mix of a dark background
  and reflective metal parts.
- **Lowering conf is a stopgap, not a fix, and is documented as such.** It
  trades false positives for recall on a model that is systematically
  under-confident on real data — acceptable for a demo where a human
  operator reviews detections, not something to carry into an unattended
  production pick. It was shipped alongside white balance (not instead of
  it) because even a color-corrected frame doesn't fully close the
  confidence gap.

Rejected alternatives:
- **Block on collecting and fine-tuning against real labelled frames before
  any real-rig demo** — rejected as a hackathon-timeline risk; white balance
  + a lower threshold gets real detections working today, and fine-tuning
  remains the documented durable fix for later.
- **A learned/adaptive white-balance model** — rejected as unnecessary
  complexity; gray-world is a single well-understood classical technique
  that measurably closed the gap on the first try.

## Consequences

- **`SCENE_WHITE_BALANCE=off` is the escape hatch** if gray-world ever
  produces a worse result on a different lighting setup or camera — no code
  change needed, just the env var.
- **The frontend's lower conf default (0.10) applies globally** to every
  YOLO-Det/YOLO-Seg call from the dashboard, not just this debugging session
  — expect more (and noisier) boxes/masks on the Perception page than the
  0.25 default would have shown. Both `runYolo()`/`runYoloSeg()` still
  accept a per-call `opts.conf` override.
- **This does not fix GigaPose/FoundationPose's own sim-to-real gap** (if
  any) — the fix is scoped to `scene_camera`'s RGB encode path, upstream of
  every consumer (YOLO, SAM3, LocateAnything, pose services), but pose
  estimation quality on real frames is a separate, unverified question.
- The real fix — fine-tuning on real labelled frames — remains open. This
  ADR's changes are explicitly a stopgap, not a replacement for that work.
