// Operator product selection (the "ERP" head of the pipeline): pick a product
// to run plan-driven, or "Manual" to keep the original perception-driven loop.
// Products come from the orchestrator's GET /products (mock-ERP dataset).

import { useEffect, useState } from "react";
import { fetchProducts } from "../lib/api";
import type { ErpProduct } from "../lib/types";

export default function ProductSelector({
  value,
  onChange,
  disabled,
}: {
  value: string; // "" = manual mode
  onChange: (v: string) => void;
  disabled: boolean;
}) {
  const [products, setProducts] = useState<ErpProduct[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchProducts()
      .then((p) => {
        if (!cancelled) setProducts(p);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = products.find((p) => p.id === value);

  return (
    <label
      className="flex items-center gap-2 text-sm text-zinc-300"
      title={
        error
          ? `Product list unavailable (${error}) — manual mode only`
          : "ERP product: the orchestrator generates + executes a per-product disassembly plan. Manual = perception picks parts."
      }
    >
      Product
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled || Boolean(error)}
        className="rounded-lg border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200 disabled:opacity-40"
      >
        <option value="">Manual (no plan)</option>
        {products.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
      {selected && (
        <span className="hidden text-[11px] text-zinc-500 xl:inline">
          {selected.parts.length} parts
        </span>
      )}
    </label>
  );
}
