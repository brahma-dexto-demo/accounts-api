import copy
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from accounts_api.main import app, get_store
from accounts_api.storage import JsonStore


@pytest.fixture
def scored_client(tmp_path, monkeypatch):
    monkeypatch.delenv("DATA_BUCKET", raising=False)
    monkeypatch.setenv("LOCAL_DATA_DIR", str(tmp_path))
    accounts = json.loads((Path(__file__).resolve().parents[1] / "data/accounts/accounts.json")
                          .read_text())[:6]
    for i, account in enumerate(accounts):
        account.update(name=f"Example {i}", industry="technology")
    store = JsonStore()
    store.write("accounts/accounts.json", accounts)
    artifact = {
        "model_version": "test-v1",
        "generated_at": "2026-10-02T12:00:00+00:00",
        "scores": [
            {"id": a["id"], "probability": score / 100, "risk_score": score}
            for a, score in zip(accounts, [0, 39, 69, 70, 100])
        ],
    }
    store.write("scores/latest.json", artifact)
    return TestClient(app), store, artifact


def test_join_filter_and_pagination(scored_client):
    client, _, _ = scored_client
    page = client.get("/accounts?limit=200").json()
    assert [a["risk_score"] for a in page["accounts"]] == [0, 39, 69, 70, 100, None]
    for account in page["accounts"]:
        assert client.get(f'/accounts/{account["id"]}').json() == account
    high = client.get("/accounts?high_risk=true&limit=1&offset=1").json()
    assert high["total"] == 2
    assert [a["risk_score"] for a in high["accounts"]] == [100]
    assert client.get("/accounts?high_risk=true&offset=2").json()["accounts"] == []
    filtered = client.get("/accounts?high_risk=true&q=example%204&industry=TECHNOLOGY").json()
    assert filtered["total"] == 1
    assert filtered["accounts"][0]["risk_score"] == 100
    assert client.get("/accounts?high_risk=true&industry=other").json()["total"] == 0
    assert client.get("/accounts?high_risk=false").json()["total"] == 6
    assert client.get("/accounts?high_risk=invalid").status_code == 422


def test_missing_file(scored_client):
    client, store, _ = scored_client
    (store.local_dir / "scores/latest.json").unlink()
    assert all(a["risk_score"] is None for a in client.get("/accounts").json()["accounts"])
    assert client.get("/accounts/acct_0001").json()["risk_score"] is None
    assert client.get("/accounts?high_risk=true").json()["total"] == 0


@pytest.mark.parametrize("field,value", [
    ("risk_score", -1), ("risk_score", 101), ("risk_score", 70.0),
    ("risk_score", "70"), ("risk_score", True), ("risk_score", None),
    ("risk_score", 69), ("probability", -0.1), ("probability", 1.1),
    ("probability", float("nan")), ("probability", float("inf")),
    ("probability", "0.7"), ("probability", True), ("id", ""), ("id", 1),
])
def test_invalid_rows(scored_client, field, value):
    client, store, artifact = scored_client
    artifact["scores"][3][field] = value
    store.write("scores/latest.json", artifact)
    assert client.get("/accounts").status_code == 503
    assert client.get("/accounts/acct_0001").status_code == 503
    assert client.get("/accounts/missing").status_code == 404


@pytest.mark.parametrize("case", ["list", "metadata", "timestamp", "duplicate", "missing",
                                 "scores", "invalid_json"])
def test_invalid_artifacts(scored_client, case):
    client, store, artifact = scored_client
    if case == "list":
        artifact = []
    elif case == "metadata":
        del artifact["model_version"]
    elif case == "timestamp":
        artifact["generated_at"] = "not-a-date"
    elif case == "duplicate":
        artifact["scores"].append(copy.deepcopy(artifact["scores"][0]))
    elif case == "missing":
        del artifact["scores"][0]["risk_score"]
    elif case == "scores":
        artifact["scores"] = {}
    store.write("scores/latest.json", artifact)
    if case == "invalid_json":
        (store.local_dir / "scores/latest.json").write_text("{")
    assert client.get("/accounts?high_risk=true&q=nonexistent").status_code == 503
    assert client.get("/accounts/acct_0001").status_code == 503


@pytest.mark.parametrize("code,expected", [("NoSuchKey", 200), ("NoSuchBucket", 503),
                                          ("AccessDenied", 503), ("InternalError", 503)])
def test_s3_errors(scored_client, code, expected):
    client, store, _ = scored_client
    accounts = store.read("accounts/accounts.json")
    store.s3 = Mock()
    store.s3.get_object.side_effect = ClientError({"Error": {"Code": code}}, "GetObject")
    original_read = store.read
    store.read = lambda key: accounts if key.startswith("accounts/") else original_read(key)
    app.dependency_overrides[get_store] = lambda: store
    try:
        response = client.get("/accounts")
        assert response.status_code == expected
        if expected == 200:
            assert all(a["risk_score"] is None for a in response.json()["accounts"])
        assert client.get("/accounts/acct_0001").status_code == expected
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("error", [PermissionError("denied"), TimeoutError("timeout"),
                                  OSError("storage offline")])
def test_nonmissing_failures(scored_client, error):
    client, store, _ = scored_client
    original_read = store.read
    def read(key):
        if key == "scores/latest.json":
            raise error
        return original_read(key)
    store.read = read
    app.dependency_overrides[get_store] = lambda: store
    try:
        assert client.get("/accounts").status_code == 503
        assert client.get("/accounts/acct_0001").status_code == 503
    finally:
        app.dependency_overrides.clear()


def test_join_is_by_id_and_rounding_contract(scored_client):
    client, store, artifact = scored_client
    artifact["scores"].reverse()
    artifact["scores"][0].update(probability=0.734, risk_score=73)
    store.write("scores/latest.json", artifact)
    assert [a["risk_score"] for a in client.get("/accounts").json()["accounts"]] == [
        0, 39, 69, 70, 73, None,
    ]
    artifact["scores"][0].update(probability=0.695, risk_score=70)
    store.write("scores/latest.json", artifact)
    assert client.get("/accounts/acct_0005").json()["risk_score"] == 70
