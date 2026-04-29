import type { StreamEvent } from "@/lib/types";

const STEP_LABELS: Record<string, string> = {
  fetcher: "1. Fetch market",
  retriever: "2. Find similar markets",
  extractor: "3. Extract structured rules",
  synthesizer: "4. Synthesize risk matrix",
};

export function AgentTimeline({ events }: { events: StreamEvent[] }) {
  return (
    <ol className="panel divide-y divide-[var(--border)]">
      {Object.entries(STEP_LABELS).map(([key, label]) => {
        const evts = events
          .filter((e) => e.type === "step" && (e.data as any)?.step === key)
          .map((e) => e.data as { step: string; status: string; [k: string]: unknown });
        const last = evts[evts.length - 1];
        const status = last?.status ?? "pending";
        const dotColor =
          status === "ok"
            ? "bg-emerald-500"
            : status === "error"
              ? "bg-red-500"
              : status === "start"
                ? "bg-amber-400 animate-pulse"
                : "bg-zinc-600";
        return (
          <li key={key} className="flex items-center gap-3 px-4 py-3">
            <span className={`h-2.5 w-2.5 rounded-full ${dotColor}`} />
            <div className="flex-1">
              <div className="text-sm font-medium">{label}</div>
              {last ? (
                <div className="muted text-xs">{describe(last)}</div>
              ) : (
                <div className="muted text-xs">waiting</div>
              )}
            </div>
            <div className="muted text-[11px] uppercase tracking-wide">{status}</div>
          </li>
        );
      })}
    </ol>
  );
}

function describe(evt: { step: string; status: string; [k: string]: unknown }): string {
  if (evt.status === "error") return String(evt.message || "failed");
  if (evt.step === "fetcher" && evt.status === "ok")
    return `${evt.exchange} · ${evt.title}`;
  if (evt.step === "retriever" && evt.status === "ok")
    return `${evt.candidates} candidates`;
  if (evt.step === "extractor" && evt.status === "ok")
    return `${evt.count} rule blocks extracted`;
  if (evt.step === "synthesizer" && evt.status === "ok")
    return `${evt.rows} risk rows`;
  if (evt.status === "start") return "running...";
  return evt.status;
}
