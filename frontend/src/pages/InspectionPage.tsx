import { useMemo } from "react";
import { useRun } from "../hooks/runContext";
import { useServiceHealth } from "../hooks/useServiceHealth";
import { streamUrl } from "../config/runtime";
import { Card } from "../components/ui";
import ServiceInfo from "../components/ServiceInfo";
import MjpegView from "../components/MjpegView";
import BinTally from "../components/BinTally";

interface InspectedPart {
  step: number;
  part: string;
  verdict: string;
  bin: string;
}

export default function InspectionPage() {
  const run = useRun();
  const { health } = useServiceHealth();

  // Pair each SORT with the part name from its step's LOCATE.
  const inspected = useMemo<InspectedPart[]>(() => {
    const partByStep = new Map<number, string>();
    for (const e of run.events) {
      if (e.state === "LOCATE") partByStep.set(e.step, String(e.data.part ?? "—"));
    }
    return run.events
      .filter((e) => e.state === "SORT")
      .map((e) => ({
        step: e.step,
        part: partByStep.get(e.step) ?? "—",
        verdict: String(e.data.verdict ?? ""),
        bin: String(e.data.bin ?? ""),
      }));
  }, [run.events]);

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        <Card title="Inspection camera">
          <MjpegView src={streamUrl("inspectionCamera")} label="inspection" />
          <p className="mt-3 text-[12px] leading-snug text-zinc-500">
            The arm presents each removed part here from several angles; the damage VLM judges OK
            vs damaged. Uncertain → reject bin (fail-safe).
          </p>
        </Card>

        <Card title="Inspection results">
          {inspected.length === 0 ? (
            <p className="py-6 text-center text-sm text-zinc-600">No parts inspected yet.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-zinc-500">
                  <th className="pb-2 font-medium">Step</th>
                  <th className="pb-2 font-medium">Part</th>
                  <th className="pb-2 font-medium">Verdict</th>
                  <th className="pb-2 font-medium">Bin</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {inspected.map((p) => {
                  const damaged = p.bin === "reject_bin";
                  return (
                    <tr key={p.step} className="border-t border-zinc-800">
                      <td className="py-1.5 text-zinc-500">{p.step}</td>
                      <td className="py-1.5 text-zinc-200">{p.part}</td>
                      <td className={`py-1.5 ${damaged ? "text-rose-300" : "text-emerald-300"}`}>
                        {p.verdict}
                      </td>
                      <td className={`py-1.5 ${damaged ? "text-rose-400" : "text-emerald-400"}`}>
                        {p.bin}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      <div className="space-y-4">
        <Card title="Damage service">
          <ServiceInfo
            serviceKey="damage"
            title="Damage VLM"
            desc="OpenRouter VLM with few-shot OK/damaged reference images; returns verdict + bin. Fail-safe: uncertain sorts to reject."
            health={health}
          />
        </Card>
        <Card title="Bins">
          <BinTally stats={run.stats} events={run.events} />
        </Card>
      </div>
    </div>
  );
}
