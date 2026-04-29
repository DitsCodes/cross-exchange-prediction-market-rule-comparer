"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { createCompare } from "@/lib/api";

const EXAMPLES = [
  {
    label: "Polymarket",
    url: "https://polymarket.com/event/will-bitcoin-reach-100k-by-end-of-2026",
  },
  {
    label: "Kalshi",
    url: "https://kalshi.com/markets/kxprez/2028-presidential-election",
  },
];

export function UrlInput() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const { comparison_id } = await createCompare(url.trim());
      router.push(`/compare/${comparison_id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <label
        className="text-xs font-medium uppercase tracking-wide text-[var(--text-dim)]"
        htmlFor="market-url"
      >
        Market URL
      </label>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          id="market-url"
          name="market-url"
          className="input"
          type="url"
          inputMode="url"
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="off"
          spellCheck={false}
          placeholder="https://polymarket.com/... or https://kalshi.com/..."
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
          autoFocus
          aria-describedby="url-examples"
        />
        <button
          className="btn-primary whitespace-nowrap sm:px-6"
          type="submit"
          disabled={busy || !url}
        >
          {busy ? "Analyzing…" : "Compare"}
        </button>
      </div>
      <div id="url-examples" className="flex flex-wrap items-center gap-2 pt-1">
        <span className="muted text-xs">Try an example:</span>
        {EXAMPLES.map((ex) => (
          <button
            key={ex.url}
            type="button"
            className="btn-secondary focus-ring"
            onClick={() => setUrl(ex.url)}
          >
            {ex.label}
          </button>
        ))}
      </div>
      {error ? (
        <div role="alert" className="alert-error mt-1">
          <span className="font-semibold">Couldn’t start comparison:</span>
          <span>{error}</span>
        </div>
      ) : null}
    </form>
  );
}
