import { useState } from "react";

// Renders an MJPEG/still stream in a plain <img>. Scene + inspection cameras are
// just URLs from the runtime config, so any host works.
export default function MjpegView({
  src,
  label,
  aspect = "aspect-video",
}: {
  src: string;
  label: string;
  aspect?: string;
}) {
  const [errored, setErrored] = useState(false);

  return (
    <div className={`relative ${aspect} w-full overflow-hidden rounded-lg bg-zinc-950 ring-1 ring-zinc-800`}>
      {src && !errored ? (
        <img
          src={src}
          alt={label}
          onError={() => setErrored(true)}
          className="h-full w-full object-contain"
        />
      ) : (
        <div className="flex h-full flex-col items-center justify-center gap-1 text-center">
          <span className="text-3xl opacity-30">🎥</span>
          <span className="text-xs text-zinc-500">{label}</span>
          <span className="text-[11px] text-zinc-600">
            {src ? "stream unavailable" : "no URL configured (Settings)"}
          </span>
        </div>
      )}
      <span className="absolute left-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-zinc-300">
        {label}
      </span>
    </div>
  );
}
