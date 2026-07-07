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
  | "grip";

export type StreamKey = "sceneCamera" | "inspectionCamera";

export interface RuntimeConfig {
  services: Record<ServiceKey, string>;
  streams: Record<StreamKey, string>;
  run: { dryRun: boolean; stepDelayMs: number };
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
