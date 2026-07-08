import { useEffect, useRef, useState } from "react";
import type { BBox, OverlayKind } from "../lib/types";

// Distinct overlay colours, cycled per instance.
const COLORS: [number, number, number][] = [
  [56, 189, 248], // sky
  [251, 191, 36], // amber
  [52, 211, 153], // emerald
  [244, 114, 182], // pink
  [167, 139, 250], // violet
  [248, 113, 113], // red
];
const css = (c: [number, number, number]) => `rgb(${c[0]},${c[1]},${c[2]})`;

export interface BoxOverlay {
  box: BBox;
  label?: string;
  score?: number;
}
export interface PointOverlay {
  x: number;
  y: number;
  label?: string;
}

// Renders a captured scene image (RGB or depth) with box/mask/point overlays,
// aligned in the image's native pixel space so coordinates from /infer map 1:1.
export default function SceneView({
  rgbB64,
  depthB64,
  showDepth,
  overlayKind,
  boxes,
  masks,
  points,
}: {
  rgbB64: string;
  depthB64?: string | null;
  showDepth?: boolean;
  overlayKind: OverlayKind;
  boxes?: BoxOverlay[];
  masks?: string[];
  points?: PointOverlay[];
}) {
  const [dims, setDims] = useState<{ w: number; h: number } | null>(null);
  const w = dims?.w ?? 1;
  const h = dims?.h ?? 1;
  const stroke = Math.max(2, w / 320);
  const font = Math.max(11, w / 55);

  return (
    <div className="relative w-full overflow-hidden rounded-lg bg-black">
      <img
        src={`data:image/png;base64,${rgbB64}`}
        alt="scene"
        onLoad={(e) => setDims({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
        className="block w-full"
      />

      {showDepth && depthB64 && (
        <DepthCanvas b64={depthB64} className="absolute inset-0 h-full w-full" />
      )}

      {overlayKind === "masks" && masks && masks.length > 0 && dims && (
        <MaskCanvas masks={masks} width={w} height={h} className="pointer-events-none absolute inset-0 h-full w-full" />
      )}

      {overlayKind === "boxes" && dims && (
        <svg
          viewBox={`0 0 ${w} ${h}`}
          preserveAspectRatio="none"
          className="pointer-events-none absolute inset-0 h-full w-full"
        >
          {boxes?.map((b, i) => {
            const c = css(COLORS[i % COLORS.length]);
            const bw = b.box.x2 - b.box.x1;
            const label = b.label
              ? b.score != null
                ? `${b.label} ${(b.score * 100).toFixed(0)}%`
                : b.label
              : undefined;
            return (
              <g key={i}>
                <rect
                  x={b.box.x1}
                  y={b.box.y1}
                  width={bw}
                  height={b.box.y2 - b.box.y1}
                  fill="none"
                  stroke={c}
                  strokeWidth={stroke}
                />
                {label && (
                  <>
                    <rect x={b.box.x1} y={Math.max(0, b.box.y1 - font * 1.4)} width={label.length * font * 0.6} height={font * 1.4} fill={c} />
                    <text x={b.box.x1 + font * 0.25} y={Math.max(font, b.box.y1 - font * 0.35)} fontSize={font} fill="#0a0a0a" fontWeight={700}>
                      {label}
                    </text>
                  </>
                )}
              </g>
            );
          })}
          {points?.map((p, i) => (
            <circle key={`p${i}`} cx={p.x} cy={p.y} r={Math.max(4, w / 120)} fill={css(COLORS[i % COLORS.length])} stroke="#0a0a0a" strokeWidth={stroke / 2} />
          ))}
        </svg>
      )}
    </div>
  );
}

// Composites per-instance single-channel mask PNGs, each in a distinct colour.
function MaskCanvas({ masks, width, height, className }: { masks: string[]; width: number; height: number; className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    cv.width = width;
    cv.height = height;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, width, height);
    let cancelled = false;
    masks.forEach((m, i) => {
      const img = new Image();
      img.onload = () => {
        if (cancelled) return;
        const tmp = document.createElement("canvas");
        tmp.width = width;
        tmp.height = height;
        const tctx = tmp.getContext("2d");
        if (!tctx) return;
        tctx.drawImage(img, 0, 0, width, height);
        const data = tctx.getImageData(0, 0, width, height);
        const px = data.data;
        const [r, g, b] = COLORS[i % COLORS.length];
        for (let p = 0; p < px.length; p += 4) {
          if (px[p] > 127) {
            px[p] = r;
            px[p + 1] = g;
            px[p + 2] = b;
            px[p + 3] = 150;
          } else {
            px[p + 3] = 0;
          }
        }
        tctx.putImageData(data, 0, 0);
        ctx.drawImage(tmp, 0, 0);
      };
      img.src = `data:image/png;base64,${m}`;
    });
    return () => {
      cancelled = true;
    };
  }, [masks, width, height]);
  return <canvas ref={ref} className={className} />;
}

// Renders a 16-bit-mm depth PNG as a normalised heatmap (min–max stretch over
// non-zero pixels). Browsers downsample 16-bit to 8-bit, so this is a display
// aid, not metric depth.
function DepthCanvas({ b64, className }: { b64: string; className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    let cancelled = false;
    const img = new Image();
    img.onload = () => {
      if (cancelled) return;
      const w = img.naturalWidth;
      const h = img.naturalHeight;
      cv.width = w;
      cv.height = h;
      const ctx = cv.getContext("2d");
      if (!ctx) return;
      ctx.drawImage(img, 0, 0);
      const data = ctx.getImageData(0, 0, w, h);
      const px = data.data;
      let min = 255;
      let max = 0;
      for (let p = 0; p < px.length; p += 4) {
        const v = px[p];
        if (v > 0) {
          if (v < min) min = v;
          if (v > max) max = v;
        }
      }
      const span = Math.max(1, max - min);
      for (let p = 0; p < px.length; p += 4) {
        const v = px[p];
        if (v === 0) {
          px[p] = px[p + 1] = px[p + 2] = 10; // no-data → near black
          px[p + 3] = 255;
          continue;
        }
        const t = Math.min(1, Math.max(0, (v - min) / span));
        const [r, g, b] = turbo(t);
        px[p] = r;
        px[p + 1] = g;
        px[p + 2] = b;
        px[p + 3] = 255;
      }
      ctx.putImageData(data, 0, 0);
    };
    img.src = `data:image/png;base64,${b64}`;
    return () => {
      cancelled = true;
    };
  }, [b64]);
  return <canvas ref={ref} className={className} />;
}

// Compact blue→cyan→green→yellow→red colormap.
function turbo(t: number): [number, number, number] {
  const r = Math.round(255 * Math.min(1, Math.max(0, 1.5 - Math.abs(2 * t - 1.5))));
  const g = Math.round(255 * Math.min(1, Math.max(0, 1.5 - Math.abs(2 * t - 1.0))));
  const b = Math.round(255 * Math.min(1, Math.max(0, 1.5 - Math.abs(2 * t - 0.5))));
  return [r, g, b];
}
