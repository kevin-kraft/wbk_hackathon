import type { RunStatus } from "../hooks/useRunStream";

export default function RunControls({
  status,
  dryRun,
  onDryRun,
  delayMs,
  onDelay,
  onStart,
  onStop,
  onReset,
}: {
  status: RunStatus;
  dryRun: boolean;
  onDryRun: (v: boolean) => void;
  delayMs: number;
  onDelay: (v: number) => void;
  onStart: () => void;
  onStop: () => void;
  onReset: () => void;
}) {
  const running = status === "running";

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

      <span
        className={`ml-auto rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider ${
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
