// Polls each service's /health on an interval.

import { useCallback, useEffect, useState } from "react";
import type { HealthStatus, ServiceKey } from "../lib/types";
import { checkHealth } from "../lib/api";
import { SERVICE_KEYS } from "../config/runtime";

export type HealthMap = Record<ServiceKey, HealthStatus>;

function initialMap(): HealthMap {
  return Object.fromEntries(SERVICE_KEYS.map((k) => [k, "unknown"])) as HealthMap;
}

export function useServiceHealth(intervalMs = 5000): { health: HealthMap; refresh: () => void } {
  const [health, setHealth] = useState<HealthMap>(initialMap);

  const refresh = useCallback(() => {
    for (const key of SERVICE_KEYS) {
      checkHealth(key).then((status) =>
        setHealth((prev) => (prev[key] === status ? prev : { ...prev, [key]: status })),
      );
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
  }, [refresh, intervalMs]);

  return { health, refresh };
}
