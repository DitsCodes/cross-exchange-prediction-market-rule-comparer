import type { ExtractedRules, Exchange } from "@/lib/types";

interface Props {
  exchange: Exchange | null;
  title: string | null;
  url: string | null;
  expirationTs: string | null;
  rules: ExtractedRules;
}

export function MarketCard({ exchange, title, url, expirationTs, rules }: Props) {
  return (
    <div className="panel p-5">
      <div className="mb-2 flex items-center gap-3">
        {exchange ? (
          <span
            className={`rounded-md border px-2 py-0.5 text-xs font-medium uppercase tracking-wide ${
              exchange === "polymarket"
                ? "border-indigo-500/40 bg-indigo-500/10 text-indigo-300"
                : "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
            }`}
          >
            {exchange}
          </span>
        ) : null}
        {expirationTs ? (
          <span className="muted text-xs">
            expires{" "}
            <time dateTime={expirationTs}>
              {new Date(expirationTs).toUTCString()}
            </time>
          </span>
        ) : null}
      </div>
      <h2 className="text-lg font-semibold leading-snug">
        {url ? (
          <a className="hover:underline" href={url} rel="noreferrer" target="_blank">
            {title || "(untitled)"}
          </a>
        ) : (
          title || "(untitled)"
        )}
      </h2>
      <dl className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Resolution source" value={rules.resolution_source_primary} />
        <Field label="Fallback source" value={rules.resolution_source_fallback} />
        <Field label="Tiebreak rule" value={rules.tiebreak_rule} />
        <Field label="Dead-heat rule" value={rules.dead_heat_rule} />
        <Field label="Settlement window" value={rules.settlement_window} />
        <Field label="Postponement" value={rules.postponement_handling} />
      </dl>
      {rules.scope_summary ? (
        <p className="muted mt-4 text-sm italic">{rules.scope_summary}</p>
      ) : null}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel-2 px-3 py-2">
      <div className="muted text-[11px] uppercase tracking-wide">{label}</div>
      <div className="mt-0.5 text-sm">{value || <span className="muted">—</span>}</div>
    </div>
  );
}
