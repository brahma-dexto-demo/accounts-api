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


def test_risk_join_filters_and_boundaries(tmp_path, monkeypatch):
    monkeypatch.delenv("DATA_BUCKET", raising=False)
    monkeypatch.setenv("LOCAL_DATA_DIR", str(tmp_path))
    source = Path(__file__).resolve().parents[1] / "data/accounts/accounts.json"
    (tmp_path / "accounts").mkdir()
    (tmp_path / "accounts/accounts.json").write_bytes(source.read_bytes())
    scores = [
        {"id": f"acct_{i:04d}", "probability": i / 100, "risk_score": score}
        for i, score in enumerate([0, 39, 40, 69, 70, 100], start=1)
    ]
    (tmp_path / "scores").mkdir()
    (tmp_path / "scores/latest.json").write_text(
        json.dumps(
            {"model_version": "test", "generated_at": "2026-10-01T00:00:00Z", "scores": scores}
        )
    )
    client = TestClient(app)
    assert [a["risk_score"] for a in client.get("/accounts?limit=7").json()["accounts"]] == [
        0, 39, 40, 69, 70, 100, None
    ]
    page = client.get("/accounts?high_risk=true&limit=1&offset=1").json()
    assert (page["total"], page["accounts"][0]["id"], page["accounts"][0]["risk_score"]) == (
        2, "acct_0006", 100
    )
    assert client.get("/accounts?high_risk=false").json()["total"] == 200
    assert client.get("/accounts?high_risk=true&offset=2").json()["accounts"] == []
    account = client.get("/accounts/acct_0005").json()
    assert account["risk_score"] == 70
    assert "monthly_spend_usd" in account
    assert client.get("/accounts/missing").status_code == 404
    assert client.get("/accounts?high_risk=notabool").status_code == 422
    source_accounts = json.loads(source.read_text())
    name = source_accounts[4]["name"]
    industry = source_accounts[4]["industry"]
    filtered = client.get(
        "/accounts", params={"high_risk": "true", "q": name, "industry": industry}
    ).json()
    assert filtered["total"] >= 1
    assert all(a["risk_score"] >= 70 and name in a["name"] for a in filtered["accounts"])


def test_missing_and_stale_scores(tmp_path, monkeypatch):
    monkeypatch.delenv("DATA_BUCKET", raising=False)
    monkeypatch.setenv("LOCAL_DATA_DIR", str(tmp_path))
    (tmp_path / "accounts").mkdir()
    source = Path(__file__).resolve().parents[1] / "data/accounts/accounts.json"
    (tmp_path / "accounts/accounts.json").write_bytes(source.read_bytes())
    client = TestClient(app)
    assert client.get("/accounts/acct_0001").json()["risk_score"] is None
    assert client.get("/accounts?high_risk=true").json()["total"] == 0
    (tmp_path / "scores").mkdir()
    (tmp_path / "scores/latest.json").write_text(
        json.dumps({"scores": [{"id": "acct_0001", "probability": 0.99}]})
    )
    assert client.get("/accounts/acct_0001").json()["risk_score"] is None
    assert client.get("/accounts?high_risk=true").json()["total"] == 0


def test_malformed_scores_are_not_masked(tmp_path, monkeypatch):
    monkeypatch.delenv("DATA_BUCKET", raising=False)
    monkeypatch.setenv("LOCAL_DATA_DIR", str(tmp_path))
    (tmp_path / "accounts").mkdir()
    source = Path(__file__).resolve().parents[1] / "data/accounts/accounts.json"
    (tmp_path / "accounts/accounts.json").write_bytes(source.read_bytes())
    (tmp_path / "scores").mkdir()
    (tmp_path / "scores/latest.json").write_text("not json")
    with pytest.raises(json.JSONDecodeError):
        TestClient(app).get("/accounts")
