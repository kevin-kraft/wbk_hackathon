// Runtime endpoint configuration.
//
// Every microservice may live on a different host, so the dashboard must be
// re-pointable WITHOUT a rebuild. Resolution order (later wins):
//
//   1. localhost fallbacks (so a bare `npm run dev` shows something)
//   2. build-time VITE_* env vars (baked defaults)
//   3. public/config.json          <- edit this on the deployed machine
//   4. localStorage overrides       <- edited live from the Settings page
//
// loadConfig() is awaited once in main.tsx before the app renders.

import type { ConfigPatch, RuntimeConfig, ServiceKey, StreamKey } from "../lib/types";

const OVERRIDE_KEY = "wbk.config.overrides";

const SERVICE_KEYS: ServiceKey[] = [
  "orchestrator",
  "yolo",
  "sam3",
  "locateanything",
  "foundationpose",
  "gigapose",
  "damage",
  "movement",
  "grip",
  "movementSim",
  "gripSim",
  "sceneCapture",
];

const STREAM_KEYS: StreamKey[] = ["sceneCamera", "inspectionCamera"];

function localhostDefaults(): RuntimeConfig {
  return {
    services: {
      orchestrator: "http://localhost:8000",
      yolo: "http://localhost:8001",
      sam3: "http://localhost:8002",
      locateanything: "http://localhost:8003",
      foundationpose: "http://localhost:8004",
      gigapose: "http://localhost:8005",
      damage: "http://localhost:8006",
      movement: "http://localhost:9000",
      grip: "http://localhost:9001",
      // Simulator endpoints — blank until the sim lands; health tiles read
      // "unknown" and the sim/both run modes stay unavailable until set.
      movementSim: "",
      gripSim: "",
      // Real Zivid RGB-D capture service (scene_camera, POST /capture).
      sceneCapture: "http://localhost:9002",
    },
    streams: { sceneCamera: "", inspectionCamera: "" },
    run: { dryRun: true, stepDelayMs: 700, robotTarget: "real" },
    apiToken: "",
  };
}

const ENV = import.meta.env as Record<string, string | undefined>;

function envDefaults(): ConfigPatch {
  const svcEnv: Record<string, string | undefined> = {
    orchestrator: ENV.VITE_ORCHESTRATOR_URL,
    yolo: ENV.VITE_YOLO_URL,
    sam3: ENV.VITE_SAM3_URL,
    locateanything: ENV.VITE_LOCATEANYTHING_URL,
    foundationpose: ENV.VITE_FOUNDATIONPOSE_URL,
    gigapose: ENV.VITE_GIGAPOSE_URL,
    damage: ENV.VITE_DAMAGE_URL,
    movement: ENV.VITE_MOVEMENT_URL,
    grip: ENV.VITE_GRIP_URL,
    movementSim: ENV.VITE_MOVEMENT_SIM_URL,
    gripSim: ENV.VITE_GRIP_SIM_URL,
    sceneCapture: ENV.VITE_SCENE_CAPTURE_URL,
  };
  const services: Partial<Record<ServiceKey, string>> = {};
  for (const k of SERVICE_KEYS) if (svcEnv[k]) services[k] = svcEnv[k]!;

  const streams: Partial<Record<StreamKey, string>> = {};
  if (ENV.VITE_SCENE_CAMERA_URL) streams.sceneCamera = ENV.VITE_SCENE_CAMERA_URL;
  if (ENV.VITE_INSPECTION_CAMERA_URL) streams.inspectionCamera = ENV.VITE_INSPECTION_CAMERA_URL;

  const patch: ConfigPatch = { services, streams };
  if (ENV.VITE_API_TOKEN) patch.apiToken = ENV.VITE_API_TOKEN;
  return patch;
}

// Deep-ish merge limited to our known shape (services / streams / run).
function merge(base: RuntimeConfig, patch?: ConfigPatch | null): RuntimeConfig {
  if (!patch) return base;
  return {
    services: { ...base.services, ...(patch.services ?? {}) },
    streams: { ...base.streams, ...(patch.streams ?? {}) },
    run: { ...base.run, ...(patch.run ?? {}) },
    apiToken: patch.apiToken ?? base.apiToken,
  };
}

function stripTrailingSlashes(cfg: RuntimeConfig): RuntimeConfig {
  const clean = (u: string) => (u ? u.replace(/\/+$/, "") : u);
  for (const k of SERVICE_KEYS) cfg.services[k] = clean(cfg.services[k]);
  for (const k of STREAM_KEYS) cfg.streams[k] = clean(cfg.streams[k]);
  return cfg;
}

export function getOverrides(): ConfigPatch | null {
  try {
    const raw = localStorage.getItem(OVERRIDE_KEY);
    return raw ? (JSON.parse(raw) as ConfigPatch) : null;
  } catch {
    return null;
  }
}

/** Persist Settings-page overrides. Caller reloads the app to apply. */
export function saveOverrides(patch: ConfigPatch): void {
  localStorage.setItem(OVERRIDE_KEY, JSON.stringify(patch));
}

export function clearOverrides(): void {
  localStorage.removeItem(OVERRIDE_KEY);
}

let current: RuntimeConfig = localhostDefaults();

export async function loadConfig(): Promise<RuntimeConfig> {
  let cfg = merge(localhostDefaults(), envDefaults());

  // public/config.json — relative fetch so it resolves under any base path.
  try {
    const res = await fetch("config.json", { cache: "no-store" });
    if (res.ok) {
      const fileCfg = (await res.json()) as ConfigPatch;
      cfg = merge(cfg, fileCfg);
    }
  } catch {
    // no config.json shipped — fall back to env/localhost defaults
  }

  cfg = merge(cfg, getOverrides());
  current = stripTrailingSlashes(cfg);
  return current;
}

export function getConfig(): RuntimeConfig {
  return current;
}

export function serviceUrl(key: ServiceKey): string {
  return current.services[key];
}

export function streamUrl(key: StreamKey): string {
  return current.streams[key];
}

export function apiToken(): string {
  return current.apiToken;
}

export { SERVICE_KEYS, STREAM_KEYS };
