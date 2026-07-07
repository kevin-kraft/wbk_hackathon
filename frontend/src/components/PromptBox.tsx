import { useState } from "react";

// Free-text prompt that will drive VLM next-part selection ("remove the top
// cover first"). The orchestrator seam exists (PerceptionClient.next_part /
// NEXT_PART_QUERY); wiring it to a VLM backend is future work, so for now this
// captures intent and previews the feature.
export default function PromptBox({
  value,
  onChange,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  const [saved, setSaved] = useState(false);

  return (
    <div className="space-y-2">
      <textarea
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setSaved(false);
        }}
        disabled={disabled}
        rows={2}
        placeholder="e.g. remove the top cover first, then the screws…"
        className="w-full resize-none rounded-lg border border-zinc-700 bg-zinc-950/60 px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:border-sky-500 focus:outline-none disabled:opacity-50"
      />
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-zinc-500">
          Guides which part to disassemble next.{" "}
          <span className="text-amber-400/80">VLM backend: future</span>
        </span>
        <button
          onClick={() => setSaved(true)}
          disabled={disabled || !value.trim()}
          className="rounded-md border border-zinc-700 px-2.5 py-1 text-xs font-medium text-zinc-300 transition hover:bg-zinc-800 disabled:opacity-40"
        >
          {saved ? "Saved ✓" : "Set intent"}
        </button>
      </div>
    </div>
  );
}
