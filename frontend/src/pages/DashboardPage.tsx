import { useMemo } from "react";
import { useRun } from "../hooks/runContext";
import { streamUrl } from "../config/runtime";
import { Card } from "../components/ui";
import RunControls from "../components/RunControls";
import StageTracker from "../components/StageTracker";
import EventLog from "../components/EventLog";
import BinTally from "../components/BinTally";
import GripTelemetry from "../components/GripTelemetry";
import PromptBox from "../components/PromptBox";
import MjpegView from "../components/MjpegView";

export default function DashboardPage() {
  const run = useRun();

  // Current part + step, derived from the latest LOCATE.
  const current = useMemo(() => {
    for (let i = run.events.length - 1; i >= 0; i--) {
      if (run.events[i].state === "LOCATE") {
        return { part: String(run.events[i].data.part ?? "—"), step: run.events[i].step };
      }
    }
    return { part: "—", step: 0 };
  }, [run.events]);

  return (
    <div className="space-y-4">
      <Card title="Run control">
        <RunControls
          status={run.status}
          dryRun={run.dryRun}
          onDryRun={run.setDryRun}
          delayMs={run.delayMs}
          onDelay={run.setDelayMs}
          onStart={() => run.start(run.dryRun, run.delayMs / 1000)}
          onStop={run.stop}
          onReset={run.reset}
        />
        {run.error && (
          <p className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
            {run.error}
          </p>
        )}
      </Card>

      <Card
        title="Pipeline"
        right={
          <span className="text-[11px] text-zinc-500">
            part <span className="font-mono text-zinc-300">{current.part}</span> · step{" "}
            <span className="font-mono text-zinc-300">{current.step}</span>
          </span>
        }
      >
        <StageTracker latest={run.latest} />
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card title="Scene camera">
            <MjpegView src={streamUrl("sceneCamera")} label="scene" />
          </Card>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Card title="Grip sensor">
              <GripTelemetry events={run.events} />
            </Card>
            <Card title="Next-part prompt">
              <PromptBox value={run.prompt} onChange={run.setPrompt} disabled={run.status === "running"} />
            </Card>
          </div>
          <Card title="Bins">
            <BinTally stats={run.stats} events={run.events} />
          </Card>
        </div>

        <Card title="Event log" className="lg:col-span-1">
          <EventLog events={run.events} />
        </Card>
      </div>
    </div>
  );
}
