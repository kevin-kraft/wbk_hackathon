import type { SourceMode } from "../lib/types";

// Picks where scene images come from: the real Zivid or the simulator.
export default function SourceToggle({
  value,
  onChange,
  disabled,
}: {
  value: SourceMode;
  onChange: (v: SourceMode) => void;
  disabled?: boolean;
}) {
  const opts: { value: SourceMode; label: string; title: string }[] = [
    { value: "real", label: "Real", title: "Real Zivid camera (scene_camera service)" },
    { value: "sim", label: "Sim", title: "Simulator render (Isaac scene)" },
  ];
  return (
    <div className="inline-flex items-center gap-1 rounded-lg border border-zinc-700 p-0.5">
      {opts.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          disabled={disabled}
          title={o.title}
          className={`rounded-md px-2.5 py-1 text-xs font-semibold transition disabled:opacity-40 ${
            value === o.value ? "bg-sky-500 text-sky-950" : "text-zinc-400 hover:bg-zinc-800"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
