import type { Divergence } from "@/lib/types";

const COPY: Record<Divergence, string> = {
  low: "Aligned",
  medium: "Watch",
  high: "Divergent",
};

export function DivergenceBadge({
  level,
  label,
}: {
  level: Divergence;
  label?: string;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide divergence-${level}`}
    >
      {label ?? COPY[level]}
    </span>
  );
}

export function ArbitrageBadge({ flag }: { flag: "potential" | "none" }) {
  if (flag === "potential") {
    return <DivergenceBadge level="high" label="Arb potential" />;
  }
  return <DivergenceBadge level="low" label="No arb" />;
}
