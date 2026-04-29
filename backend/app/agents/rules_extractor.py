"""RulesExtractor agent: turn free-form rule text into structured ExtractedRules via Claude."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.agents.state import CompareState
from app.config import get_settings
from app.schemas.market import ExtractedRules, NormalizedMarket

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """\
You are a careful prediction-market rules analyst. Given the title and rules text of a single market,
extract a strict JSON object matching this exact schema:

{
  "resolution_source_primary": string,   // Primary data source the market settles on. Empty string if unspecified.
  "resolution_source_fallback": string,  // Fallback / secondary source. Empty string if none.
  "tiebreak_rule": string,               // How exact-threshold ties are resolved. Empty if unspecified.
  "dead_heat_rule": string,              // Specifically how a 'dead heat' (no clear winner) is handled.
  "expiration_ts_utc": string,           // ISO 8601 UTC timestamp if explicitly stated, else "".
  "settlement_window": string,           // Phrase describing the settlement window (e.g. "within 24h of event end").
  "postponement_handling": string,       // Treatment of postponements / cancellations / delays.
  "scope_summary": string                // ONE sentence stating what the market is asking.
}

Rules:
- Output ONLY a single JSON object. No prose, no markdown fences.
- Use empty strings for fields not addressed by the source text. Do not invent.
- Keep each value under 280 characters.
"""


def _build_prompt(market: NormalizedMarket) -> str:
    rules_lines = []
    for k, v in (market.rules_raw or {}).items():
        if isinstance(v, str) and v.strip():
            rules_lines.append(f"{k}: {v}")
    rules_block = "\n".join(rules_lines) or "(no structured rules fields)"
    expires = market.expiration_ts.isoformat() if market.expiration_ts else "(unspecified)"
    return (
        f"Exchange: {market.exchange}\n"
        f"Title: {market.title}\n"
        f"Stated expiration: {expires}\n"
        f"Stated resolution source: {market.resolution_source or '(unspecified)'}\n\n"
        f"--- DESCRIPTION ---\n{market.description_raw or '(empty)'}\n\n"
        f"--- STRUCTURED FIELDS ---\n{rules_block}"
    )


def _safe_parse_rules(raw: Any) -> ExtractedRules:
    if isinstance(raw, ExtractedRules):
        return raw
    text: str = ""
    if isinstance(raw, str):
        text = raw
    elif hasattr(raw, "content"):
        content = raw.content
        if isinstance(content, list):
            text = "".join(
                p.get("text", "") if isinstance(p, dict) else str(p)
                for p in content
            )
        else:
            text = str(content)
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
        return ExtractedRules.model_validate(data)
    except Exception:
        return ExtractedRules()


async def _extract_one(llm, market: NormalizedMarket) -> ExtractedRules:
    if llm is None:
        return _heuristic_extract(market)
    try:
        resp = await llm.ainvoke(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(market)},
            ]
        )
        return _safe_parse_rules(resp)
    except Exception as e:
        logger.warning("Claude extraction failed for %s: %s", market.title, e)
        return _heuristic_extract(market)


def _heuristic_extract(market: NormalizedMarket) -> ExtractedRules:
    return ExtractedRules(
        resolution_source_primary=market.resolution_source or "",
        scope_summary=market.title,
        expiration_ts_utc=market.expiration_ts.isoformat() if market.expiration_ts else "",
    )


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
            max_tokens=1024,
        )
    except Exception as e:
        logger.warning("Could not init ChatAnthropic; falling back to heuristic extraction: %s", e)
        return None


async def rules_extractor_node(state: CompareState) -> CompareState:
    events = state.get("events", [])
    market = state.get("input_market")
    candidates = state.get("candidates", [])
    if market is None:
        events.append({"step": "extractor", "status": "skipped", "reason": "no input market"})
        return {**state, "events": events}

    events.append({"step": "extractor", "status": "start", "count": 1 + len(candidates)})
    llm = _build_llm()

    targets: list[tuple[str, NormalizedMarket]] = [("input", market)]
    for c in candidates:
        targets.append((c.market_id, c.market))

    results = await asyncio.gather(
        *(_extract_one(llm, mkt) for _, mkt in targets), return_exceptions=False
    )
    extracted: dict[str, ExtractedRules] = {}
    for (key, _), rules in zip(targets, results):
        extracted[key] = rules

    events.append({"step": "extractor", "status": "ok", "count": len(extracted)})
    return {**state, "extracted": extracted, "events": events}
