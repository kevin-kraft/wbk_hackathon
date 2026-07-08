import { useMemo, useState } from "react";
import { useRun } from "../hooks/runContext";
import { useServiceHealth } from "../hooks/useServiceHealth";
import { captureScene, runYolo, runSam3, runLocate, SIM_NOT_IMPLEMENTED } from "../lib/api";
import type { LocateResponse, OverlayKind, Sam3Response, SceneCapture, YoloResponse } from "../lib/types";
import { Card } from "../components/ui";
import ServiceInfo from "../components/ServiceInfo";
import SourceToggle from "../components/SourceToggle";
import PartSelector from "../components/PartSelector";
import SceneView, { type BoxOverlay, type PointOverlay } from "../components/SceneView";
import { SUPPORTED_PARTS } from "../lib/parts";

type Model = "yolo" | "sam3" | "locateanything";
type Result =
  | { kind: "yolo"; data: YoloResponse }
  | { kind: "sam3"; data: Sam3Response }
  | { kind: "locate"; data: LocateResponse };

const MODELS: { key: Model; label: string }[] = [
  { key: "yolo", label: "YOLO" },
  { key: "sam3", label: "SAM 3" },
  { key: "locateanything", label: "LocateAnything" },
];

function friendlyError(e: unknown): string {
  const m = e instanceof Error ? e.message : String(e);
  if (m === SIM_NOT_IMPLEMENTED)
    return "Sim scene capture isn't implemented yet (Group 2). Switch to Real, or see contracts/sim_scene_capture.md.";
  return m;
}

export default function PerceptionPage() {
  const run = useRun();
  const { health } = useServiceHealth();

  const [scene, setScene] = useState<SceneCapture | null>(null);
  const [showDepth, setShowDepth] = useState(false);
  const [model, setModel] = useState<Model>("sam3");
  const [prompt, setPrompt] = useState(SUPPORTED_PARTS[0].prompt);
  const [overlayKind, setOverlayKind] = useState<OverlayKind>("masks");
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState<null | "capture" | "infer">(null);
  const [err, setErr] = useState<string | null>(null);

  const needsPrompt = model === "sam3" || model === "locateanything";
  const canInfer = !!scene && !busy && (!needsPrompt || prompt.trim().length > 0);

  function pickModel(m: Model) {
    setModel(m);
    setResult(null);
    setOverlayKind(m === "sam3" ? "masks" : "boxes");
  }

  async function capture() {
    setBusy("capture");
    setErr(null);
    try {
      const s = await captureScene(run.sourceMode);
      setScene(s);
      setResult(null);
      if (!s.depth_b64) setShowDepth(false);
    } catch (e) {
      setErr(friendlyError(e));
    } finally {
      setBusy(null);
    }
  }

  async function infer() {
    if (!scene) return;
    setBusy("infer");
    setErr(null);
    try {
      if (model === "yolo") setResult({ kind: "yolo", data: await runYolo(scene.rgb_b64) });
      else if (model === "sam3") setResult({ kind: "sam3", data: await runSam3(scene.rgb_b64, prompt) });
      else setResult({ kind: "locate", data: await runLocate(scene.rgb_b64, prompt) });
    } catch (e) {
      setErr(friendlyError(e));
    } finally {
      setBusy(null);
    }
  }

  const overlays = useMemo<{ boxes: BoxOverlay[]; masks: string[]; points: PointOverlay[] }>(() => {
    if (!result) return { boxes: [], masks: [], points: [] };
    if (result.kind === "yolo")
      return { boxes: result.data.detections.map((d) => ({ box: d.box, label: d.label, score: d.score })), masks: [], points: [] };
    if (result.kind === "sam3")
      return {
        boxes: result.data.masks.filter((m) => m.box).map((m) => ({ box: m.box!, label: m.label ?? prompt, score: m.score })),
        masks: result.data.masks.map((m) => m.mask_b64_png),
        points: [],
      };
    return {
      boxes: result.data.locations.filter((l) => l.box).map((l) => ({ box: l.box!, label: l.label, score: l.score })),
      masks: [],
      points: result.data.locations.map((l) => ({ x: l.point.x, y: l.point.y, label: l.label })),
    };
  }, [result, prompt]);

  const count = result
    ? result.kind === "yolo"
      ? result.data.detections.length
      : result.kind === "sam3"
        ? result.data.masks.length
        : result.data.locations.length
    : 0;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      {/* ---- Scene + overlays ---- */}
      <div className="space-y-4 lg:col-span-2">
        <Card
          title="Scene"
          right={
            <div className="flex items-center gap-2">
              <SourceToggle value={run.sourceMode} onChange={run.setSourceMode} disabled={busy !== null} />
            </div>
          }
        >
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <button
              onClick={capture}
              disabled={busy !== null}
              className="rounded-lg bg-sky-500 px-3 py-1.5 text-sm font-semibold text-sky-950 transition hover:bg-sky-400 disabled:opacity-40"
            >
              {busy === "capture" ? "Capturing…" : run.sourceMode === "sim" ? "Render Zivid view" : "Capture Zivid view"}
            </button>
            <label className={`flex items-center gap-1.5 text-xs ${scene?.depth_b64 ? "text-zinc-300" : "text-zinc-600"}`}>
              <input
                type="checkbox"
                checked={showDepth}
                onChange={(e) => setShowDepth(e.target.checked)}
                disabled={!scene?.depth_b64}
                className="h-3.5 w-3.5 accent-sky-500"
              />
              Depth map
            </label>
            {result && model === "sam3" && (
              <div className="ml-auto inline-flex items-center gap-1 rounded-lg border border-zinc-700 p-0.5">
                {(["masks", "boxes"] as OverlayKind[]).map((k) => (
                  <button
                    key={k}
                    onClick={() => setOverlayKind(k)}
                    className={`rounded-md px-2 py-0.5 text-[11px] font-semibold capitalize transition ${
                      overlayKind === k ? "bg-sky-500 text-sky-950" : "text-zinc-400 hover:bg-zinc-800"
                    }`}
                  >
                    {k}
                  </button>
                ))}
              </div>
            )}
          </div>

          {scene ? (
            <SceneView
              rgbB64={scene.rgb_b64}
              depthB64={scene.depth_b64}
              showDepth={showDepth}
              overlayKind={overlayKind}
              boxes={overlays.boxes}
              masks={overlays.masks}
              points={overlays.points}
            />
          ) : (
            <div className="grid h-64 place-items-center rounded-lg border border-dashed border-zinc-700 text-sm text-zinc-600">
              No scene yet — capture one to run detection.
            </div>
          )}

          {err && (
            <p className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">{err}</p>
          )}
          {result && !err && (
            <p className="mt-3 text-[12px] text-zinc-500">
              {count} result{count === 1 ? "" : "s"} · <span className="font-mono text-zinc-400">{result.data.model}</span> ·{" "}
              {result.data.inference_ms.toFixed(0)} ms · {result.data.width}×{result.data.height}
            </p>
          )}
        </Card>
      </div>

      {/* ---- Model controls + health ---- */}
      <div className="space-y-4">
        <Card title="Detection">
          <div className="mb-3 inline-flex items-center gap-1 rounded-lg border border-zinc-700 p-0.5">
            {MODELS.map((m) => (
              <button
                key={m.key}
                onClick={() => pickModel(m.key)}
                className={`rounded-md px-2.5 py-1 text-xs font-semibold transition ${
                  model === m.key ? "bg-sky-500 text-sky-950" : "text-zinc-400 hover:bg-zinc-800"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>

          {needsPrompt ? (
            <div className="mb-3">
              <p className="mb-1.5 text-[11px] font-medium text-zinc-400">Target part</p>
              <PartSelector value={prompt} onChange={setPrompt} allowCustom={model === "sam3" || model === "locateanything"} disabled={busy !== null} />
            </div>
          ) : (
            <p className="mb-3 text-[12px] leading-snug text-zinc-500">
              YOLO uses its fixed COCO-80 vocabulary — it won't recognise the disassembly parts. Use SAM 3 or LocateAnything
              (open-vocab) with the part selector for those.
            </p>
          )}

          <button
            onClick={infer}
            disabled={!canInfer}
            className="w-full rounded-lg bg-emerald-500 px-3 py-2 text-sm font-semibold text-emerald-950 transition hover:bg-emerald-400 disabled:opacity-40"
          >
            {busy === "infer" ? "Running…" : `Run ${MODELS.find((m) => m.key === model)!.label}`}
          </button>
          {!scene && <p className="mt-2 text-[11px] text-zinc-600">Capture a scene first.</p>}
        </Card>

        <Card title="Perception stack">
          <div className="space-y-3">
            <ServiceInfo serviceKey="yolo" title="YOLO" desc="Fast object detection — COCO-80 boxes." health={health} />
            <ServiceInfo serviceKey="sam3" title="SAM 3" desc="Promptable segmentation — text/points/boxes → masks." health={health} />
            <ServiceInfo serviceKey="locateanything" title="LocateAnything" desc="Open-vocab localisation from a text query." health={health} />
          </div>
        </Card>
      </div>
    </div>
  );
}
