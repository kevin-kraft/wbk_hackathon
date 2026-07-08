// App-level run state so the live loop persists across page navigation
// (Dashboard, Inspection, Perception all read the same stream).

import { createContext, useContext, useState, type ReactNode } from "react";
import { useRunStream, type RunStreamState } from "./useRunStream";
import { getConfig } from "../config/runtime";
import type { RobotTarget, SourceMode } from "../lib/types";

interface RunContextValue extends RunStreamState {
  dryRun: boolean;
  setDryRun: (v: boolean) => void;
  delayMs: number;
  setDelayMs: (v: number) => void;
  robotTarget: RobotTarget;
  setRobotTarget: (v: RobotTarget) => void;
  // Scene-image source (real Zivid vs simulator), shared across pages.
  sourceMode: SourceMode;
  setSourceMode: (v: SourceMode) => void;
  prompt: string;
  setPrompt: (v: string) => void;
}

const RunContext = createContext<RunContextValue | null>(null);

export function RunProvider({ children }: { children: ReactNode }) {
  const cfg = getConfig();
  const stream = useRunStream();
  const [dryRun, setDryRun] = useState(cfg.run.dryRun);
  const [delayMs, setDelayMs] = useState(cfg.run.stepDelayMs);
  const [robotTarget, setRobotTarget] = useState<RobotTarget>(cfg.run.robotTarget);
  // Default the scene source to the sim when the robot target is sim, else real.
  const [sourceMode, setSourceMode] = useState<SourceMode>(cfg.run.robotTarget === "sim" ? "sim" : "real");
  const [prompt, setPrompt] = useState("");

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
        sourceMode,
        setSourceMode,
        prompt,
        setPrompt,
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
