"""SAM 3 segmentation adapter (Meta, via HuggingFace transformers).

SAM 3 (released 2025-11) splits into two heads in the transformers integration:

* **Concept head** (`Sam3Model` / `Sam3Processor`) — text / noun-phrase prompt,
  returns masks for *all* matching instances at once (the SAM3 headline feature).
* **Tracker head** (`Sam3TrackerModel` / `Sam3TrackerProcessor`) — classic SAM
  point / box prompts.

Weights (`facebook/sam3`) are GATED on HuggingFace: request access, then
`hf auth login` (or set HF_TOKEN) before first run. Override the id via
SAM3_MODEL_ID.
"""

from __future__ import annotations

import time

from ..shared.imaging import decode_image_b64, encode_mask_png_b64
from ..shared.model_base import BasePerceptionModel
from ..shared.schemas import BBox, MaskResult, Sam3Request, Sam3Response

_DEFAULT_MODEL_ID = "facebook/sam3"


class Sam3Backend(BasePerceptionModel):
    name = "sam3"

    def load(self) -> None:
        import torch  # noqa: F401  (ensures torch present; device already resolved)
        from transformers import (
            Sam3Model,
            Sam3Processor,
            Sam3TrackerModel,
            Sam3TrackerProcessor,
        )

        device = self._resolve_device()
        model_id = self.settings.sam3_model_id or _DEFAULT_MODEL_ID
        # facebook/sam3 is gated; load from the pre-provisioned HF cache without
        # an online auth round-trip (see Settings.sam3_local_files_only).
        lfo = self.settings.sam3_local_files_only

        # Concept (text) head.
        self._concept = Sam3Model.from_pretrained(model_id, local_files_only=lfo).to(device)
        self._concept_proc = Sam3Processor.from_pretrained(model_id, local_files_only=lfo)
        # Tracker (point / box) head.
        self._tracker = Sam3TrackerModel.from_pretrained(model_id, local_files_only=lfo).to(device)
        self._tracker_proc = Sam3TrackerProcessor.from_pretrained(model_id, local_files_only=lfo)

        self._model_id = model_id
        self._loaded = True

    # ------------------------------------------------------------------ #
    def infer(self, req: Sam3Request) -> Sam3Response:
        import torch

        img = decode_image_b64(req.image_b64)
        t0 = time.perf_counter()

        if req.text:
            masks = self._infer_text(img, req.text)
        elif req.points or req.boxes:
            masks = self._infer_geometric(img, req)
        else:
            raise ValueError("Sam3Request needs one of: text, points, or boxes.")

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return Sam3Response(
            masks=masks,
            width=img.width,
            height=img.height,
            model=self._model_id,
            inference_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------ #
    def _infer_text(self, img, text: str) -> list[MaskResult]:
        import torch

        proc, model = self._concept_proc, self._concept
        inputs = proc(images=img, text=text, return_tensors="pt").to(self.device)
        with torch.no_grad():
            out = model(**inputs)
        results = proc.post_process_instance_segmentation(
            out,
            threshold=0.5,
            mask_threshold=0.5,
            target_sizes=inputs.get("original_sizes").tolist(),
        )[0]

        masks: list[MaskResult] = []
        boxes = results.get("boxes")
        scores = results.get("scores")
        for i, mask in enumerate(results["masks"]):
            box = None
            if boxes is not None and i < len(boxes):
                x1, y1, x2, y2 = [float(v) for v in boxes[i].tolist()]
                box = BBox(x1=x1, y1=y1, x2=x2, y2=y2)
            masks.append(
                MaskResult(
                    mask_b64_png=encode_mask_png_b64(mask.cpu().numpy()),
                    score=float(scores[i]) if scores is not None else 1.0,
                    box=box,
                    label=text,
                )
            )
        return masks

    def _infer_geometric(self, img, req: Sam3Request) -> list[MaskResult]:
        import torch

        proc, model = self._tracker_proc, self._tracker
        kwargs: dict = {"images": img, "return_tensors": "pt"}
        # Nesting convention: [batch][object][points][xy].
        if req.points:
            kwargs["input_points"] = [[[[p.x, p.y] for p in req.points]]]
            kwargs["input_labels"] = [[[p.label for p in req.points]]]
        if req.boxes:
            kwargs["input_boxes"] = [[[b.x1, b.y1, b.x2, b.y2] for b in req.boxes]]

        inputs = proc(**kwargs).to(self.device)
        with torch.no_grad():
            out = model(**inputs)
        pred_masks = proc.post_process_masks(
            out.pred_masks.cpu(), inputs["original_sizes"]
        )[0]
        iou = getattr(out, "iou_predictions", None)
        iou = iou.squeeze().tolist() if iou is not None else None

        masks: list[MaskResult] = []
        for i, mask in enumerate(pred_masks):
            score = 1.0
            if isinstance(iou, list) and i < len(iou):
                score = float(iou[i])
            elif isinstance(iou, float):
                score = iou
            masks.append(
                MaskResult(
                    mask_b64_png=encode_mask_png_b64(mask.numpy()),
                    score=score,
                    box=None,
                    label=req.text,
                )
            )
        return masks
