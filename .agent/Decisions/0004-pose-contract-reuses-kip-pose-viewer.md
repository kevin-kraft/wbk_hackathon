# ADR 0004: Pose wire contract reuses the KIP `kip-pose-viewer` reference

## Related Docs
- [Architecture](../System/architecture.md) — pose stage detail
- [Integration Points](../System/integration_points.md) — full `/pose` contract spec
- [ADR: perception shared container vs. pose split containers](./0001-perception-shared-container-pose-split-containers.md)

## Status
Accepted (as scaffolded, 2026-07-07 — commit `82a88f9`).

## Context

Both `foundationpose_svc` and `gigapose_svc` need a `POST /pose` request and
response shape. There was an existing reference implementation to draw on: a
prior project at `~/code/kip-pose-viewer` (outside this repo) which already
wraps FoundationPose and GigaPose behind FastAPI services with a working
`/pose` contract.

## Decision

`pose/shared/schemas.py`'s `PoseRequest`/`PoseInstance`/`ObjectPose`/
`PoseResponse`/`PoseHealth` are **deliberately identical** to the KIP
`kip-pose-viewer` `/pose` contract — same field names (`rgb_b64`, `depth_b64`,
`K` as flat 9 row-major, `instances[{id,class,mask_b64}]`), same output shape
(`T_cam_obj` as a 4x4 row-major OpenCV-frame metres transform, plus optional
`score`/`stage`), same GigaPose-only knobs (`hypotheses`, `pipeline`,
`kabsch`). This is stated directly in both `pose/README.md` ("mirrors the
reference implementation in `~/code/kip-pose-viewer`") and in the schema
module docstring itself.

## Why

Reusing a contract that already has two working implementations behind it
(KIP's own FoundationPose and GigaPose wrappers) meant this repo's pose stage
could be scaffolded quickly against a shape already proven to fit both
estimators' quirks (e.g. FoundationPose requiring depth, GigaPose's
rgb-vs-rgbd pipeline switch and optional Kabsch depth-alignment tail). It also
means a future orchestration gateway that fans a request out to either
estimator can treat them as drop-in interchangeable — the whole point of
having two alternative pose estimators in the first place (ADR 0001) only pays
off if callers don't have to special-case the request/response shape per
backend.

## Consequences

- Any change to `pose/shared/schemas.py` should be treated as a **breaking
  change against the KIP reference contract**, not just an internal API
  tweak — if this pipeline and `kip-pose-viewer` are ever meant to stay
  interoperable (e.g. sharing a gateway, or porting fixes between the two
  repos), schema drift here defeats that.
- The Dockerfiles (`pose/foundationpose_svc/Dockerfile`,
  `pose/gigapose_svc/Dockerfile`) also mirror the KIP pattern of building on
  top of pre-built, model-repo-specific GPU base images rather than
  reinventing the CUDA/torch/nvdiffrast/pytorch3d (FoundationPose) or
  xformers/panda3d/MegaPose (GigaPose) build steps — see
  [SOP: running the services](../SOP/running_services.md) for the exact
  build commands.
- Per-object setup (CAD meshes for both; 162 pre-rendered templates per object
  for GigaPose) is a KIP convention this repo inherits as-is — the reference
  hardcodes two demo parts, and this repo's real disassembly objects still
  need that same per-object asset pipeline run before the services will
  produce correct poses for them.
