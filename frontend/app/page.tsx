import { UrlInput } from "@/components/UrlInput";

export default function HomePage() {
  return (
    <div className="space-y-10">
      <section className="panel p-8">
        <h1 className="text-2xl font-semibold tracking-tight">
          Compare prediction market settlement rules across exchanges.
        </h1>
        <p className="muted mt-3 max-w-2xl text-sm leading-relaxed">
          Paste a Polymarket or Kalshi URL. RuleC fetches the market via API, retrieves
          similar markets on the opposite exchange from a fresh embedding catalog, and
          generates a Structural Risk Matrix that highlights divergences in resolution
          source, dead-heat tie-breaking rules, and expiration timestamps.
        </p>
        <div className="mt-6">
          <UrlInput />
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Step
          n="1"
          title="Fetch"
          body="Polymarket Gamma + Kalshi v2 APIs return the canonical market metadata."
        />
        <Step
          n="2"
          title="Retrieve"
          body="Voyage AI embeddings + pgvector cosine search find cross-exchange neighbors above the similarity threshold."
        />
        <Step
          n="3"
          title="Synthesize"
          body="A LangGraph supervisor of Claude sub-agents extracts structured rules and scores per-dimension divergences."
        />
      </section>
    </div>
  );
}

function Step({ n, title, body }: { n: string; title: string; body: string }) {
  return (
    <div className="panel p-5">
      <div className="muted mb-1 text-xs uppercase tracking-wide">Step {n}</div>
      <div className="mb-2 text-base font-semibold">{title}</div>
      <p className="muted text-sm leading-relaxed">{body}</p>
    </div>
  );
}
