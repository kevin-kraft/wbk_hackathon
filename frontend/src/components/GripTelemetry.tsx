import type { LoopEvent } from "../lib/types";

// Derives the grip state for the *current* part from the event stream. The
// motor-current value comes from the live grip-sensor endpoint (contracts/grip_api.md)
// once wired; until then we show the binary verdict + retry count the loop reports,
// which is the "rectify grabbing mistakes" behaviour made visible.
export default function GripTelemetry({ events }: { events: LoopEvent[] }) {
  // Look back to the most recent LOCATE to scope "this part".
  let startIdx = 0;
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].state === "LOCATE") {
      startIdx = i;
      break;
    }
  }
  const partEvents = events.slice(startIdx);
  const attempts = partEvents.filter((e) => e.state === "REGRASP").length;
  const confirmed = [...partEvents].reverse().find((e) => e.state === "GRIP");
  const retrying = partEvents.length > 0 && partEvents[partEvents.length - 1].state === "REGRASP";

  const status: { label: string; cls: string; pulse: boolean } = confirmed
    ? { label: "GRASPED", cls: "text-emerald-300", pulse: false }
    : retrying
      ? { label: "REGRASPING", cls: "text-amber-300", pulse: true }
      : { label: "IDLE", cls: "text-zinc-500", pulse: false };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className={`inline-block h-3 w-3 rounded-full ${
              confirmed ? "bg-emerald-400" : retrying ? "bg-amber-400" : "bg-zinc-600"
            } ${status.pulse ? "animate-pulse" : ""}`}
          />
          <span className={`font-mono text-lg font-semibold ${status.cls}`}>{status.label}</span>
        </div>
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500">Retries</div>
          <div className="font-mono text-lg font-semibold tabular-nums text-zinc-200">{attempts}</div>
        </div>
      </div>

      {/* Motor-current gauge placeholder — binds to the grip endpoint when live. */}
      <div>
        <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wider text-zinc-500">
          <span>Motor current (grip pressure)</span>
          <span className="font-mono normal-case text-zinc-600">live sensor pending</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-zinc-800">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              confirmed ? "bg-emerald-400/70" : retrying ? "bg-amber-400/70" : "bg-zinc-700"
            }`}
            style={{ width: confirmed ? "72%" : retrying ? "34%" : "0%" }}
          />
        </div>
      </div>

      <p className="text-[11px] leading-snug text-zinc-500">
        Binary verdict shown from the loop. The analog current/width from the motor-current sensor
        adds a partial-grip signal; a VLM grip check can AND in as a second opinion.
      </p>
    </div>
  );
}
