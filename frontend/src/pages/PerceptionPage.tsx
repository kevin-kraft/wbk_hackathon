import { useServiceHealth } from "../hooks/useServiceHealth";
import { streamUrl } from "../config/runtime";
import { Card } from "../components/ui";
import ServiceInfo from "../components/ServiceInfo";
import MjpegView from "../components/MjpegView";

export default function PerceptionPage() {
  const { health } = useServiceHealth();

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div className="lg:col-span-2">
        <Card title="Scene camera" right={<span className="text-[11px] text-zinc-500">detection overlays: future</span>}>
          <MjpegView src={streamUrl("sceneCamera")} label="scene" />
          <p className="mt-3 text-[12px] leading-snug text-zinc-500">
            Live view of the assembly. YOLO boxes, SAM 3 masks, and the LocateAnything next-part
            highlight will render as overlays here once the perception services stream detections.
          </p>
        </Card>
      </div>

      <div className="space-y-3">
        <Card title="Perception stack">
          <div className="space-y-3">
            <ServiceInfo
              serviceKey="yolo"
              title="YOLO"
              desc="Fast object detection — bounding boxes for known part classes (teammate-owned model)."
              health={health}
            />
            <ServiceInfo
              serviceKey="sam3"
              title="SAM 3"
              desc="Promptable segmentation — masks for a located part; before/after presence check on removal."
              health={health}
            />
            <ServiceInfo
              serviceKey="locateanything"
              title="LocateAnything"
              desc="Open-vocabulary localisation — picks the next part to remove from a text query."
              health={health}
            />
          </div>
        </Card>
      </div>
    </div>
  );
}
