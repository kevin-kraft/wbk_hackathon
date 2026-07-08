"""YOLO-Seg adapter (Ultralytics) — instance segmentation.

Same Ultralytics backbone as the detector, but a *-seg weights file, so each
prediction carries a per-instance mask in addition to the box. `retina_masks`
returns masks at the original image resolution (not the letterboxed net size),
so the base64 PNG lines up 1:1 with the RGB the frontend renders.
"""

from __future__ import annotations

import time

from ..shared.imaging import decode_image_b64, encode_mask_png_b64, to_numpy
from ..shared.model_base import BasePerceptionModel
from ..shared.schemas import BBox, SegInstance, YoloSegRequest, YoloSegResponse


class YoloSegModel(BasePerceptionModel):
    name = "yoloseg"

    def load(self) -> None:
        from ultralytics import YOLO

        device = self._resolve_device()
        self._model = YOLO(self.settings.yolo_seg_weights)
        self._model.to(device)
        self._loaded = True

    def infer(self, req: YoloSegRequest) -> YoloSegResponse:
        img = decode_image_b64(req.image_b64)
        arr = to_numpy(img)

        t0 = time.perf_counter()
        results = self._model.predict(
            arr,
            conf=req.conf,
            iou=req.iou,
            classes=req.classes,
            max_det=req.max_det,
            device=self.device,
            retina_masks=True,  # masks at original image resolution
            verbose=False,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        result = results[0]
        names = result.names  # {class_id: label}
        instances: list[SegInstance] = []
        # result.masks is None when nothing was detected.
        if result.masks is not None:
            masks = result.masks.data.cpu().numpy()  # (N, H, W), 0/1
            for i, box in enumerate(result.boxes):
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                class_id = int(box.cls[0])
                instances.append(
                    SegInstance(
                        box=BBox(x1=x1, y1=y1, x2=x2, y2=y2),
                        mask_b64_png=encode_mask_png_b64(masks[i]),
                        score=float(box.conf[0]),
                        class_id=class_id,
                        label=names.get(class_id, str(class_id)),
                    )
                )

        return YoloSegResponse(
            instances=instances,
            width=img.width,
            height=img.height,
            model=self.settings.yolo_seg_weights,
            inference_ms=elapsed_ms,
        )
