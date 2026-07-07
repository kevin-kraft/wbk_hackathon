// Pure derivations from the loop event stream. Kept out of the components so
// they're unit-testable without rendering.

import type { LoopEvent, RunStats } from "./types";

export interface BinCounts {
  removed: number;
  ok: number;
  reject: number;
  skipped: number;
}

// Live bin counts from SORT/SKIP events, superseded by the final summary once it lands.
export function tallyBins(events: LoopEvent[], stats: RunStats | null): BinCounts {
  const live = events.reduce(
    (acc, e) => {
      if (e.state === "SORT") {
        const bin = String(e.data.bin ?? "");
        if (bin === "ok_bin") acc.ok += 1;
        else if (bin === "reject_bin") acc.reject += 1;
      }
      if (e.state === "SKIP") acc.skipped += 1;
      return acc;
    },
    { ok: 0, reject: 0, skipped: 0 },
  );

  return {
    ok: stats?.ok_bin ?? live.ok,
    reject: stats?.reject_bin ?? live.reject,
    removed: stats?.removed ?? live.ok + live.reject,
    skipped: stats?.skipped ?? live.skipped,
  };
}

export interface InspectedPart {
  step: number;
  part: string;
  verdict: string;
  bin: string;
}

// Pair each SORT with the part name from its step's LOCATE.
export function deriveInspections(events: LoopEvent[]): InspectedPart[] {
  const partByStep = new Map<number, string>();
  for (const e of events) {
    if (e.state === "LOCATE") partByStep.set(e.step, String(e.data.part ?? "—"));
  }
  return events
    .filter((e) => e.state === "SORT")
    .map((e) => ({
      step: e.step,
      part: partByStep.get(e.step) ?? "—",
      verdict: String(e.data.verdict ?? ""),
      bin: String(e.data.bin ?? ""),
    }));
}

export type GripStatus = "grasped" | "regrasping" | "idle";

export interface GripState {
  attempts: number;
  confirmed: boolean;
  retrying: boolean;
  status: GripStatus;
}

// Grip state for the CURRENT part (scoped to the most recent LOCATE).
export function deriveGrip(events: LoopEvent[]): GripState {
  let startIdx = 0;
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].state === "LOCATE") {
      startIdx = i;
      break;
    }
  }
  const partEvents = events.slice(startIdx);
  const attempts = partEvents.filter((e) => e.state === "REGRASP").length;
  const confirmed = partEvents.some((e) => e.state === "GRIP");
  const retrying = partEvents.length > 0 && partEvents[partEvents.length - 1].state === "REGRASP";
  const status: GripStatus = confirmed ? "grasped" : retrying ? "regrasping" : "idle";
  return { attempts, confirmed, retrying, status };
}

export interface CurrentPart {
  part: string;
  step: number;
}

// The part currently being worked, from the latest LOCATE.
export function currentPart(events: LoopEvent[]): CurrentPart {
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].state === "LOCATE") {
      return { part: String(events[i].data.part ?? "—"), step: events[i].step };
    }
  }
  return { part: "—", step: 0 };
}
