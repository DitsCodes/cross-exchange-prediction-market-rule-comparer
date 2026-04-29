"use client";

import { useState } from "react";
import type { RiskRow } from "@/lib/types";
import { ArbitrageBadge, DivergenceBadge } from "./DivergenceBadge";

const DIMENSIONS: { key: string; label: string }[] = [
  { key: "resolution_source", label: "Resolution source" },
  { key: "tiebreak", label: "Tiebreak / dead-heat" },
  { key: "expiration", label: "Expiration" },
  { key: "scope", label: "Scope" },
];

export function RiskMatrix({ rows }: { rows: RiskRow[] }) {
  if (!rows.length) {
    return (
      <div className="panel p-6 text-center muted">
        No cross-exchange candidates passed the similarity threshold yet.
      </div>
    );
  }
  return (
    <div className="panel overflow-x-auto">
      <div className="grid min-w-[820px] grid-cols-[2fr,repeat(4,minmax(0,1.1fr)),0.9fr] gap-px bg-[var(--border)]">
        <Header>Candidate</Header>
        {DIMENSIONS.map((d) => (
          <Header key={d.key}>{d.label}</Header>
        ))}
        <Header>Verdict</Header>
        {rows.map((row) => (
          <Row key={row.candidate.market_id} row={row} />
        ))}
      </div>
    </div>
  );
}

function Header({ children }: { children: React.ReactNode }) {
  return (
    <div className="bg-[var(--panel)] px-3 py-2 text-[11px] font-semibold uppercase tracking-wide muted">
      {children}
    </div>
  );
}

function Row({ row }: { row: RiskRow }) {
  const [open, setOpen] = useState(false);
  const toggle = () => setOpen((v) => !v);
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      toggle();
    }
  };
  return (
    <>
      <div
        role="button"
        tabIndex={0}
        aria-expanded={open}
        onClick={toggle}
        onKeyDown={onKey}
        className="focus-ring col-span-full grid cursor-pointer grid-cols-[2fr,repeat(4,minmax(0,1.1fr)),0.9fr] gap-px bg-[var(--border)] text-left transition-colors hover:bg-[var(--panel-2)]"
      >
        <CandidateCell row={row} />
        {DIMENSIONS.map((d) => {
          const dim = row.dimensions[d.key];
          if (!dim) {
            return (
              <div key={d.key} className="bg-[var(--panel)] px-3 py-3">
                <span className="muted text-xs">—</span>
              </div>
            );
          }
          return (
            <div key={d.key} className="bg-[var(--panel)] px-3 py-3">
              <DivergenceBadge level={dim.divergence} />
              <div className="muted mt-1.5 text-xs leading-snug">{dim.note}</div>
            </div>
          );
        })}
        <div className="flex items-center justify-between bg-[var(--panel)] px-3 py-3">
          <ArbitrageBadge flag={row.arbitrage_flag} />
          <span
            aria-hidden
            className={`muted text-xs transition-transform ${open ? "rotate-180" : ""}`}
          >
            ▾
          </span>
        </div>
      </div>
      {open ? (
        <div className="col-span-full bg-[var(--panel-2)] px-6 py-5">
          <div className="muted mb-2 text-[11px] font-semibold uppercase tracking-[0.18em]">
            Rationale
          </div>
          <p className="mb-5 text-sm leading-relaxed">{row.rationale}</p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {DIMENSIONS.map((d) => {
              const dim = row.dimensions[d.key];
              if (!dim) return null;
              return (
                <div key={d.key} className="panel-2 p-4">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <div className="text-xs font-semibold">{d.label}</div>
                    <DivergenceBadge level={dim.divergence} />
                  </div>
                  <DimRow label="Input" value={dim.input} />
                  <DimRow label="Candidate" value={dim.candidate} />
                  {dim.note ? (
                    <p className="muted mt-2 text-xs italic leading-snug">{dim.note}</p>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </>
  );
}

function CandidateCell({ row }: { row: RiskRow }) {
  return (
    <div className="bg-[var(--panel)] px-3 py-3">
      <div className="muted tabular text-[10px] font-semibold uppercase tracking-[0.14em]">
        {row.candidate.exchange} · sim {Math.round(row.candidate.similarity * 100)}%
      </div>
      <div className="mt-1 text-sm font-medium leading-snug">
        {row.candidate.url ? (
          <a
            className="focus-ring hover:underline"
            href={row.candidate.url}
            rel="noreferrer"
            target="_blank"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
          >
            {row.candidate.title}
          </a>
        ) : (
          row.candidate.title
        )}
      </div>
    </div>
  );
}

function DimRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-xs">
      <span className="muted mr-1">{label}:</span>
      {value || <span className="muted">—</span>}
    </div>
  );
}
