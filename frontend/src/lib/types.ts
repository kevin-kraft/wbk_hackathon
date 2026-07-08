// Shared types across the dashboard.

export type ServiceKey =
  | "orchestrator"
  | "yolo"
  | "sam3"
  | "locateanything"
  | "foundationpose"
  | "gigapose"
  | "damage"
  | "movement"
  | "grip"
  | "movementSim"
  | "gripSim"
  | "sceneCapture";

export type StreamKey = "sceneCamera" | "inspectionCamera";

// Where scene images come from: the real Zivid (scene_camera /capture) or the
// simulator's render endpoint. Gates the scene-preview + perception capture.
export type SourceMode = "real" | "sim";

// Detection overlay drawn on a captured scene image.
export type OverlayKind = "boxes" | "masks";

// Which robot the loop drives: the real Jetson arm, the simulator, or both in
// parallel (real authoritative + sim mirrored as a digital twin). Mirrors the
// orchestrator's ROBOT_TARGET / ?target= query param.
export type RobotTarget = "real" | "sim" | "both";

export interface RuntimeConfig {
  services: Record<ServiceKey, string>;
  streams: Record<StreamKey, string>;
  run: { dryRun: boolean; stepDelayMs: number; robotTarget: RobotTarget };
  // Shared API token sent to the orchestrator (Bearer header on POST, ?token= on
  // SSE). Empty = don't send one. Matches the services' WBK_API_TOKEN.
  apiToken: string;
}

// A partial config layer (config.json, env, or localStorage overrides). Every
// section is optional and independently sparse — merge() fills the rest from the
// defaults, so e.g. overriding just `run.stepDelayMs` is valid.
export interface ConfigPatch {
  services?: Partial<Record<ServiceKey, string>>;
  streams?: Partial<Record<StreamKey, string>>;
  run?: Partial<RuntimeConfig["run"]>;
  apiToken?: string;
}

// --- Orchestrator loop events (mirrors orchestrator/models.py:LoopEvent) ---

export type LoopState =
  | "LOCATE"
  | "POSE"
  | "GRIP"
  | "REGRASP"
  | "REMOVE"
  | "RECHECK"
  | "SORT"
  | "SKIP"
  | "BLOCKED"
  | "SIM_WARN"
  | "DONE"
  | "SUMMARY";

export interface LoopEvent {
  step: number;
  state: LoopState | string;
  message: string;
  data: Record<string, unknown>;
}

export interface RunStats {
  removed: number;
  ok_bin: number;
  reject_bin: number;
  skipped: number;
  [k: string]: number;
}

export type HealthStatus = "up" | "down" | "unknown";

// --- Perception /infer results (mirror perception/services/shared/schemas.py) ---
// All boxes are xyxy in ABSOLUTE pixels, top-left origin; scale by width/height.

export interface BBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface YoloDetection {
  box: BBox;
  score: number;
  class_id: number;
  label: string;
}
export interface YoloResponse {
  detections: YoloDetection[];
  width: number;
  height: number;
  model: string;
  inference_ms: number;
}

export interface Sam3Mask {
  mask_b64_png: string; // single-channel (L) PNG, full-res, base64 (no data-URI)
  score: number;
  box?: BBox | null;
  label?: string | null;
}
export interface Sam3Response {
  masks: Sam3Mask[];
  width: number;
  height: number;
  model: string;
  inference_ms: number;
}

export interface LocateLocation {
  point: { x: number; y: number; label?: string };
  box?: BBox | null;
  score: number;
  label: string;
}
export interface LocateResponse {
  locations: LocateLocation[];
  width: number;
  height: number;
  model: string;
  inference_ms: number;
}

// scene_camera /capture (real) or the sim scene-capture contract.
export interface SceneCapture {
  rgb_b64: string; // base64 PNG (no data-URI prefix)
  depth_b64?: string | null; // uint16-mm PNG, base64
  K?: number[] | null;
  width?: number;
  height?: number;
  backend?: string;
}
