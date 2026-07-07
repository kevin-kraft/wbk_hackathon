// The canonical per-part pipeline, and how raw loop states map onto it.

import type { LoopState } from "./types";

export interface StageMeta {
  key: string;
  label: string;
  blurb: string;
}

// Mirrors orchestrator/loop.py and the README loop diagram.
export const STAGES: StageMeta[] = [
  { key: "LOCATE", label: "Locate", blurb: "VLM picks the next part" },
  { key: "POSE", label: "Pose", blurb: "6DoF estimate" },
  { key: "PLAN", label: "Plan", blurb: "grasp from pose" },
  { key: "GRASP", label: "Grasp", blurb: "close + verify grip" },
  { key: "REMOVE", label: "Remove", blurb: "lift clear, confirm gone" },
  { key: "INSPECT", label: "Inspect", blurb: "damage VLM, N angles" },
  { key: "SORT", label: "Sort", blurb: "ok / reject bin" },
];

export const STAGE_INDEX: Record<string, number> = Object.fromEntries(
  STAGES.map((s, i) => [s.key, i]),
);

/** Which stage a raw loop state belongs to (null = terminal / non-stage). */
export function stateToStage(state: LoopState | string): string | null {
  switch (state) {
    case "LOCATE":
      return "LOCATE";
    case "POSE":
      return "POSE";
    case "GRIP":
    case "REGRASP":
    case "SKIP":
      return "GRASP";
    case "REMOVE":
    case "RECHECK":
      return "REMOVE";
    case "SORT":
      return "SORT";
    default:
      return null; // DONE / BLOCKED / SUMMARY
  }
}

// Per-state pill styling for the event log (Tailwind classes).
export const STATE_STYLE: Record<string, string> = {
  LOCATE: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  POSE: "bg-violet-500/15 text-violet-300 ring-violet-500/30",
  GRIP: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  REGRASP: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
  REMOVE: "bg-teal-500/15 text-teal-300 ring-teal-500/30",
  RECHECK: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
  SORT: "bg-indigo-500/15 text-indigo-300 ring-indigo-500/30",
  SKIP: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  BLOCKED: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  DONE: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  SUMMARY: "bg-zinc-500/15 text-zinc-300 ring-zinc-500/30",
};

export function stateStyle(state: string): string {
  return STATE_STYLE[state] ?? "bg-zinc-500/15 text-zinc-300 ring-zinc-500/30";
}
