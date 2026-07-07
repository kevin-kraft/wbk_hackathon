"""LocateAnything adapter — NVIDIA LocateAnything-3B (vision-language grounding).

Image + text query -> located boxes / points. Emitted as `<box>...</box>`
special tokens (not JSON): boxes carry 4 normalized ints [0,1000], points carry
2. There is NO native per-instance float score — instances come back in a ranked
list (Parallel Box Decoding order ~= confidence), so we derive a rank-based
pseudo-score to satisfy the response contract.

Weights (`nvidia/LocateAnything-3B`) are ungated but load via `trust_remote_code`
(custom `py_apply_chat_template` / `process_vision_info` / `generation_mode`
methods) — pin a revision in prod since remote-code APIs can shift.
"""

from __future__ import annotations

import re
import time

from ..shared.imaging import decode_image_b64
from ..shared.model_base import BasePerceptionModel
from ..shared.schemas import BBox, LocateRequest, LocateResponse, Location, Point

_DEFAULT_MODEL_ID = "nvidia/LocateAnything-3B"

# Try the 4-int box pattern first; a box must not be misread as two points.
_BOX_RE = re.compile(r"<box><(\d+)><(\d+)><(\d+)><(\d+)></box>")
_POINT_RE = re.compile(r"<box><(\d+)><(\d+)></box>")


class LocateAnythingBackend(BasePerceptionModel):
    name = "locateanything"

    def load(self) -> None:
        import torch
        from transformers import AutoModel, AutoProcessor, AutoTokenizer

        device = self._resolve_device()
        model_id = self.settings.locate_model_id or _DEFAULT_MODEL_ID
        self._dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32

        self._tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
        self._processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
        self._model = (
            AutoModel.from_pretrained(model_id, torch_dtype=self._dtype, trust_remote_code=True)
            .to(device)
            .eval()
        )
        self._model_id = model_id
        self._loaded = True

    # ------------------------------------------------------------------ #
    def infer(self, req: LocateRequest) -> LocateResponse:
        import torch

        img = decode_image_b64(req.image_b64)
        question = (
            "Locate all the instances that matches the following description: "
            f"{req.query}."
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": img},
                    {"type": "text", "text": question},
                ],
            }
        ]

        proc = self._processor
        text = proc.py_apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        images, videos = proc.process_vision_info(messages)
        inputs = proc(text=[text], images=images, videos=videos, return_tensors="pt").to(self.device)

        t0 = time.perf_counter()
        with torch.no_grad():
            response = self._model.generate(
                pixel_values=inputs["pixel_values"].to(self._dtype),
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
                image_grid_hws=inputs.get("image_grid_hws", None),
                tokenizer=self._tokenizer,
                max_new_tokens=2048,
                generation_mode="hybrid",
            )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        answer = response[0] if isinstance(response, tuple) else response
        if not isinstance(answer, str):
            answer = str(answer)

        locations = self._parse(answer, img.width, img.height, req.query, req.top_k)
        return LocateResponse(
            locations=locations,
            width=img.width,
            height=img.height,
            model=self._model_id,
            inference_ms=elapsed_ms,
        )

    # ------------------------------------------------------------------ #
    def _parse(self, answer: str, w: int, h: int, label: str, top_k: int) -> list[Location]:
        raw: list[tuple] = []  # (box|None, point)

        # Boxes first; blank them out so the point regex can't re-match them.
        masked = answer
        for m in _BOX_RE.finditer(answer):
            a, b, c, d = (int(v) for v in m.groups())
            box = BBox(x1=a / 1000 * w, y1=b / 1000 * h, x2=c / 1000 * w, y2=d / 1000 * h)
            cx, cy = (box.x1 + box.x2) / 2, (box.y1 + box.y2) / 2
            raw.append((box, Point(x=cx, y=cy)))
        masked = _BOX_RE.sub("", masked)

        # Remaining bare 2-int tags are points (pointing task).
        for m in _POINT_RE.finditer(masked):
            a, b = (int(v) for v in m.groups())
            raw.append((None, Point(x=a / 1000 * w, y=b / 1000 * h)))

        raw = raw[:top_k]
        n = max(len(raw), 1)
        # Rank-based pseudo-score (no native float); first = highest.
        return [
            Location(point=pt, box=box, score=round(1.0 - i / n, 4), label=label)
            for i, (box, pt) in enumerate(raw)
        ]
