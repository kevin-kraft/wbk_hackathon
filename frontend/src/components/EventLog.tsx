import { useEffect, useRef } from "react";
import type { LoopEvent } from "../lib/types";
import { stateStyle } from "../lib/stages";

// Append-only stream of loop events, auto-scrolled to the newest.
export default function EventLog({ events }: { events: LoopEvent[] }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [events.length]);

  if (events.length === 0) {
    return <p className="py-8 text-center text-sm text-zinc-600">No events yet — start a run.</p>;
  }

  return (
    <div className="max-h-[420px] space-y-1 overflow-y-auto font-mono text-[12px]">
      {events.map((e, i) => (
        <div key={i} className="flex items-start gap-2 rounded px-1 py-0.5 hover:bg-zinc-800/40">
          <span className="w-8 shrink-0 text-right text-zinc-600">[{e.step}]</span>
          <span
            className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ${stateStyle(
              e.state,
            )}`}
          >
            {e.state}
          </span>
          <span className="text-zinc-300">{e.message}</span>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}
