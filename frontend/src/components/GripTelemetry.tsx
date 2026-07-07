import type { LoopEvent } from "../lib/types";
import { deriveGrip } from "../lib/derive";

// Renders the grip state for the *current* part. The motor-current value comes
// from the live grip-sensor endpoint (contracts/grip_api.md) once wired; until
// then we show the binary verdict + retry count the loop reports, which is the
// "rectify grabbing mistakes" behaviour made visible.
export default function GripTelemetry({ events }: { events: LoopEvent[] }) {
  const { attempts, confirmed, retrying } = deriveGrip(events);

  const label = confirmed ? "GRASPED" : retrying ? "REGRASPING" : "IDLE";
  const labelCls = confirmed ? "text-emerald-300" : retrying ? "text-amber-300" : "text-zinc-500";

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className={`inline-block h-3 w-3 rounded-full ${
              confirmed ? "bg-emerald-400" : retrying ? "bg-amber-400" : "bg-zinc-600"
            } ${retrying ? "animate-pulse" : ""}`}
          />
          <span className={`font-mono text-lg font-semibold ${labelCls}`}>{label}</span>
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
