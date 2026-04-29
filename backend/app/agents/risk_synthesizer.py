"""RiskSynthesizer agent: deterministic per-dimension diff + Claude rationale."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any

from app.agents.state import CompareState
from app.config import get_settings
from app.schemas.market import (
    Candidate,
    DimensionDiff,
    ExtractedRules,
    NormalizedMarket,
    RiskRow,
)

logger = logging.getLogger(__name__)


_TIEBREAK_KEYWORDS = {
    "first_to_threshold": {"first to", "whoever first", "first crosses"},
    "pro_rata": {"pro rata", "pro-rata", "split", "proportional"},
    "void": {"void", "no contest", "refund"},
    "yes": {"resolves yes", "settles yes"},
    "no": {"resolves no", "settles no"},
}


def _classify_tiebreak(text: str) -> str:
    s = (text or "").lower()
    for label, kws in _TIEBREAK_KEYWORDS.items():
        if any(kw in s for kw in kws):
            return label
    return ""


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9][a-z0-9\-']+", (text or "").lower()) if len(w) > 2}


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _diff_resolution_source(input_r: ExtractedRules, cand_r: ExtractedRules) -> DimensionDiff:
    a = input_r.resolution_source_primary.strip()
    b = cand_r.resolution_source_primary.strip()
    if not a and not b:
        return DimensionDiff(input=a, candidate=b, divergence="medium", note="Neither side states a resolution source")
    if not a or not b:
        return DimensionDiff(input=a, candidate=b, divergence="medium", note="One side has no stated source")
    sim = _jaccard(a, b)
    if a.lower() == b.lower() or sim >= 0.7:
        return DimensionDiff(input=a, candidate=b, divergence="low", note="Sources are aligned")
    if sim >= 0.3:
        return DimensionDiff(input=a, candidate=b, divergence="medium", note="Sources partially overlap")
    return DimensionDiff(input=a, candidate=b, divergence="high", note="Different primary sources")


def _diff_tiebreak(input_r: ExtractedRules, cand_r: ExtractedRules) -> DimensionDiff:
    a = input_r.tiebreak_rule or input_r.dead_heat_rule
    b = cand_r.tiebreak_rule or cand_r.dead_heat_rule
    cls_a = _classify_tiebreak(a)
    cls_b = _classify_tiebreak(b)
    if not a and not b:
        return DimensionDiff(input=a, candidate=b, divergence="medium", note="Neither side specifies a tie-break rule")
    if not a or not b:
        return DimensionDiff(input=a, candidate=b, divergence="medium", note="One side has no tie-break rule stated")
    if cls_a and cls_b and cls_a == cls_b:
        return DimensionDiff(input=a, candidate=b, divergence="low", note="Compatible tie-break logic")
    if cls_a and cls_b and cls_a != cls_b:
        return DimensionDiff(input=a, candidate=b, divergence="high", note="Incompatible tie-break logic")
    sim = _jaccard(a, b)
    if sim >= 0.5:
        return DimensionDiff(input=a, candidate=b, divergence="low", note="Tie-break wording aligns")
    return DimensionDiff(input=a, candidate=b, divergence="medium", note="Tie-break wording differs")


def _parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _diff_expiration(
    input_market: NormalizedMarket,
    cand_market: NormalizedMarket,
    input_r: ExtractedRules,
    cand_r: ExtractedRules,
) -> DimensionDiff:
    a = input_market.expiration_ts or _parse_iso(input_r.expiration_ts_utc)
    b = cand_market.expiration_ts or _parse_iso(cand_r.expiration_ts_utc)
    a_str = a.isoformat() if a else (input_r.expiration_ts_utc or "")
    b_str = b.isoformat() if b else (cand_r.expiration_ts_utc or "")
    if a is None or b is None:
        return DimensionDiff(input=a_str, candidate=b_str, divergence="medium", note="Missing expiration on at least one side")
    delta_seconds = abs((a - b).total_seconds())
    delta_h = delta_seconds / 3600.0
    note = _format_gap(delta_seconds)
    if delta_h <= 1:
        level = "low"
    elif delta_h <= 24:
        level = "medium"
    else:
        level = "high"
    return DimensionDiff(input=a_str, candidate=b_str, divergence=level, note=f"{note} gap")


def _format_gap(delta_seconds: float) -> str:
    """Render a time delta in the largest sensible unit."""
    minutes = delta_seconds / 60.0
    hours = delta_seconds / 3600.0
    days = hours / 24.0
    if delta_seconds < 60:
        return f"{int(delta_seconds)}s"
    if minutes < 60:
        return f"{minutes:.0f}m"
    if hours < 48:
        return f"{hours:.1f}h"
    if days < 60:
        return f"{days:.1f}d"
    if days < 730:
        return f"{days / 30.4375:.1f}mo"
    return f"{days / 365.25:.1f}y"


def _diff_scope(input_r: ExtractedRules, cand_r: ExtractedRules) -> DimensionDiff:
    a = input_r.scope_summary
    b = cand_r.scope_summary
    if not a or not b:
        return DimensionDiff(input=a, candidate=b, divergence="medium", note="Scope summary missing on one side")
    sim = _jaccard(a, b)
    if sim >= 0.6:
        return DimensionDiff(input=a, candidate=b, divergence="low", note="Scope is closely aligned")
    if sim >= 0.3:
        return DimensionDiff(input=a, candidate=b, divergence="medium", note="Scope partially overlaps")
    return DimensionDiff(input=a, candidate=b, divergence="high", note="Scope materially differs")


_RATIONALE_PROMPT = """\
You are a prediction-market arbitrage analyst. You will be given the structured
divergences between an input market and a similar market on a different exchange.

Output ONLY a single JSON object of the form:
{"arbitrage_flag": "potential" | "none", "rationale": "<one sentence, <=240 chars>"}

Set arbitrage_flag = "potential" only if the divergences could plausibly cause
the two markets to settle differently or at materially different times.
Otherwise "none". Keep the rationale concrete and actionable.
"""


def _heuristic_rationale(dims: dict[str, DimensionDiff]) -> tuple[str, str]:
    high = [k for k, d in dims.items() if d.divergence == "high"]
    medium = [k for k, d in dims.items() if d.divergence == "medium"]
    if high:
        flag = "potential"
        notes = "; ".join(f"{k}: {dims[k].note}" for k in high)
        rationale = f"High divergence on {', '.join(high)} ({notes})."
    elif len(medium) >= 2:
        flag = "potential"
        rationale = f"Multiple medium divergences across {', '.join(medium)} could shift settlement."
    else:
        flag = "none"
        rationale = "Resolution rules look broadly aligned; no obvious settlement divergence."
    return flag, rationale[:240]


async def _llm_rationale(
    llm,
    input_title: str,
    candidate_title: str,
    dims: dict[str, DimensionDiff],
) -> tuple[str, str]:
    if llm is None:
        return _heuristic_rationale(dims)
    user_msg = (
        f"Input market: {input_title}\n"
        f"Candidate market: {candidate_title}\n\n"
        "Divergences:\n"
        + json.dumps({k: v.model_dump() for k, v in dims.items()}, indent=2)
    )
    try:
        resp = await llm.ainvoke(
            [
                {"role": "system", "content": _RATIONALE_PROMPT},
                {"role": "user", "content": user_msg},
            ]
        )
        text = resp.content if hasattr(resp, "content") else str(resp)
        if isinstance(text, list):
            text = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in text)
        text = str(text).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]
        data = json.loads(text)
        flag = data.get("arbitrage_flag", "none")
        if flag not in {"potential", "none"}:
            flag = "none"
        rationale = str(data.get("rationale", ""))[:240]
        if not rationale:
            return _heuristic_rationale(dims)
        return flag, rationale
    except Exception as e:
        logger.warning("Rationale LLM call failed: %s", e)
        return _heuristic_rationale(dims)


def _build_llm():
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    try:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,
            temperature=0.0,
            max_tokens=300,
        )
    except Exception as e:
        logger.warning("Could not init ChatAnthropic for rationale: %s", e)
        return None


async def risk_synthesizer_node(state: CompareState) -> CompareState:
    events = state.get("events", [])
    market = state.get("input_market")
    candidates: list[Candidate] = state.get("candidates", [])
    extracted: dict[str, ExtractedRules] = state.get("extracted", {})
    if market is None:
        events.append({"step": "synthesizer", "status": "skipped"})
        return {**state, "events": events}

    events.append({"step": "synthesizer", "status": "start", "candidates": len(candidates)})
    input_rules = extracted.get("input", ExtractedRules())
    llm = _build_llm()

    rows_data: list[tuple[Candidate, dict[str, DimensionDiff]]] = []
    for c in candidates:
        cand_rules = extracted.get(c.market_id, ExtractedRules())
        dims = {
            "resolution_source": _diff_resolution_source(input_rules, cand_rules),
            "tiebreak": _diff_tiebreak(input_rules, cand_rules),
            "expiration": _diff_expiration(market, c.market, input_rules, cand_rules),
            "scope": _diff_scope(input_rules, cand_rules),
        }
        rows_data.append((c, dims))

    rationales = await asyncio.gather(
        *(_llm_rationale(llm, market.title, c.title, dims) for c, dims in rows_data),
        return_exceptions=False,
    )

    rows: list[RiskRow] = []
    for (c, dims), (flag, rationale) in zip(rows_data, rationales):
        rows.append(
            RiskRow(
                candidate={
                    "market_id": c.market_id,
                    "exchange": c.exchange,
                    "title": c.title,
                    "url": c.url,
                    "similarity": c.similarity,
                },
                dimensions=dims,
                arbitrage_flag=flag,
                rationale=rationale,
            )
        )

    events.append({"step": "synthesizer", "status": "ok", "rows": len(rows)})
    return {**state, "risk_matrix": rows, "events": events}


def build_risk_matrix_payload(state: CompareState) -> dict[str, Any]:
    """Compose the final RiskMatrix JSON payload from the terminal state."""
    market: NormalizedMarket | None = state.get("input_market")
    rules: ExtractedRules = state.get("extracted", {}).get("input", ExtractedRules())
    rows: list[RiskRow] = state.get("risk_matrix", [])
    return {
        "input": {
            "exchange": market.exchange if market else None,
            "title": market.title if market else None,
            "url": market.url if market else None,
            "expiration_ts": market.expiration_ts.isoformat() if market and market.expiration_ts else None,
            "rules": rules.model_dump(),
        },
        "rows": [r.model_dump() for r in rows],
    }
