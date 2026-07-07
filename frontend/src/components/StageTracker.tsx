import type { LoopEvent } from "../lib/types";
import { STAGES, STAGE_INDEX, stateToStage } from "../lib/stages";

// Highlights the active stage of the per-part loop from the latest event.
export default function StageTracker({ latest }: { latest: LoopEvent | null }) {
  const activeStage = latest ? stateToStage(latest.state) : null;
  const activeIdx = activeStage ? STAGE_INDEX[activeStage] : -1;
  const isRetry = latest?.state === "REGRASP" || latest?.state === "RECHECK";

  return (
    <div className="flex items-stretch gap-1.5 overflow-x-auto">
      {STAGES.map((stage, i) => {
        const done = activeIdx >= 0 && i < activeIdx;
        const active = i === activeIdx;
        return (
          <div key={stage.key} className="flex min-w-[92px] flex-1 items-center">
            <div
              className={`w-full rounded-lg border px-2.5 py-2 transition ${
                active
                  ? isRetry
                    ? "border-amber-500/50 bg-amber-500/10"
                    : "border-sky-500/50 bg-sky-500/10"
                  : done
                    ? "border-zinc-700 bg-zinc-800/40"
                    : "border-zinc-800 bg-zinc-900/30"
              }`}
            >
              <div className="flex items-center gap-1.5">
                <span
                  className={`grid h-4 w-4 place-items-center rounded-full text-[9px] font-bold ${
                    active
                      ? isRetry
                        ? "bg-amber-400 text-amber-950"
                        : "bg-sky-400 text-sky-950"
                      : done
                        ? "bg-emerald-400/80 text-emerald-950"
                        : "bg-zinc-700 text-zinc-400"
                  }`}
                >
                  {done ? "✓" : i + 1}
                </span>
                <span
                  className={`text-xs font-semibold ${
                    active ? "text-zinc-100" : done ? "text-zinc-300" : "text-zinc-500"
                  }`}
                >
                  {stage.label}
                </span>
              </div>
              <div className="mt-1 text-[10px] leading-tight text-zinc-500">{stage.blurb}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
