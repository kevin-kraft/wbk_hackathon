import type { RunStats, LoopEvent } from "../lib/types";
import { Stat } from "./ui";

// Live bin counts. Falls back to counting SORT events until the final summary lands.
export default function BinTally({ stats, events }: { stats: RunStats | null; events: LoopEvent[] }) {
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

  const ok = stats?.ok_bin ?? live.ok;
  const reject = stats?.reject_bin ?? live.reject;
  const removed = stats?.removed ?? live.ok + live.reject;
  const skipped = stats?.skipped ?? live.skipped;

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <Stat label="Removed" value={removed} />
      <Stat label="OK bin" value={ok} tone="ok" />
      <Stat label="Reject bin" value={reject} tone="reject" />
      <Stat label="Skipped" value={skipped} tone="muted" />
    </div>
  );
}
