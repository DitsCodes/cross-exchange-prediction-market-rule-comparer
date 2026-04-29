import type { ExtractedRules, Exchange } from "@/lib/types";

interface Props {
  exchange: Exchange | null;
  title: string | null;
  url: string | null;
  expirationTs: string | null;
  rules: ExtractedRules;
}

const EXCHANGE_LABELS: Record<string, string> = {
  polymarket: "Polymarket",
  kalshi: "Kalshi",
};

export function MarketCard({ exchange, title, url, expirationTs, rules }: Props) {
  const expDate = expirationTs ? new Date(expirationTs) : null;
  return (
    <article className="panel p-6">
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1">
        {exchange ? (
          <span className="inline-flex items-center gap-1.5 rounded-md border border-[var(--border)] bg-[var(--panel-2)] px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--text)]">
            <span
              aria-hidden
              className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--accent)]"
            />
            {EXCHANGE_LABELS[exchange] ?? exchange}
          </span>
        ) : null}
        {expDate ? (
          <span className="muted tabular text-xs">
            Expires{" "}
            <time dateTime={expirationTs!}>
              {expDate.toLocaleDateString(undefined, {
                year: "numeric",
                month: "short",
                day: "numeric",
              })}
            </time>
          </span>
        ) : null}
      </div>
      <h3 className="text-lg font-semibold leading-snug tracking-tight">
        {url ? (
          <a
            className="hover:underline focus-ring"
            href={url}
            rel="noreferrer"
            target="_blank"
          >
            {title || "(untitled)"}
          </a>
        ) : (
          title || "(untitled)"
        )}
      </h3>
      <dl className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Resolution source" value={rules.resolution_source_primary} />
        <Field label="Fallback source" value={rules.resolution_source_fallback} />
        <Field label="Tiebreak rule" value={rules.tiebreak_rule} />
        <Field label="Dead-heat rule" value={rules.dead_heat_rule} />
        <Field label="Settlement window" value={rules.settlement_window} />
        <Field label="Postponement" value={rules.postponement_handling} />
      </dl>
      {rules.scope_summary ? (
        <p className="muted mt-5 border-t border-[var(--border)] pt-4 text-sm leading-relaxed italic">
          {rules.scope_summary}
        </p>
      ) : null}
    </article>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel-2 px-3 py-2.5">
      <dt className="muted text-[10px] font-semibold uppercase tracking-[0.14em]">
        {label}
      </dt>
      <dd className="mt-1 text-sm leading-snug">
        {value || <span className="muted">—</span>}
      </dd>
    </div>
  );
}
