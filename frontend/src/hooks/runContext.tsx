// App-level run state so the live loop persists across page navigation
// (Dashboard, Inspection, Perception all read the same stream).

import { createContext, useContext, useState, type ReactNode } from "react";
import { useRunStream, type RunStreamState } from "./useRunStream";
import { getConfig } from "../config/runtime";
import type { LocalizationMode, PosePipeline, RobotTarget, SourceMode } from "../lib/types";

interface RunContextValue extends RunStreamState {
  dryRun: boolean;
  setDryRun: (v: boolean) => void;
  delayMs: number;
  setDelayMs: (v: number) => void;
  robotTarget: RobotTarget;
  setRobotTarget: (v: RobotTarget) => void;
  // Pose stage pipeline (6DoF rgbd/rgb, or CAD-free 2d planar), shared across pages.
  posePipeline: PosePipeline;
  setPosePipeline: (v: PosePipeline) => void;
  // Localization mode (pose stage vs depth-free slot lookup), shared across pages.
  localization: LocalizationMode;
  setLocalization: (v: LocalizationMode) => void;
  // Scene-image source (real Zivid vs simulator), shared across pages.
  sourceMode: SourceMode;
  setSourceMode: (v: SourceMode) => void;
  prompt: string;
  setPrompt: (v: string) => void;
  // Plan-driven runs: selected ERP product ("" = manual, perception-driven mode).
  product: string;
  setProduct: (v: string) => void;
}

const RunContext = createContext<RunContextValue | null>(null);

export function RunProvider({ children }: { children: ReactNode }) {
  const cfg = getConfig();
  const stream = useRunStream();
  const [dryRun, setDryRun] = useState(cfg.run.dryRun);
  const [delayMs, setDelayMs] = useState(cfg.run.stepDelayMs);
  const [robotTarget, setRobotTarget] = useState<RobotTarget>(cfg.run.robotTarget);
  const [posePipeline, setPosePipeline] = useState<PosePipeline>(cfg.run.posePipeline);
  const [localization, setLocalization] = useState<LocalizationMode>(cfg.run.localization);
  // Default the scene source to the sim when the robot target is sim, else real.
  const [sourceMode, setSourceMode] = useState<SourceMode>(cfg.run.robotTarget === "sim" ? "sim" : "real");
  const [prompt, setPrompt] = useState("");
  const [product, setProduct] = useState("");

  return (
    <RunContext.Provider
      value={{
        ...stream,
        dryRun,
        setDryRun,
        delayMs,
        setDelayMs,
        robotTarget,
        setRobotTarget,
        posePipeline,
        setPosePipeline,
        localization,
        setLocalization,
        sourceMode,
        setSourceMode,
        prompt,
        setPrompt,
        product,
        setProduct,
      }}
    >
      {children}
    </RunContext.Provider>
  );
}

export function useRun(): RunContextValue {
  const ctx = useContext(RunContext);
  if (!ctx) throw new Error("useRun must be used within RunProvider");
  return ctx;
}
