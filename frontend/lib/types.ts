export type Exchange = "polymarket" | "kalshi";
export type Divergence = "low" | "medium" | "high";

export interface DimensionDiff {
  input: string;
  candidate: string;
  divergence: Divergence;
  note: string;
}

export interface ExtractedRules {
  resolution_source_primary: string;
  resolution_source_fallback: string;
  tiebreak_rule: string;
  dead_heat_rule: string;
  expiration_ts_utc: string;
  settlement_window: string;
  postponement_handling: string;
  scope_summary: string;
}

export interface RiskRow {
  candidate: {
    market_id: string;
    exchange: Exchange;
    title: string;
    url: string | null;
    similarity: number;
  };
  dimensions: Record<string, DimensionDiff>;
  arbitrage_flag: "potential" | "none";
  rationale: string;
}

export interface RiskMatrix {
  input: {
    exchange: Exchange | null;
    title: string | null;
    url: string | null;
    expiration_ts: string | null;
    rules: ExtractedRules;
  };
  rows: RiskRow[];
  errors?: string[];
  events?: { step: string; status: string; [k: string]: unknown }[];
}

export interface CompareResult {
  comparison_id: string;
  status: "pending" | "running" | "done" | "error";
  risk_matrix: RiskMatrix | null;
  error: string | null;
}

export interface StreamEvent {
  type: "started" | "step" | "result" | "error";
  data: unknown;
}
