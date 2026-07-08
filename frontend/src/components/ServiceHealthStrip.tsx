import type { ServiceKey } from "../lib/types";
import type { HealthMap } from "../hooks/useServiceHealth";
import { Dot } from "./ui";

const SHORT: Record<ServiceKey, string> = {
  orchestrator: "orch",
  yolo: "yolo",
  sam3: "sam3",
  locateanything: "locate",
  foundationpose: "fpose",
  gigapose: "giga",
  damage: "damage",
  movement: "move",
  grip: "grip",
  movementSim: "move·sim",
  gripSim: "grip·sim",
  sceneCapture: "zivid",
};

export default function ServiceHealthStrip({ health }: { health: HealthMap }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      {(Object.keys(SHORT) as ServiceKey[]).map((k) => (
        <span key={k} className="flex items-center gap-1.5 text-[11px] text-zinc-400" title={`${k}: ${health[k]}`}>
          <Dot status={health[k]} />
          {SHORT[k]}
        </span>
      ))}
    </div>
  );
}
