// Thin fetch helpers bound to the runtime config.

import type {
  ErpProduct,
  HealthStatus,
  LocateResponse,
  PlanPreview,
  PosePipeline,
  RobotTarget,
  Sam3Response,
  SceneCapture,
  ServiceKey,
  SourceMode,
  YoloResponse,
  YoloSegResponse,
} from "./types";
import { serviceUrl, apiToken } from "../config/runtime";

/** Thrown when a sim-side endpoint isn't implemented yet (Group 2 to build). */
export const SIM_NOT_IMPLEMENTED = "SIM_NOT_IMPLEMENTED";

/** Bearer header for the shared token, or {} when none is configured. */
export function authHeaders(): Record<string, string> {
  const t = apiToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function withTimeout<T>(p: (signal: AbortSignal) => Promise<T>, ms: number): Promise<T> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), ms);
  try {
    return await p(ctrl.signal);
  } finally {
    clearTimeout(t);
  }
}

/** GET {service}/health — returns "up" only on a 2xx response. */
export async function checkHealth(key: ServiceKey, timeoutMs = 3000): Promise<HealthStatus> {
  const base = serviceUrl(key);
  if (!base) return "unknown";
  try {
    const res = await withTimeout(
      (signal) => fetch(`${base}/health`, { signal, cache: "no-store" }),
      timeoutMs,
    );
    return res.ok ? "up" : "down";
  } catch {
    return "down";
  }
}

/** POST {orchestrator}/run — non-streaming full run (returns events + stats).
 * `target` (real|sim|both) overrides which robot the loop drives for this run.
 * `product` switches to a plan-driven run (ERP + LLM plan, executed step by step). */
export async function runOnce(
  dryRun: boolean,
  target?: RobotTarget,
  product?: string,
  posePipeline?: PosePipeline,
): Promise<{ stats: Record<string, number>; target?: string; events: unknown[] }> {
  const base = serviceUrl("orchestrator");
  let url = `${base}/run?dry_run=${dryRun}`;
  if (target) url += `&target=${target}`;
  if (product) url += `&product=${encodeURIComponent(product)}`;
  if (posePipeline) url += `&pose_pipeline=${posePipeline}`;
  const res = await fetch(url, { method: "POST", headers: authHeaders() });
  if (!res.ok) throw new Error(`run failed: HTTP ${res.status}`);
  return res.json();
}

/** URL for the SSE streaming run endpoint. The token rides as a query param
 * because EventSource can't set an Authorization header. `target` picks the
 * robot (real|sim|both); `product` switches to a plan-driven run. */
export function runStreamUrl(
  dryRun: boolean,
  delaySeconds: number,
  target?: RobotTarget,
  product?: string,
  posePipeline?: PosePipeline,
): string {
  const base = serviceUrl("orchestrator");
  const delay = Math.max(0, delaySeconds);
  let url = `${base}/events/run?dry_run=${dryRun}&delay=${delay}`;
  if (target) url += `&target=${target}`;
  if (product) url += `&product=${encodeURIComponent(product)}`;
  if (posePipeline) url += `&pose_pipeline=${posePipeline}`;
  const t = apiToken();
  if (t) url += `&token=${encodeURIComponent(t)}`;
  return url;
}

/** GET {orchestrator}/products — the operator-selectable (mock-)ERP products. */
export async function fetchProducts(): Promise<ErpProduct[]> {
  const base = serviceUrl("orchestrator");
  const res = await fetch(`${base}/products`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`products failed: HTTP ${res.status}`);
  return ((await res.json()) as { products: ErpProduct[] }).products;
}

/** GET {orchestrator}/plan — preview the generated plan without executing it. */
export async function fetchPlan(product: string, dryRun: boolean): Promise<PlanPreview> {
  const base = serviceUrl("orchestrator");
  const res = await fetch(
    `${base}/plan?product=${encodeURIComponent(product)}&dry_run=${dryRun}`,
    { headers: authHeaders() },
  );
  if (!res.ok) throw new Error(`plan failed: HTTP ${res.status}`);
  return res.json();
}

// --- Perception inference ------------------------------------------------- //

/** POST {service}/infer with a JSON body. `image` is base64 (data-URI ok). */
async function postInfer<T>(key: ServiceKey, body: Record<string, unknown>): Promise<T> {
  const base = serviceUrl(key);
  if (!base) throw new Error(`${key} is not configured`);
  const res = await fetch(`${base}/infer`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${key} inference failed: HTTP ${res.status}`);
  return res.json();
}

// Low default conf: the parts models are trained on synthetic renders and score
// low on real Zivid frames (sim-to-real gap), so 0.25 hid almost everything.
export function runYolo(imageB64: string, opts: { conf?: number } = {}): Promise<YoloResponse> {
  return postInfer("yolo", { image_b64: imageB64, conf: opts.conf ?? 0.1 });
}

/** YOLO-Seg: trained parts instance segmentation (boxes + masks, closed-vocab). */
export function runYoloSeg(imageB64: string, opts: { conf?: number } = {}): Promise<YoloSegResponse> {
  return postInfer("yoloseg", { image_b64: imageB64, conf: opts.conf ?? 0.1 });
}

/** SAM3 text-prompted segmentation (open-vocab). */
export function runSam3(imageB64: string, text: string): Promise<Sam3Response> {
  return postInfer("sam3", { image_b64: imageB64, text });
}

/** LocateAnything text-prompted localisation (open-vocab). */
export function runLocate(imageB64: string, query: string, topK = 10): Promise<LocateResponse> {
  return postInfer("locateanything", { image_b64: imageB64, query, top_k: topK });
}

// --- Scene capture -------------------------------------------------------- //

/** Capture an RGB(-D) scene frame. Real → the Zivid scene_camera service; sim →
 * the sim backend's scene-capture contract (may be unimplemented → throws
 * SIM_NOT_IMPLEMENTED). See contracts/scene_camera_api.md + sim_scene_capture.md. */
export async function captureScene(mode: SourceMode): Promise<SceneCapture> {
  if (mode === "real") {
    const base = serviceUrl("sceneCapture");
    if (!base) throw new Error("scene capture service (Zivid) is not configured");
    const res = await fetch(`${base}/capture`, { method: "POST", headers: authHeaders() });
    if (!res.ok) throw new Error(`capture failed: HTTP ${res.status}`);
    return res.json();
  }
  const base = serviceUrl("movementSim");
  if (!base) throw new Error("sim backend is not configured");
  const res = await fetch(`${base}/simulation/scene/capture`, { method: "POST", headers: authHeaders() });
  if (res.status === 404 || res.status === 501) throw new Error(SIM_NOT_IMPLEMENTED);
  if (!res.ok) throw new Error(`sim capture failed: HTTP ${res.status}`);
  return res.json();
}

/** Sim-only: render a frontal, slightly-elevated overview of the arm + table.
 * Returns base64 image; throws SIM_NOT_IMPLEMENTED until Group 2 ships it. */
export async function generateScenePreview(): Promise<string> {
  const base = serviceUrl("movementSim");
  if (!base) throw new Error("sim backend is not configured");
  const res = await fetch(`${base}/simulation/scene/preview`, { method: "POST", headers: authHeaders() });
  if (res.status === 404 || res.status === 501) throw new Error(SIM_NOT_IMPLEMENTED);
  if (!res.ok) throw new Error(`sim preview failed: HTTP ${res.status}`);
  const data = (await res.json()) as { image_b64: string };
  return data.image_b64;
}
