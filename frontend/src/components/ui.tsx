// Small styling primitives shared across pages.
import type { ReactNode } from "react";

export function Card({
  title,
  right,
  children,
  className = "",
}: {
  title?: ReactNode;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rounded-xl border border-zinc-800 bg-zinc-900/50 shadow-sm ${className}`}
    >
      {(title || right) && (
        <header className="flex items-center justify-between gap-2 border-b border-zinc-800 px-4 py-2.5">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-400">{title}</h2>
          {right}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Dot({ status }: { status: "up" | "down" | "unknown" }) {
  const color =
    status === "up" ? "bg-emerald-400" : status === "down" ? "bg-rose-500" : "bg-zinc-600";
  const ring =
    status === "up" ? "shadow-[0_0_0_3px_rgba(52,211,153,0.15)]" : "";
  return <span className={`inline-block h-2.5 w-2.5 rounded-full ${color} ${ring}`} />;
}

export function Stat({ label, value, tone = "default" }: { label: string; value: ReactNode; tone?: "default" | "ok" | "reject" | "muted" }) {
  const toneClass =
    tone === "ok"
      ? "text-emerald-300"
      : tone === "reject"
        ? "text-rose-300"
        : tone === "muted"
          ? "text-zinc-500"
          : "text-zinc-100";
  return (
    <div className="rounded-lg bg-zinc-950/60 px-3 py-2.5 ring-1 ring-zinc-800">
      <div className="text-[10px] font-medium uppercase tracking-wider text-zinc-500">{label}</div>
      <div className={`mt-0.5 text-2xl font-semibold tabular-nums ${toneClass}`}>{value}</div>
    </div>
  );
}
