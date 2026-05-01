"""TestClient smoke tests for FastAPI endpoints."""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_healthz(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_openapi_lists_all_routes(client: TestClient) -> None:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json().get("paths", {})
    assert "/api/v1/compare" in paths
    assert "/api/v1/compare/{comparison_id}" in paths
    assert "/api/v1/compare/{comparison_id}/stream" in paths
    assert "/api/v1/markets/{exchange}/{identifier}" in paths
    assert "/admin/ingest" in paths
    assert "/healthz" in paths


def test_admin_ingest_requires_token(client: TestClient) -> None:
    resp = client.post("/admin/ingest")
    assert resp.status_code == 401


def test_compare_rejects_unsupported_url(client: TestClient) -> None:
    resp = client.post("/api/v1/compare", json={"url": "https://example.com/foo"})
    assert resp.status_code == 400


def test_compare_rejects_non_http_url(client: TestClient) -> None:
    resp = client.post("/api/v1/compare", json={"url": "ftp://polymarket.com/market/x"})
    assert resp.status_code == 400


def test_markets_route_uses_adapter(client: TestClient) -> None:
    sample = {
        "id": "0x1",
        "conditionId": "0xCond",
        "slug": "test-market",
        "question": "Test market?",
        "description": "desc",
        "active": True,
        "closed": False,
        "endDate": "2026-12-31T00:00:00Z",
    }
    with respx.mock(base_url="https://gamma-api.polymarket.com") as r:
        r.get("/markets/slug/test-market").mock(
            return_value=httpx.Response(200, json=sample)
        )
        resp = client.get("/api/v1/markets/polymarket/test-market")
    assert resp.status_code == 200
    body = resp.json()
    assert body["exchange"] == "polymarket"
    assert body["title"] == "Test market?"


def test_markets_route_404_passes_through(client: TestClient) -> None:
    with respx.mock(base_url="https://gamma-api.polymarket.com") as r:
        r.get("/markets/slug/missing").mock(return_value=httpx.Response(404))
        r.get("/markets", params={"slug": "missing", "limit": 10}).mock(
            return_value=httpx.Response(200, json=[])
        )
        r.get("/events/slug/missing").mock(return_value=httpx.Response(404))
        r.get("/events", params={"slug": "missing", "limit": 5}).mock(
            return_value=httpx.Response(200, json=[])
        )
        resp = client.get("/api/v1/markets/polymarket/missing")
    assert resp.status_code == 404


def test_markets_route_invalid_exchange(client: TestClient) -> None:
    resp = client.get("/api/v1/markets/manifold/x")
    assert resp.status_code == 422
