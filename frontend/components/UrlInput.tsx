"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { createCompare } from "@/lib/api";

const EXAMPLES = [
  "https://polymarket.com/event/will-bitcoin-reach-100k-by-end-of-2026",
  "https://kalshi.com/markets/kxprez/2028-presidential-election",
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
      <label className="text-sm font-medium" htmlFor="market-url">
        Market URL
      </label>
      <div className="flex gap-2">
        <input
          id="market-url"
          name="market-url"
          className="input"
          placeholder="https://polymarket.com/... or https://kalshi.com/..."
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
          autoFocus
        />
        <button className="btn-primary whitespace-nowrap" type="submit" disabled={busy || !url}>
          {busy ? "Analyzing..." : "Compare"}
        </button>
      </div>
      <div className="muted text-xs">
        Try:
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            type="button"
            className="ml-2 underline decoration-dotted hover:text-white"
            onClick={() => setUrl(ex)}
          >
            {new URL(ex).hostname}
          </button>
        ))}
      </div>
      {error ? <div className="text-sm text-risk-high">{error}</div> : null}
    </form>
  );
}
