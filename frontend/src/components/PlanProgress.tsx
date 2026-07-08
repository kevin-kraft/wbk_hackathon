// Live checklist of the generated disassembly plan, derived from the run's
// PLAN_GENERATED event (the full plan) + STEP/SORT/SKIP/BLOCKED events (progress).

import { useMemo } from "react";
import { derivePlan, type PlanRow } from "../lib/derive";
import type { LoopEvent } from "../lib/types";

const DOT: Record<PlanRow["status"], string> = {
  pending: "bg-zinc-600",
  active: "bg-sky-400 animate-pulse",
  done: "bg-emerald-400",
  skipped: "bg-amber-400",
  blocked: "bg-rose-400",
};

export default function PlanProgress({ events }: { events: LoopEvent[] }) {
  const plan = useMemo(() => derivePlan(events), [events]);
  if (!plan) return null;

  return (
    <div className="space-y-1.5">
      <div className="text-[11px] uppercase tracking-wider text-zinc-500">
        plan source: <span className="text-zinc-300">{plan.source}</span>
      </div>
      <ol className="space-y-1">
        {plan.rows.map((row, i) => (
          <li key={`${row.part}-${i}`} className="flex items-center gap-2 text-sm">
            <span className={`h-2 w-2 shrink-0 rounded-full ${DOT[row.status]}`} />
            <span className="font-mono text-xs text-zinc-400">{i + 1}.</span>
            <span className={row.status === "done" ? "text-zinc-500 line-through" : "text-zinc-200"}>
              {row.action}
            </span>
            <span className="ml-auto font-mono text-[11px] text-zinc-500">{row.part}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
