import type { ReactNode } from "react";
import type { RunStatus } from "../hooks/useRunStream";
import type { PosePipeline, RobotTarget } from "../lib/types";

const TARGETS: { value: RobotTarget; label: string; title: string }[] = [
  { value: "real", label: "Real", title: "Drive the real Jetson arm only" },
  { value: "sim", label: "Sim", title: "Drive the simulator only — no real hardware moves" },
  { value: "both", label: "Both", title: "Real arm (authoritative) + simulator mirrored as a digital twin" },
];

const POSE_PIPELINES: { value: PosePipeline; label: string; title: string }[] = [
  { value: "rgbd", label: "6DoF", title: "FoundationPose 6DoF with depth (default)" },
  { value: "rgb", label: "6DoF·RGB", title: "GigaPose 6DoF, RGB only (no depth)" },
  { value: "2d", label: "2D", title: "GigaPose CAD-free planar pose from the mask — no templates; top-down/planar picking" },
];

export default function RunControls({
  status,
  dryRun,
  onDryRun,
  delayMs,
  onDelay,
  robotTarget,
  onRobotTarget,
  posePipeline,
  onPosePipeline,
  simAvailable,
  activeTarget,
  onStart,
  onStop,
  onReset,
  productSlot,
}: {
  status: RunStatus;
  dryRun: boolean;
  onDryRun: (v: boolean) => void;
  delayMs: number;
  onDelay: (v: number) => void;
  robotTarget: RobotTarget;
  onRobotTarget: (v: RobotTarget) => void;
  posePipeline: PosePipeline;
  onPosePipeline: (v: PosePipeline) => void;
  simAvailable: boolean;
  activeTarget: string | null;
  onStart: () => void;
  onStop: () => void;
  onReset: () => void;
  // Optional product selector (plan-driven runs), rendered inline with the controls.
  productSlot?: ReactNode;
}) {
  const running = status === "running";
  // Target only matters for a live run; mocks ignore it.
  const targetDisabled = running || dryRun;
  const ACTIVE_LABEL: Record<string, string> = {
    real: "▶ REAL ARM",
    sim: "▶ SIMULATOR",
    both: "▶ REAL + SIM",
  };

  return (
    <div className="flex flex-wrap items-center gap-3">
      {!running ? (
        <button
          onClick={onStart}
          className="rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-sky-950 transition hover:bg-sky-400"
        >
          ▶ Start run
        </button>
      ) : (
        <button
          onClick={onStop}
          className="rounded-lg bg-rose-500 px-4 py-2 text-sm font-semibold text-rose-950 transition hover:bg-rose-400"
        >
          ■ Stop
        </button>
      )}
      <button
        onClick={onReset}
        disabled={running}
        className="rounded-lg border border-zinc-700 px-3 py-2 text-sm font-medium text-zinc-300 transition hover:bg-zinc-800 disabled:opacity-40"
      >
        Reset
      </button>

      <label className="ml-1 flex cursor-pointer items-center gap-2 text-sm text-zinc-300">
        <input
          type="checkbox"
          checked={dryRun}
          onChange={(e) => onDryRun(e.target.checked)}
          disabled={running}
          className="h-4 w-4 accent-sky-500"
        />
        Dry run (mocks)
      </label>

      <div
        className="flex items-center gap-1 rounded-lg border border-zinc-700 p-0.5"
        title={dryRun ? "Dry run uses mocks — robot target is ignored" : "Which robot to drive"}
      >
        {TARGETS.map((t) => {
          const unavailable = t.value !== "real" && !simAvailable;
          const active = robotTarget === t.value;
          return (
            <button
              key={t.value}
              onClick={() => onRobotTarget(t.value)}
              disabled={targetDisabled || unavailable}
              title={unavailable ? "Set the simulator endpoint in Settings first" : t.title}
              className={`rounded-md px-2.5 py-1 text-xs font-semibold transition ${
                active ? "bg-sky-500 text-sky-950" : "text-zinc-400 hover:bg-zinc-800"
              } disabled:cursor-not-allowed disabled:opacity-40`}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      <div
        className="flex items-center gap-1 rounded-lg border border-zinc-700 p-0.5"
        title={dryRun ? "Dry run uses mocks — pose stage is mocked" : "Pose stage pipeline"}
      >
        <span className="px-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Pose</span>
        {POSE_PIPELINES.map((p) => {
          const active = posePipeline === p.value;
          return (
            <button
              key={p.value}
              onClick={() => onPosePipeline(p.value)}
              disabled={targetDisabled}
              title={p.title}
              className={`rounded-md px-2 py-1 text-xs font-semibold transition ${
                active ? "bg-sky-500 text-sky-950" : "text-zinc-400 hover:bg-zinc-800"
              } disabled:cursor-not-allowed disabled:opacity-40`}
            >
              {p.label}
            </button>
          );
        })}
      </div>

      {productSlot}

      <label className="flex items-center gap-2 text-sm text-zinc-400">
        Pace
        <input
          type="range"
          min={0}
          max={2000}
          step={100}
          value={delayMs}
          onChange={(e) => onDelay(Number(e.target.value))}
          disabled={running}
          className="w-28 accent-sky-500"
        />
        <span className="w-12 font-mono text-xs tabular-nums text-zinc-500">{delayMs}ms</span>
      </label>

      {activeTarget && !dryRun && (
        <span
          className="ml-auto rounded-full bg-zinc-700/40 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-zinc-300"
          title="Robot the server drove this run"
        >
          {ACTIVE_LABEL[activeTarget] ?? activeTarget}
        </span>
      )}
      <span
        className={`${activeTarget && !dryRun ? "" : "ml-auto"} rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider ${
          status === "running"
            ? "bg-sky-500/15 text-sky-300"
            : status === "done"
              ? "bg-emerald-500/15 text-emerald-300"
              : status === "error"
                ? "bg-rose-500/15 text-rose-300"
                : "bg-zinc-700/40 text-zinc-400"
        }`}
      >
        {status}
      </span>
    </div>
  );
}
