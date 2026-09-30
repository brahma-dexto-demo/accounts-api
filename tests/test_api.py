import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from accounts_api.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("DATA_BUCKET", raising=False)
    monkeypatch.setenv("LOCAL_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data"))
    return TestClient(app)


def test_health_and_pagination(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    page = client.get("/accounts", params={"limit": 2, "offset": 1}).json()
    assert page["total"] == 200
    assert len(page["accounts"]) == 2
    assert page["accounts"][0]["id"] == "acct_0002"
    assert "monthly_spend_usd" in page["accounts"][0]
    assert "monthlySpendUsd" not in page["accounts"][0]
    assert client.get("/accounts?offset=200").json()["accounts"] == []


def test_filters_and_detail(client):
    page = client.get("/accounts?industry=TECHNOLOGY&q=cedar&limit=200").json()
    assert page["total"] > 0
    assert all(a["industry"] == "technology" and "Cedar" in a["name"] for a in page["accounts"])
    assert client.get("/accounts/acct_0001").json()["id"] == "acct_0001"
    assert client.get("/accounts/missing").status_code == 404
    assert client.get("/accounts?q=no-such-customer").json()["total"] == 0


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "offset=-1", "limit=abc"])
def test_invalid_pagination(client, query):
    assert client.get(f"/accounts?{query}").status_code == 422


def test_openapi_matches():
    path = Path(__file__).resolve().parents[1] / "openapi.json"
    assert json.loads(path.read_text()) == app.openapi()
