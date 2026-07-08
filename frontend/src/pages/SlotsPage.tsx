// Slot-localization calibration + visualization.
//
// The depth-free pipeline: a fixed tray whose slots have known pixel centres and
// known base-frame coordinates. This page lets you (1) place each slot's pixel
// on a real captured frame, (2) record its measured base pose, and (3) run SAM3
// occupancy to see which slots read as filled — the exact signal the orchestrator
// uses in localization=slots mode.

import { useEffect, useRef, useState } from "react";
import { useRun } from "../hooks/runContext";
import {
  captureScene,
  fetchSlotLayout,
  runSlotOccupancy,
  saveSlotLayout,
  SIM_NOT_IMPLEMENTED,
} from "../lib/api";
import type { SlotLayout, SlotOccupancyResponse, SlotSpec } from "../lib/types";
import { Card } from "../components/ui";

const EMPTY_LAYOUT: SlotLayout = {
  name: "default_tray",
  image_size: null,
  mask_source: "sam3",
  defaults: { radius_px: 22, fill_frac: 0.35 },
  slots: [],
};

function friendlyError(e: unknown): string {
  const m = e instanceof Error ? e.message : String(e);
  if (m === SIM_NOT_IMPLEMENTED) return "Scene capture isn't available in sim mode — switch the source to real, or upload an image.";
  return m;
}

export default function SlotsPage() {
  const run = useRun();
  const [layout, setLayout] = useState<SlotLayout>(EMPTY_LAYOUT);
  const [imageB64, setImageB64] = useState<string | null>(null);
  const [imgNatural, setImgNatural] = useState<[number, number] | null>(null);
  const [occ, setOcc] = useState<SlotOccupancyResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [maskSource, setMaskSource] = useState<string>("sam3");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    fetchSlotLayout()
      .then((l) => {
        setLayout({ ...EMPTY_LAYOUT, ...l });
        setMaskSource(l.mask_source || "sam3");
        if (l.slots?.length) setSelectedId(l.slots[0].id);
      })
      .catch((e) => setErr(friendlyError(e)));
  }, []);

  // Working image size: the calibration resolution, else the loaded image's
  // native size, else a sane default. Slot pixels are stored in THIS space.
  const size = layout.image_size ?? imgNatural ?? [1280, 720];
  const [W, H] = size;

  function patchLayout(patch: Partial<SlotLayout>) {
    setLayout((l) => ({ ...l, ...patch }));
  }

  function updateSlot(id: string, patch: Partial<SlotSpec>) {
    setLayout((l) => ({ ...l, slots: l.slots.map((s) => (s.id === id ? { ...s, ...patch } : s)) }));
  }

  function addSlot() {
    const base = `S${layout.slots.length + 1}`;
    let id = base;
    let n = layout.slots.length + 1;
    while (layout.slots.some((s) => s.id === id)) id = `S${++n}`;
    const slot: SlotSpec = {
      id,
      expected_class: "",
      pixel: [Math.round(W / 2), Math.round(H / 2)],
      base_xyz_m: [0, 0, 0],
      yaw_deg: 0,
    };
    setLayout((l) => ({ ...l, slots: [...l.slots, slot] }));
    setSelectedId(id);
  }

  function removeSlot(id: string) {
    setLayout((l) => ({ ...l, slots: l.slots.filter((s) => s.id !== id) }));
    if (selectedId === id) setSelectedId(null);
  }

  function onImageClick(e: React.MouseEvent<HTMLImageElement>) {
    if (!selectedId || !imgRef.current) return;
    const rect = imgRef.current.getBoundingClientRect();
    const fx = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    const fy = Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height));
    updateSlot(selectedId, { pixel: [Math.round(fx * W), Math.round(fy * H)] });
  }

  async function capture() {
    setBusy("capture");
    setErr(null);
    setOcc(null);
    try {
      const s = await captureScene(run.sourceMode);
      setImageB64(s.rgb_b64);
    } catch (e) {
      setErr(friendlyError(e));
    } finally {
      setBusy(null);
    }
  }

  async function upload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBusy("capture");
    setErr(null);
    setOcc(null);
    try {
      const dataUrl = await new Promise<string>((resolve, reject) => {
        const fr = new FileReader();
        fr.onload = () => resolve(fr.result as string);
        fr.onerror = () => reject(new Error(`Could not read ${file.name}`));
        fr.readAsDataURL(file);
      });
      const b64 = dataUrl.replace(/^data:[^;]+;base64,/, "");
      if (!b64) throw new Error("Empty or unreadable image file");
      setImageB64(b64);
    } catch (e) {
      setErr(friendlyError(e));
    } finally {
      setBusy(null);
    }
  }

  async function runOccupancy() {
    if (!imageB64) return;
    setBusy("occ");
    setErr(null);
    try {
      setOcc(await runSlotOccupancy(imageB64, maskSource));
    } catch (e) {
      setErr(friendlyError(e));
    } finally {
      setBusy(null);
    }
  }

  async function save() {
    setBusy("save");
    setErr(null);
    setMsg(null);
    try {
      const out = { ...layout, mask_source: maskSource };
      const res = await saveSlotLayout(out);
      setMsg(`Saved ${res.slots} slot(s) to the orchestrator.`);
    } catch (e) {
      setErr(friendlyError(e));
    } finally {
      setBusy(null);
    }
  }

  function exportJson() {
    const blob = new Blob([JSON.stringify({ ...layout, mask_source: maskSource }, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "slot_layout.json";
    a.click();
    URL.revokeObjectURL(url);
  }

  const occById = new Map((occ?.slots ?? []).map((s) => [s.slot_id, s]));
  const selected = layout.slots.find((s) => s.id === selectedId) ?? null;

  function markerColor(id: string): string {
    const o = occById.get(id);
    if (!o) return "border-zinc-300 bg-zinc-500/30";
    if (!o.filled) return "border-zinc-400 bg-zinc-700/40";
    return o.identity_ok ? "border-emerald-300 bg-emerald-500/40" : "border-amber-300 bg-amber-500/40";
  }

  return (
    <div className="space-y-4">
      <Card title="Slot localization — calibration & occupancy">
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={capture}
            disabled={busy !== null}
            className="rounded-lg bg-sky-500 px-3 py-1.5 text-sm font-semibold text-sky-950 transition hover:bg-sky-400 disabled:opacity-40"
          >
            {busy === "capture" ? "Capturing…" : "Capture frame"}
          </button>
          <label className="cursor-pointer rounded-lg border border-zinc-700 px-3 py-1.5 text-sm font-medium text-zinc-300 transition hover:bg-zinc-800">
            Upload image
            <input type="file" accept="image/*" onChange={upload} className="hidden" />
          </label>
          <button
            onClick={runOccupancy}
            disabled={busy !== null || !imageB64}
            className="rounded-lg bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-emerald-950 transition hover:bg-emerald-400 disabled:opacity-40"
          >
            {busy === "occ" ? "Scoring…" : "Run occupancy"}
          </button>
          <div className="flex items-center gap-1 rounded-lg border border-zinc-700 p-0.5" title="Mask source for occupancy">
            <span className="px-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Masks</span>
            {["sam3", "yoloseg"].map((m) => (
              <button
                key={m}
                onClick={() => setMaskSource(m)}
                className={`rounded-md px-2 py-1 text-xs font-semibold transition ${
                  maskSource === m ? "bg-sky-500 text-sky-950" : "text-zinc-400 hover:bg-zinc-800"
                }`}
              >
                {m}
              </button>
            ))}
          </div>
          <span className="ml-auto text-[11px] text-zinc-500">
            calibrated at <span className="font-mono text-zinc-300">{W}×{H}</span>
            {occ && <> · <span className="font-mono text-emerald-300">{occ.filled}</span> filled</>}
          </span>
        </div>
        {err && (
          <p className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">{err}</p>
        )}
        {msg && (
          <p className="mt-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">{msg}</p>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card
          title={selectedId ? `Click the image to place slot ${selectedId}` : "Select a slot, then click to place it"}
          className="lg:col-span-2"
        >
          {imageB64 ? (
            <div className="relative inline-block max-w-full select-none">
              <img
                ref={imgRef}
                src={`data:image/png;base64,${imageB64}`}
                alt="scene"
                onLoad={(e) => {
                  const el = e.currentTarget;
                  setImgNatural([el.naturalWidth, el.naturalHeight]);
                  if (!layout.image_size) patchLayout({ image_size: [el.naturalWidth, el.naturalHeight] });
                }}
                onClick={onImageClick}
                className={`max-h-[70vh] w-auto rounded-lg ${selectedId ? "cursor-crosshair" : "cursor-default"}`}
              />
              {layout.slots.map((s) => {
                const o = occById.get(s.id);
                return (
                  <button
                    key={s.id}
                    onClick={(ev) => {
                      ev.stopPropagation();
                      setSelectedId(s.id);
                    }}
                    title={o ? `${s.id}: ${o.filled ? o.detected_class ?? "filled" : "empty"} (${(o.fill_score * 100).toFixed(0)}%)` : s.id}
                    style={{ left: `${(s.pixel[0] / W) * 100}%`, top: `${(s.pixel[1] / H) * 100}%` }}
                    className={`absolute -translate-x-1/2 -translate-y-1/2 grid h-6 w-6 place-items-center rounded-full border-2 text-[9px] font-bold text-white shadow ${markerColor(
                      s.id,
                    )} ${selectedId === s.id ? "ring-2 ring-sky-400 ring-offset-1 ring-offset-zinc-900" : ""}`}
                  >
                    {s.id}
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="grid h-64 place-items-center rounded-lg border border-dashed border-zinc-700 text-center text-sm text-zinc-600">
              Capture a frame or upload an image to calibrate slot positions.
            </div>
          )}
          <div className="mt-3 flex flex-wrap gap-3 text-[11px] text-zinc-500">
            <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full border-2 border-emerald-300 bg-emerald-500/40" /> filled · right part</span>
            <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full border-2 border-amber-300 bg-amber-500/40" /> filled · wrong part</span>
            <span className="flex items-center gap-1.5"><span className="h-3 w-3 rounded-full border-2 border-zinc-400 bg-zinc-700/40" /> empty</span>
          </div>
        </Card>

        <Card
          title="Slots"
          right={
            <button onClick={addSlot} className="rounded-md bg-zinc-800 px-2 py-1 text-xs font-semibold text-zinc-200 hover:bg-zinc-700">
              + Add
            </button>
          }
        >
          <div className="space-y-1.5">
            {layout.slots.length === 0 && <p className="text-sm text-zinc-500">No slots yet — add one.</p>}
            {layout.slots.map((s) => {
              const o = occById.get(s.id);
              return (
                <button
                  key={s.id}
                  onClick={() => setSelectedId(s.id)}
                  className={`flex w-full items-center justify-between rounded-lg border px-3 py-1.5 text-left text-sm transition ${
                    selectedId === s.id ? "border-sky-500 bg-sky-500/10" : "border-zinc-800 hover:bg-zinc-800/50"
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full ${o ? (o.filled ? (o.identity_ok ? "bg-emerald-400" : "bg-amber-400") : "bg-zinc-600") : "bg-zinc-700"}`} />
                    <span className="font-mono text-zinc-200">{s.id}</span>
                    <span className="text-zinc-500">{s.expected_class || "—"}</span>
                  </span>
                  {o?.filled && <span className="font-mono text-[11px] text-zinc-400">{(o.fill_score * 100).toFixed(0)}%</span>}
                </button>
              );
            })}
          </div>

          {selected && (
            <div className="mt-4 space-y-2 border-t border-zinc-800 pt-3">
              <Field label="Slot id">
                <input
                  value={selected.id}
                  onChange={(e) => {
                    const id = e.target.value;
                    updateSlot(selected.id, { id });
                    setSelectedId(id);
                  }}
                  className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm text-zinc-100"
                />
              </Field>
              <Field label="Expected class">
                <input
                  value={selected.expected_class}
                  onChange={(e) => updateSlot(selected.id, { expected_class: e.target.value })}
                  placeholder="e.g. poltopf_kurz"
                  className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm text-zinc-100"
                />
              </Field>
              <Field label="Pixel (u, v)">
                <span className="font-mono text-sm text-zinc-300">
                  {selected.pixel[0]}, {selected.pixel[1]} <span className="text-zinc-600">(click image)</span>
                </span>
              </Field>
              <Field label="Base xyz (m)">
                <div className="flex gap-1">
                  {[0, 1, 2].map((i) => (
                    <input
                      key={i}
                      type="number"
                      step="0.001"
                      value={selected.base_xyz_m[i]}
                      onChange={(e) => {
                        const xyz = [...selected.base_xyz_m] as [number, number, number];
                        xyz[i] = Number(e.target.value);
                        updateSlot(selected.id, { base_xyz_m: xyz });
                      }}
                      className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm text-zinc-100"
                    />
                  ))}
                </div>
              </Field>
              <div className="flex gap-2">
                <Field label="Yaw (deg)">
                  <input
                    type="number"
                    step="1"
                    value={selected.yaw_deg ?? 0}
                    onChange={(e) => updateSlot(selected.id, { yaw_deg: Number(e.target.value) })}
                    className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm text-zinc-100"
                  />
                </Field>
                <Field label="Radius (px)">
                  <input
                    type="number"
                    step="1"
                    value={selected.radius_px ?? layout.defaults?.radius_px ?? 22}
                    onChange={(e) => updateSlot(selected.id, { radius_px: Number(e.target.value) })}
                    className="w-full rounded-md border border-zinc-700 bg-zinc-950 px-2 py-1 text-sm text-zinc-100"
                  />
                </Field>
              </div>
              <button
                onClick={() => removeSlot(selected.id)}
                className="w-full rounded-md border border-rose-500/40 px-2 py-1 text-xs font-semibold text-rose-300 hover:bg-rose-500/10"
              >
                Remove slot
              </button>
            </div>
          )}

          <div className="mt-4 flex gap-2 border-t border-zinc-800 pt-3">
            <button
              onClick={save}
              disabled={busy !== null}
              className="flex-1 rounded-lg bg-sky-500 px-3 py-1.5 text-sm font-semibold text-sky-950 transition hover:bg-sky-400 disabled:opacity-40"
            >
              {busy === "save" ? "Saving…" : "Save to server"}
            </button>
            <button
              onClick={exportJson}
              className="rounded-lg border border-zinc-700 px-3 py-1.5 text-sm font-medium text-zinc-300 transition hover:bg-zinc-800"
            >
              Export JSON
            </button>
          </div>
        </Card>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider text-zinc-500">{label}</span>
      {children}
    </label>
  );
}
