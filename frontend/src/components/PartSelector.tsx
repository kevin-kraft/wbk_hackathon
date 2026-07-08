import { SUPPORTED_PARTS } from "../lib/parts";

// Choose the target part for the open-vocab models (SAM3 / LocateAnything).
// Replaces a freeform text box with the fixed set of supported parts, plus a
// "custom" escape hatch for ad-hoc prompts.
export default function PartSelector({
  value,
  onChange,
  allowCustom = true,
  disabled,
}: {
  value: string;
  onChange: (prompt: string) => void;
  allowCustom?: boolean;
  disabled?: boolean;
}) {
  const isPreset = SUPPORTED_PARTS.some((p) => p.prompt === value);
  const custom = allowCustom && !isPreset;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {SUPPORTED_PARTS.map((p) => (
          <button
            key={p.id}
            onClick={() => onChange(p.prompt)}
            disabled={disabled}
            className={`rounded-full px-3 py-1 text-xs font-medium transition disabled:opacity-40 ${
              value === p.prompt
                ? "bg-sky-500 text-sky-950"
                : "border border-zinc-700 text-zinc-300 hover:bg-zinc-800"
            }`}
          >
            {p.label}
          </button>
        ))}
        {allowCustom && (
          <button
            onClick={() => onChange(custom ? value : "")}
            disabled={disabled}
            className={`rounded-full px-3 py-1 text-xs font-medium transition disabled:opacity-40 ${
              custom ? "bg-sky-500 text-sky-950" : "border border-zinc-700 text-zinc-300 hover:bg-zinc-800"
            }`}
          >
            Custom…
          </button>
        )}
      </div>
      {custom && (
        <input
          type="text"
          value={value}
          autoFocus
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          placeholder="free-text prompt"
          spellCheck={false}
          className="w-full rounded-lg border border-zinc-700 bg-zinc-950/60 px-3 py-1.5 text-xs text-zinc-200 focus:border-sky-500 focus:outline-none"
        />
      )}
    </div>
  );
}
