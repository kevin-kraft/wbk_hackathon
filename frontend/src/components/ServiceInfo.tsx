import type { ServiceKey } from "../lib/types";
import type { HealthMap } from "../hooks/useServiceHealth";
import { serviceUrl } from "../config/runtime";
import { Dot } from "./ui";

export default function ServiceInfo({
  serviceKey,
  title,
  desc,
  health,
}: {
  serviceKey: ServiceKey;
  title: string;
  desc: string;
  health: HealthMap;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/40 p-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-zinc-200">{title}</span>
        <span className="flex items-center gap-1.5 text-[11px] text-zinc-400">
          <Dot status={health[serviceKey]} />
          {health[serviceKey]}
        </span>
      </div>
      <p className="mt-1 text-[12px] leading-snug text-zinc-500">{desc}</p>
      <code className="mt-2 block truncate rounded bg-zinc-900 px-2 py-1 font-mono text-[11px] text-zinc-400">
        {serviceUrl(serviceKey) || "— not configured —"}
      </code>
    </div>
  );
}
