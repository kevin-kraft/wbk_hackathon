import { useState } from "react";
import type { RuntimeConfig, ServiceKey, StreamKey } from "../lib/types";
import { getConfig, saveOverrides, clearOverrides, getOverrides, SERVICE_KEYS, STREAM_KEYS } from "../config/runtime";
import { Card } from "../components/ui";

const SERVICE_LABEL: Record<ServiceKey, string> = {
  orchestrator: "Orchestrator",
  yolo: "YOLO",
  sam3: "SAM 3",
  locateanything: "LocateAnything",
  foundationpose: "FoundationPose",
  gigapose: "GigaPose",
  damage: "Damage VLM",
  movement: "Movement (Jetson)",
  grip: "Grip sensor",
};

const STREAM_LABEL: Record<StreamKey, string> = {
  sceneCamera: "Scene camera (MJPEG)",
  inspectionCamera: "Inspection camera (MJPEG)",
};

function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="block">
      <span className="text-[11px] font-medium text-zinc-400">{label}</span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
        className="mt-1 w-full rounded-lg border border-zinc-700 bg-zinc-950/60 px-3 py-1.5 font-mono text-xs text-zinc-200 focus:border-sky-500 focus:outline-none"
      />
    </label>
  );
}

export default function SettingsPage() {
  const [cfg, setCfg] = useState<RuntimeConfig>(() => structuredClone(getConfig()));
  const hasOverrides = getOverrides() !== null;

  const setService = (k: ServiceKey, v: string) =>
    setCfg((c) => ({ ...c, services: { ...c.services, [k]: v } }));
  const setStream = (k: StreamKey, v: string) =>
    setCfg((c) => ({ ...c, streams: { ...c.streams, [k]: v } }));

  const save = () => {
    saveOverrides(cfg);
    window.location.reload();
  };
  const reset = () => {
    clearOverrides();
    window.location.reload();
  };

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <Card title="Endpoints" right={<span className="text-[11px] text-zinc-500">{hasOverrides ? "local overrides active" : "from config.json"}</span>}>
        <p className="mb-4 text-[12px] leading-snug text-zinc-500">
          Each microservice can live on a different host. Changes here are saved in this browser and
          override <code className="font-mono text-zinc-400">public/config.json</code>. For a fleet-wide
          default, edit that file on the server instead (no rebuild needed).
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {SERVICE_KEYS.map((k) => (
            <Field key={k} label={SERVICE_LABEL[k]} value={cfg.services[k]} onChange={(v) => setService(k, v)} />
          ))}
        </div>
      </Card>

      <Card title="Camera streams">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {STREAM_KEYS.map((k) => (
            <Field key={k} label={STREAM_LABEL[k]} value={cfg.streams[k]} onChange={(v) => setStream(k, v)} />
          ))}
        </div>
      </Card>

      <Card title="Run defaults">
        <div className="flex flex-wrap items-center gap-6">
          <label className="flex cursor-pointer items-center gap-2 text-sm text-zinc-300">
            <input
              type="checkbox"
              checked={cfg.run.dryRun}
              onChange={(e) => setCfg((c) => ({ ...c, run: { ...c.run, dryRun: e.target.checked } }))}
              className="h-4 w-4 accent-sky-500"
            />
            Default to dry run (mocks)
          </label>
          <label className="flex items-center gap-2 text-sm text-zinc-300">
            Pace
            <input
              type="number"
              min={0}
              step={100}
              value={cfg.run.stepDelayMs}
              onChange={(e) => setCfg((c) => ({ ...c, run: { ...c.run, stepDelayMs: Number(e.target.value) } }))}
              className="w-24 rounded-lg border border-zinc-700 bg-zinc-950/60 px-2 py-1 font-mono text-xs text-zinc-200 focus:border-sky-500 focus:outline-none"
            />
            ms
          </label>
        </div>
      </Card>

      <div className="flex items-center gap-3">
        <button
          onClick={save}
          className="rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-sky-950 transition hover:bg-sky-400"
        >
          Save &amp; reload
        </button>
        <button
          onClick={reset}
          disabled={!hasOverrides}
          className="rounded-lg border border-zinc-700 px-3 py-2 text-sm font-medium text-zinc-300 transition hover:bg-zinc-800 disabled:opacity-40"
        >
          Reset to config.json
        </button>
      </div>
    </div>
  );
}
