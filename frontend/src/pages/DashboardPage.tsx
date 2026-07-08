import { useMemo, useState } from "react";
import { useRun } from "../hooks/runContext";
import { serviceUrl, streamUrl } from "../config/runtime";
import { currentPart } from "../lib/derive";
import { generateScenePreview, SIM_NOT_IMPLEMENTED } from "../lib/api";
import { Card } from "../components/ui";
import RunControls from "../components/RunControls";
import SourceToggle from "../components/SourceToggle";
import StageTracker from "../components/StageTracker";
import EventLog from "../components/EventLog";
import BinTally from "../components/BinTally";
import GripTelemetry from "../components/GripTelemetry";
import PromptBox from "../components/PromptBox";
import MjpegView from "../components/MjpegView";

export default function DashboardPage() {
  const run = useRun();

  // Current part + step, derived from the latest LOCATE.
  const current = useMemo(() => currentPart(run.events), [run.events]);

  // sim/both run modes are only offered once a simulator endpoint is configured.
  const simAvailable = Boolean(serviceUrl("movementSim"));

  // Sim scene preview (frontal, slightly-elevated overview render).
  const [preview, setPreview] = useState<string | null>(null);
  const [previewErr, setPreviewErr] = useState<string | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  async function genPreview() {
    setPreviewBusy(true);
    setPreviewErr(null);
    try {
      setPreview(await generateScenePreview());
    } catch (e) {
      const m = e instanceof Error ? e.message : String(e);
      setPreviewErr(
        m === SIM_NOT_IMPLEMENTED
          ? "Sim scene preview isn't implemented yet (Group 2). See contracts/sim_scene_capture.md."
          : m,
      );
    } finally {
      setPreviewBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card title="Run control">
        <RunControls
          status={run.status}
          dryRun={run.dryRun}
          onDryRun={run.setDryRun}
          delayMs={run.delayMs}
          onDelay={run.setDelayMs}
          robotTarget={run.robotTarget}
          onRobotTarget={run.setRobotTarget}
          simAvailable={simAvailable}
          activeTarget={run.activeTarget}
          onStart={() => run.start(run.dryRun, run.delayMs / 1000, run.dryRun ? undefined : run.robotTarget)}
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
          <Card
            title="Scene camera"
            right={<SourceToggle value={run.sourceMode} onChange={run.setSourceMode} />}
          >
            {run.sourceMode === "real" ? (
              <MjpegView src={streamUrl("sceneCamera")} label="scene" />
            ) : (
              <div className="space-y-3">
                <button
                  onClick={genPreview}
                  disabled={previewBusy}
                  className="rounded-lg bg-sky-500 px-3 py-1.5 text-sm font-semibold text-sky-950 transition hover:bg-sky-400 disabled:opacity-40"
                >
                  {previewBusy ? "Rendering…" : "Generate scene preview"}
                </button>
                {preview ? (
                  <img src={`data:image/png;base64,${preview}`} alt="sim scene preview" className="w-full rounded-lg" />
                ) : (
                  <div className="grid h-56 place-items-center rounded-lg border border-dashed border-zinc-700 text-center text-sm text-zinc-600">
                    Frontal, slightly-elevated view of the arm + table.
                    <br />
                    Render one from the simulator.
                  </div>
                )}
                {previewErr && (
                  <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
                    {previewErr}
                  </p>
                )}
              </div>
            )}
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
