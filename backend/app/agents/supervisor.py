"""LangGraph supervisor that orchestrates the four sub-agent nodes in order."""

from __future__ import annotations

import logging
from typing import AsyncIterator

from langgraph.graph import END, StateGraph

from app.agents.market_fetcher import market_fetcher_node
from app.agents.risk_synthesizer import build_risk_matrix_payload, risk_synthesizer_node
from app.agents.rules_extractor import rules_extractor_node
from app.agents.similarity_retriever import similarity_retriever_node
from app.agents.state import CompareState, new_state

logger = logging.getLogger(__name__)


def _has_input_market(state: CompareState) -> str:
    return "ok" if state.get("input_market") is not None else "halt"


def _has_candidates(state: CompareState) -> str:
    return "ok" if state.get("candidates") else "halt"


def build_graph():
    graph = StateGraph(CompareState)
    graph.add_node("fetcher", market_fetcher_node)
    graph.add_node("retriever", similarity_retriever_node)
    graph.add_node("extractor", rules_extractor_node)
    graph.add_node("synthesizer", risk_synthesizer_node)

    graph.set_entry_point("fetcher")
    graph.add_conditional_edges(
        "fetcher", _has_input_market, {"ok": "retriever", "halt": END}
    )
    graph.add_conditional_edges(
        "retriever", _has_candidates, {"ok": "extractor", "halt": END}
    )
    graph.add_edge("extractor", "synthesizer")
    graph.add_edge("synthesizer", END)
    return graph.compile()


_compiled = None


def _get_compiled():
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled


async def run_compare(url: str) -> dict:
    """Run the compare graph end-to-end and return the final RiskMatrix payload."""
    initial = new_state(url)
    final_state: CompareState = await _get_compiled().ainvoke(initial)
    payload = build_risk_matrix_payload(final_state)
    payload["errors"] = final_state.get("errors", [])
    payload["events"] = final_state.get("events", [])
    return payload


async def stream_compare(url: str) -> AsyncIterator[dict]:
    """Stream per-step events to the caller (one dict per node completion)."""
    initial = new_state(url)
    last_seen = 0
    async for chunk in _get_compiled().astream(initial, stream_mode="values"):
        events = chunk.get("events", [])
        for event in events[last_seen:]:
            yield {"type": "step", "data": event}
        last_seen = len(events)
        if not chunk.get("input_market") and chunk.get("errors"):
            yield {"type": "error", "data": chunk["errors"][-1]}
            return
    yield {
        "type": "result",
        "data": build_risk_matrix_payload(chunk),
    }
