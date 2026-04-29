"use client";

import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";
import { AgentTimeline } from "@/components/AgentTimeline";
import { MarketCard } from "@/components/MarketCard";
import { RiskMatrix } from "@/components/RiskMatrix";
import { RiskMatrixSkeleton } from "@/components/RiskMatrixSkeleton";
import { getCompare, streamCompareUrl } from "@/lib/api";
import type { CompareResult, RiskMatrix as RiskMatrixType, StreamEvent } from "@/lib/types";

export default function ComparePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [matrix, setMatrix] = useState<RiskMatrixType | null>(null);
  const [status, setStatus] = useState<CompareResult["status"]>("pending");
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCompare(id)
      .then((res) => {
        if (cancelled) return;
        setStatus(res.status);
        if (res.risk_matrix) setMatrix(res.risk_matrix);
        if (res.error) setError(res.error);
        if (res.status === "pending" || res.status === "running") {
          openStream();
        }
      })
      .catch((e) => setError((e as Error).message));

    function openStream() {
      const es = new EventSource(streamCompareUrl(id));
      esRef.current = es;
      const consume = (raw: string, type: StreamEvent["type"]) => {
        try {
          const data = JSON.parse(raw);
          setEvents((prev) => [...prev, { type, data }]);
          if (type === "result") {
            setMatrix(data as RiskMatrixType);
            setStatus("done");
            es.close();
          } else if (type === "error") {
            setError(typeof data === "string" ? data : JSON.stringify(data));
            setStatus("error");
            es.close();
          }
        } catch {
          /* ignore malformed event */
        }
      };
      es.addEventListener("started", (e) => consume((e as MessageEvent).data, "started"));
      es.addEventListener("step", (e) => consume((e as MessageEvent).data, "step"));
      es.addEventListener("result", (e) => consume((e as MessageEvent).data, "result"));
      es.addEventListener("error", (e) => {
        const msg = (e as MessageEvent).data;
        if (typeof msg === "string") consume(msg, "error");
        else {
          setStatus("error");
          es.close();
        }
      });
    }

    return () => {
      cancelled = true;
      esRef.current?.close();
    };
  }, [id]);

  const input = matrix?.input ?? null;
  const heading = input?.title || "Comparison";
  const isWorking = status === "pending" || status === "running";

  return (
    <div className="space-y-10">
      <div className="space-y-3">
        <Link
          href="/"
          className="muted focus-ring inline-flex items-center gap-1 text-sm hover:text-white"
        >
          <span aria-hidden>←</span> New comparison
        </Link>
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h1 className="font-serif text-3xl leading-tight tracking-tight">
            {heading}
          </h1>
          <span className="muted tabular text-[11px] uppercase tracking-wide">
            run · {id.slice(0, 8)}
          </span>
        </div>
      </div>

      <AgentTimeline events={events} />

      {error ? (
        <div role="alert" className="alert-error">
          <div>
            <div className="font-semibold text-[#fca5a5]">
              Couldn’t complete this comparison
            </div>
            <div className="mt-0.5 text-[var(--text-dim)]">{error}</div>
          </div>
        </div>
      ) : null}

      {input ? (
        <section>
          <SectionHeader>Input market</SectionHeader>
          <MarketCard
            exchange={input.exchange}
            title={input.title}
            url={input.url}
            expirationTs={input.expiration_ts}
            rules={input.rules}
          />
        </section>
      ) : null}

      <section>
        <SectionHeader>Structural risk matrix</SectionHeader>
        {matrix ? (
          <RiskMatrix rows={matrix.rows} />
        ) : isWorking ? (
          <RiskMatrixSkeleton />
        ) : (
          <div className="panel p-8 text-center">
            <div className="muted text-sm">No results yet.</div>
            <Link href="/" className="btn-secondary focus-ring mt-4 inline-flex">
              Start a new comparison
            </Link>
          </div>
        )}
      </section>
    </div>
  );
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="muted mb-3 text-xs font-semibold uppercase tracking-[0.18em]">
      {children}
    </h2>
  );
}
