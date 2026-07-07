// Thin fetch helpers bound to the runtime config.

import type { HealthStatus, ServiceKey } from "./types";
import { serviceUrl, apiToken } from "../config/runtime";

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

/** POST {orchestrator}/run — non-streaming full run (returns events + stats). */
export async function runOnce(dryRun: boolean): Promise<{ stats: Record<string, number>; events: unknown[] }> {
  const base = serviceUrl("orchestrator");
  const res = await fetch(`${base}/run?dry_run=${dryRun}`, { method: "POST", headers: authHeaders() });
  if (!res.ok) throw new Error(`run failed: HTTP ${res.status}`);
  return res.json();
}

/** URL for the SSE streaming run endpoint. The token rides as a query param
 * because EventSource can't set an Authorization header. */
export function runStreamUrl(dryRun: boolean, delaySeconds: number): string {
  const base = serviceUrl("orchestrator");
  const delay = Math.max(0, delaySeconds);
  let url = `${base}/events/run?dry_run=${dryRun}&delay=${delay}`;
  const t = apiToken();
  if (t) url += `&token=${encodeURIComponent(t)}`;
  return url;
}
