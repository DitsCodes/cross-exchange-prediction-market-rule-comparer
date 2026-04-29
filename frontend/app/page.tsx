import { UrlInput } from "@/components/UrlInput";

export default function HomePage() {
  return (
    <div className="space-y-16">
      <section className="max-w-3xl">
        <p className="muted mb-4 text-xs font-semibold uppercase tracking-[0.18em]">
          Cross-exchange rules diff
        </p>
        <h1 className="font-serif text-4xl leading-[1.1] tracking-tight sm:text-5xl">
          Compare prediction market settlement rules
          <br className="hidden sm:block" />
          <span className="text-[var(--accent)]"> across exchanges.</span>
        </h1>
        <p className="muted mt-5 max-w-xl text-base leading-relaxed">
          Paste a Polymarket or Kalshi URL. RuleC retrieves similar markets on the
          opposite exchange and surfaces divergences in resolution source,
          tie-breaking rules, and expiration timestamps.
        </p>
        <div className="mt-8">
          <UrlInput />
        </div>
      </section>

      <section
        aria-label="How it works"
        className="border-t border-[var(--border)] pt-10"
      >
        <ol className="grid grid-cols-1 gap-x-10 gap-y-6 text-sm sm:grid-cols-3">
          <PipelineStep
            n="01"
            title="Fetch"
            body="Polymarket Gamma + Kalshi v2 return the canonical metadata."
          />
          <PipelineStep
            n="02"
            title="Retrieve"
            body="Voyage embeddings + pgvector search find cross-exchange neighbors."
          />
          <PipelineStep
            n="03"
            title="Synthesize"
            body="A LangGraph supervisor extracts rules and scores divergences."
          />
        </ol>
      </section>
    </div>
  );
}

function PipelineStep({
  n,
  title,
  body,
}: {
  n: string;
  title: string;
  body: string;
}) {
  return (
    <li className="flex gap-4">
      <span className="tabular muted shrink-0 text-xs font-semibold tracking-wider">
        {n}
      </span>
      <div>
        <div className="text-sm font-semibold text-[var(--text)]">{title}</div>
        <p className="muted mt-1 leading-relaxed">{body}</p>
      </div>
    </li>
  );
}
