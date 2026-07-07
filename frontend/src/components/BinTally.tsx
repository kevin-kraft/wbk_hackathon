import type { RunStats, LoopEvent } from "../lib/types";
import { tallyBins } from "../lib/derive";
import { Stat } from "./ui";

// Live bin counts. Falls back to counting SORT events until the final summary lands.
export default function BinTally({ stats, events }: { stats: RunStats | null; events: LoopEvent[] }) {
  const { removed, ok, reject, skipped } = tallyBins(events, stats);

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <Stat label="Removed" value={removed} />
      <Stat label="OK bin" value={ok} tone="ok" />
      <Stat label="Reject bin" value={reject} tone="reject" />
      <Stat label="Skipped" value={skipped} tone="muted" />
    </div>
  );
}
