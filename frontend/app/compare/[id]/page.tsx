"use client";

import { use, useEffect, useRef, useState } from "react";
import { AgentTimeline } from "@/components/AgentTimeline";
import { MarketCard } from "@/components/MarketCard";
import { RiskMatrix } from "@/components/RiskMatrix";
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

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">Comparison</h1>
        <span className="muted text-xs">id: {id}</span>
      </div>

      <AgentTimeline events={events} />

      {error ? (
        <div className="panel border-red-500/40 bg-red-500/10 p-4 text-sm text-red-300">
          {error}
        </div>
      ) : null}

      {input ? (
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide muted">
            Input market
          </h2>
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
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide muted">
          Structural risk matrix
        </h2>
        {matrix ? (
          <RiskMatrix rows={matrix.rows} />
        ) : (
          <div className="panel p-6 muted">
            {status === "running" || status === "pending"
              ? "Running agents…"
              : "No results yet."}
          </div>
        )}
      </section>
    </div>
  );
}
