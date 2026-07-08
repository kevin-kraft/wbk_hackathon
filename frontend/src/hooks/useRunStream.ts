// Subscribes to the orchestrator's SSE run stream and accumulates loop events.
//
// Each `start()` opens a fresh EventSource to GET /events/run, which triggers a
// new loop server-side. We MUST close the source on the "end" event, otherwise
// EventSource auto-reconnects and would kick off another run.

import { useCallback, useEffect, useRef, useState } from "react";
import type { LoopEvent, RobotTarget, RunStats } from "../lib/types";
import { runStreamUrl } from "../lib/api";

export type RunStatus = "idle" | "running" | "done" | "error";

export interface RunStreamState {
  status: RunStatus;
  events: LoopEvent[];
  stats: RunStats | null;
  latest: LoopEvent | null;
  error: string | null;
  // Robot the server actually drove this run (from the SSE "start" event) — may
  // differ from the requested toggle if ROBOT_TARGET was forced server-side.
  activeTarget: string | null;
  start: (dryRun: boolean, delaySeconds: number, target?: RobotTarget, product?: string) => void;
  stop: () => void;
  reset: () => void;
}

export function useRunStream(): RunStreamState {
  const [status, setStatus] = useState<RunStatus>("idle");
  const [events, setEvents] = useState<LoopEvent[]>([]);
  const [stats, setStats] = useState<RunStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTarget, setActiveTarget] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const closeSource = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
  }, []);

  const stop = useCallback(() => {
    closeSource();
    setStatus((s) => (s === "running" ? "idle" : s));
  }, [closeSource]);

  const reset = useCallback(() => {
    closeSource();
    setEvents([]);
    setStats(null);
    setError(null);
    setActiveTarget(null);
    setStatus("idle");
  }, [closeSource]);

  const start = useCallback(
    (dryRun: boolean, delaySeconds: number, target?: RobotTarget, product?: string) => {
      closeSource();
      setEvents([]);
      setStats(null);
      setError(null);
      setActiveTarget(null);
      setStatus("running");

      const es = new EventSource(runStreamUrl(dryRun, delaySeconds, target, product));
      esRef.current = es;

      es.addEventListener("start", (e) => {
        try {
          setActiveTarget((JSON.parse((e as MessageEvent).data) as { target?: string }).target ?? null);
        } catch {
          /* ignore malformed start frame */
        }
      });
      es.addEventListener("event", (e) => {
        const ev = JSON.parse((e as MessageEvent).data) as LoopEvent;
        setEvents((prev) => [...prev, ev]);
      });
      es.addEventListener("summary", (e) => {
        setStats(JSON.parse((e as MessageEvent).data) as RunStats);
      });
      es.addEventListener("error", (e) => {
        // Named "error" event from the server (a run failure), not a transport error.
        const msg = e as MessageEvent;
        if (msg?.data) {
          try {
            setError((JSON.parse(msg.data) as { error: string }).error);
          } catch {
            setError("run error");
          }
          setStatus("error");
          closeSource();
        }
      });
      es.addEventListener("end", () => {
        setStatus((s) => (s === "error" ? s : "done"));
        closeSource();
      });
      es.onerror = () => {
        // Transport-level error (server unreachable / stream dropped mid-run).
        if (esRef.current) {
          setStatus((s) => {
            if (s === "running") {
              setError("connection to orchestrator lost");
              return "error";
            }
            return s;
          });
          closeSource();
        }
      };
    },
    [closeSource],
  );

  useEffect(() => () => closeSource(), [closeSource]);

  const latest = events.length ? events[events.length - 1] : null;
  return { status, events, stats, latest, error, activeTarget, start, stop, reset };
}
