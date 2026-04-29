import type { StreamEvent } from "@/lib/types";

const STEP_LABELS: Record<string, string> = {
  fetcher: "Fetch market",
  retriever: "Find similar markets",
  extractor: "Extract structured rules",
  synthesizer: "Synthesize risk matrix",
};

const STEP_ORDER = Object.keys(STEP_LABELS);

export function AgentTimeline({ events }: { events: StreamEvent[] }) {
  return (
    <ol
      aria-label="Agent pipeline progress"
      className="panel divide-y divide-[var(--border)]"
    >
      {STEP_ORDER.map((key, idx) => {
        const evts = events
          .filter((e) => e.type === "step" && (e.data as any)?.step === key)
          .map((e) => e.data as { step: string; status: string; [k: string]: unknown });
        const last = evts[evts.length - 1];
        const status = (last?.status as string) ?? "pending";
        return (
          <li
            key={key}
            className="flex items-center gap-4 px-4 py-3"
            aria-current={status === "start" ? "step" : undefined}
          >
            <StatusDot status={status} />
            <div className="flex-1">
              <div className="flex items-baseline gap-2">
                <span className="muted tabular text-[11px] font-semibold tracking-wider">
                  {String(idx + 1).padStart(2, "0")}
                </span>
                <span className="text-sm font-medium">{STEP_LABELS[key]}</span>
              </div>
              <div className="muted mt-0.5 text-xs">
                {last ? describe(last) : "waiting"}
              </div>
            </div>
            <StatusBadge status={status} />
          </li>
        );
      })}
    </ol>
  );
}

function StatusDot({ status }: { status: string }) {
  if (status === "ok") {
    return (
      <span
        aria-hidden
        className="grid h-5 w-5 place-items-center rounded-full bg-emerald-500/15 text-[10px] text-emerald-400"
      >
        ✓
      </span>
    );
  }
  if (status === "error") {
    return (
      <span
        aria-hidden
        className="grid h-5 w-5 place-items-center rounded-full bg-red-500/15 text-[10px] text-red-300"
      >
        ✕
      </span>
    );
  }
  if (status === "start") {
    return (
      <span
        aria-hidden
        className="relative grid h-5 w-5 place-items-center"
      >
        <span className="absolute inset-0 rounded-full bg-[var(--accent)]/30 animate-ping" />
        <span className="relative h-2.5 w-2.5 rounded-full bg-[var(--accent)]" />
      </span>
    );
  }
  return (
    <span
      aria-hidden
      className="h-5 w-5 rounded-full border border-[var(--border)] bg-[var(--panel-2)]"
    />
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    ok: { label: "Done", cls: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30" },
    error: { label: "Failed", cls: "bg-red-500/10 text-red-300 border-red-500/30" },
    start: { label: "Running", cls: "bg-[var(--accent)]/10 text-[var(--accent)] border-[var(--accent)]/40" },
  };
  const conf = map[status] ?? {
    label: "Pending",
    cls: "bg-[var(--panel-2)] text-[var(--text-dim)] border-[var(--border)]",
  };
  return (
    <span
      className={`tabular inline-flex items-center rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${conf.cls}`}
    >
      {conf.label}
    </span>
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
  if (evt.status === "start") return "running…";
  return evt.status;
}
