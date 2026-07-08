"""DDS cloud-API adapter — IDEA Research / DeepDataSpace open-world detectors.

One proxy fronting four cloud models behind a single ``/infer`` so they can be
A/B'd against the local YOLO / SAM3 / LocateAnything stack on the same frames:

  * ``DINO-X-1.0``            (``/v2/task/dinox/detection``)         text · universal · visual · bbox+mask
  * ``DINO-XSeek-1.0``        (``/v2/task/dino_xseek/detection``)    long/referring text · bbox
  * ``GroundingDino-1.6-Pro`` (``/v2/task/grounding_dino/detection``) text · bbox
  * ``T-Rex-2.0``             (``/v2/task/trex/detection``)          visual prompt (reference box) · bbox

These are NETWORK calls, not local weights: no GPU, no HF cache. ``load()`` just
builds the client from ``DDS_API_TOKEN``. Only DINO-X returns masks (``coco_rle``);
the others return boxes only — feed those boxes to SAM3 for a mask if needed.

The SDK's ``create_task_with_local_image_auto_resize`` resizes the target image
to each endpoint's max edge AND un-scales bbox/mask back to the original image's
pixel coordinates, so every result is in the input frame's coordinate space —
directly comparable with the other perception services.
"""

from __future__ import annotations

import base64
import io
import time

from ..shared.imaging import encode_mask_png_b64
from ..shared.model_base import BasePerceptionModel
from ..shared.schemas import BBox, DdsDetection, DdsRequest, DdsResponse

# model id -> DDS V2 endpoint
_ENDPOINTS = {
    "DINO-X-1.0": "/v2/task/dinox/detection",
    "DINO-XSeek-1.0": "/v2/task/dino_xseek/detection",
    "GroundingDino-1.6-Pro": "/v2/task/grounding_dino/detection",
    "T-Rex-2.0": "/v2/task/trex/detection",
}
_SUPPORTS_TEXT = {"DINO-X-1.0", "DINO-XSeek-1.0", "GroundingDino-1.6-Pro"}
_SUPPORTS_VISUAL = {"DINO-X-1.0", "T-Rex-2.0"}
_SUPPORTS_UNIVERSAL = {"DINO-X-1.0"}
_SUPPORTS_MASK = {"DINO-X-1.0"}

# Reference images for visual prompts are capped at the strictest endpoint limit
# (T-Rex2 = 1333px longest edge). Rects are scaled to match.
_REF_MAX_EDGE = 1333


class DdsBackend(BasePerceptionModel):
    name = "dds"

    def load(self) -> None:
        # No weights — just a client. Import lives here (not top-level) so tests
        # and the token-less dev path never need the SDK installed.
        self._device = "cloud"
        token = self.settings.dds_api_token
        if not token:
            # Start anyway so /health is reachable; /infer will 400 until a
            # token is set. (Do not import the SDK on this path.)
            self._loaded = False
            return
        from dds_cloudapi_sdk import Client, Config

        config = Config(token)
        if self.settings.dds_endpoint:
            config.endpoint = self.settings.dds_endpoint
        self._client = Client(config)
        self._loaded = True

    # ------------------------------------------------------------------ #
    def infer(self, req: DdsRequest) -> DdsResponse:
        if not self._loaded:
            raise RuntimeError(
                "DDS_API_TOKEN is not set — cannot reach the DeepDataSpace cloud API. "
                "Get a token at https://cloud.deepdataspace.com and set DDS_API_TOKEN."
            )

        model = req.model or self.settings.dds_default_model
        if model not in _ENDPOINTS:
            raise ValueError(f"unknown DDS model {model!r}; choose one of {sorted(_ENDPOINTS)}")
        api_path = _ENDPOINTS[model]

        want_mask = bool(req.return_mask) and model in _SUPPORTS_MASK
        api_body: dict = {
            "model": model,
            "prompt": self._build_prompt(req, model),  # validates modality vs model
            "targets": ["bbox", "mask"] if want_mask else ["bbox"],
        }
        if want_mask:
            api_body["mask_format"] = "coco_rle"
        # bbox/iou thresholds apply to the DINO family; the T-Rex visual endpoint
        # ignores them (harmless to omit).
        if model != "T-Rex-2.0":
            api_body["bbox_threshold"] = req.bbox_threshold
            api_body["iou_threshold"] = req.iou_threshold

        img_bytes, width, height = self._decode(req.image_b64)

        # SDK import lives here — after cheap validation — so bad-request paths
        # (unknown model, wrong prompt modality) never require the SDK installed.
        from dds_cloudapi_sdk.tasks.v2_task import create_task_with_local_image_auto_resize

        # image_path accepts bytes/BytesIO; the helper resizes the target frame to
        # the endpoint max edge and un-scales results to original coordinates.
        task = create_task_with_local_image_auto_resize(
            api_path=api_path,
            api_body_without_image=api_body,
            image_path=img_bytes,
        )

        t0 = time.perf_counter()
        self._client.run_task(task)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        objects = (task.result or {}).get("objects", []) or []
        detections = self._to_detections(objects, want_mask)
        if req.top_k:
            detections.sort(key=lambda d: d.score, reverse=True)
            detections = detections[: req.top_k]

        return DdsResponse(
            detections=detections,
            width=width,
            height=height,
            model=model,
            api_path=api_path,
            inference_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------ #
    def _build_prompt(self, req: DdsRequest, model: str) -> dict:
        if req.visual_prompts:
            if model not in _SUPPORTS_VISUAL:
                raise ValueError(
                    f"{model} does not accept visual prompts — use DINO-X-1.0 or T-Rex-2.0"
                )
            return {"type": "visual_images", "visual_images": self._build_visual_images(req)}
        if req.prompt_free:
            if model not in _SUPPORTS_UNIVERSAL:
                raise ValueError(f"prompt-free (universal) mode is DINO-X-1.0 only, not {model}")
            return {"type": "universal"}
        if req.text:
            if model not in _SUPPORTS_TEXT:
                raise ValueError(f"{model} does not accept text prompts — give it a visual prompt")
            return {"type": "text", "text": req.text}
        raise ValueError("request needs one of: text, visual_prompts, or prompt_free=true")

    def _build_visual_images(self, req: DdsRequest) -> list[dict]:
        from dds_cloudapi_sdk.image_resizer import image_to_base64, resize_image

        # Group interactions by their reference image (None => the main frame),
        # so one reference image => one `visual_images` entry with all its rects.
        groups: dict[str, dict] = {}
        for vp in req.visual_prompts or []:
            key = vp.reference_image_b64 or "__main__"
            if key not in groups:
                src = self._decode(vp.reference_image_b64 or req.image_b64)[0]
                groups[key] = {"src": src, "prompts": []}
            groups[key]["prompts"].append(vp)

        visual_images: list[dict] = []
        for g in groups.values():
            resized, info = resize_image(g["src"], _REF_MAX_EDGE)
            ratio = info["ratio"] if info else 1.0
            interactions = [
                {
                    "type": "rect",
                    "category_id": vp.category_id,
                    "rect": [
                        vp.rect.x1 * ratio,
                        vp.rect.y1 * ratio,
                        vp.rect.x2 * ratio,
                        vp.rect.y2 * ratio,
                    ],
                }
                for vp in g["prompts"]
            ]
            visual_images.append({"image": image_to_base64(resized), "interactions": interactions})
        return visual_images

    # ------------------------------------------------------------------ #
    def _to_detections(self, objects: list, want_mask: bool) -> list[DdsDetection]:
        mask_utils = None
        if want_mask:
            import pycocotools.mask as mask_utils  # noqa: F401

        dets: list[DdsDetection] = []
        for obj in objects:
            bb = obj.get("bbox")
            if not bb or len(bb) < 4:
                continue
            box = BBox(x1=float(bb[0]), y1=float(bb[1]), x2=float(bb[2]), y2=float(bb[3]))
            mask_png = None
            m = obj.get("mask")
            if want_mask and m and mask_utils is not None:
                mask_png = self._encode_mask(m, mask_utils)
            dets.append(
                DdsDetection(
                    box=box,
                    score=float(obj.get("score", 0.0)),
                    category=str(obj.get("category", "")),
                    mask_b64_png=mask_png,
                )
            )
        return dets

    @staticmethod
    def _encode_mask(mask: dict, mask_utils) -> str:
        # coco_rle: {"counts": <str>, "size": [h, w], "format": "coco_rle"}.
        # pycocotools wants bytes counts; the API returns utf-8 str.
        rle = dict(mask)
        counts = rle.get("counts")
        if isinstance(counts, str):
            rle["counts"] = counts.encode("utf-8")
        arr = mask_utils.decode(rle)  # HxW uint8 {0,1}
        return encode_mask_png_b64(arr)  # binarizes to 0/255

    @staticmethod
    def _decode(image_b64: str) -> tuple[bytes, int, int]:
        """Base64 (optionally data-URI-prefixed) -> (raw bytes, width, height)."""
        from PIL import Image

        data = image_b64
        if data.strip().startswith("data:") and "," in data:
            data = data.split(",", 1)[1]
        raw = base64.b64decode(data)
        with Image.open(io.BytesIO(raw)) as im:
            w, h = im.size
        return raw, w, h
