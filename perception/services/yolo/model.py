"""YOLO detection adapter (Ultralytics)."""

from __future__ import annotations

import time

from ..shared.imaging import decode_image_b64, to_numpy
from ..shared.model_base import BasePerceptionModel
from ..shared.schemas import BBox, Detection, YoloRequest, YoloResponse


class YoloModel(BasePerceptionModel):
    name = "yolo"

    def load(self) -> None:
        from ultralytics import YOLO

        device = self._resolve_device()
        self._model = YOLO(self.settings.yolo_weights)
        self._model.to(device)
        self._loaded = True

    def infer(self, req: YoloRequest) -> YoloResponse:
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
            verbose=False,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        result = results[0]
        names = result.names  # {class_id: label}
        detections: list[Detection] = []
        for box in result.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            class_id = int(box.cls[0])
            detections.append(
                Detection(
                    box=BBox(x1=x1, y1=y1, x2=x2, y2=y2),
                    score=float(box.conf[0]),
                    class_id=class_id,
                    label=names.get(class_id, str(class_id)),
                )
            )

        return YoloResponse(
            detections=detections,
            width=img.width,
            height=img.height,
            model=self.settings.yolo_weights,
            inference_ms=elapsed_ms,
        )
