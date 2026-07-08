// Supported disassembly parts offered in the SAM3 / LocateAnything prompt
// selector (open-vocab text models). YOLO is fixed COCO-80 vocab and does NOT
// know these, so the selector does not apply to it.
//
// Scope: the SHORT variants only (per the operator, 2026-07-07) — we run the
// "kurz" variant of each part. `prompt` is the text sent to the model.

export interface Part {
  id: string;
  label: string;
  prompt: string;
}

export const SUPPORTED_PARTS: Part[] = [
  { id: "anker", label: "Anker", prompt: "copper part" },
  { id: "buerstenhalter", label: "Bürstenhalter", prompt: "bürstenhalter" },
  { id: "poltopf", label: "Poltopf", prompt: "poltopf" },
];
