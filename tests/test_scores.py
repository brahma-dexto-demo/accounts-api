import json
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from fastapi.testclient import TestClient

from accounts_api.main import app
from accounts_api.scores import read_scores
from accounts_api.storage import JsonStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("DATA_BUCKET", raising=False)
    monkeypatch.setenv("LOCAL_DATA_DIR", str(tmp_path))
    return JsonStore()


def test_absent_and_legacy_scores(store):
    assert read_scores(store) == {}
    store.write("scores/latest.json", {
        "model_version": "legacy", "generated_at": "2026-10-05T00:00:00Z",
        "scores": [{"id": "acct-001", "probability": 0.734}],
    })
    assert read_scores(store) == {"acct-001": None}


@pytest.mark.parametrize("value", [
    None, [], {}, {"scores": None}, {"scores": {}}, {"scores": [None]},
    {"scores": [{"id": "", "probability": 0.5}]},
    {"scores": [{"id": 1, "probability": 0.5}]},
    {"scores": [{"id": "a"}]},
    *[{"scores": [{"id": "a", "probability": p}]} for p in
      [None, True, "0.5", -0.1, 1.1, float("nan"), float("inf")]],
    *[{"scores": [{"id": "a", "probability": 0.5, "risk_score": s}]} for s in
      [None, True, "50", 50.0, -1, 101]],
    {"scores": [{"id": "a", "probability": 0.5}] * 2},
])
def test_invalid_scores_are_not_absence(store, value):
    store.write("scores/latest.json", value)
    with pytest.raises(ValueError):
        read_scores(store)


def test_corrupt_json(store):
    store.write("scores/latest.json", {})
    (store.local_dir / "scores/latest.json").write_text("{")
    with pytest.raises(json.JSONDecodeError):
        read_scores(store)


@pytest.mark.parametrize("failure", [PermissionError("denied"), OSError("I/O error")])
def test_local_failures_propagate(store, monkeypatch, failure):
    monkeypatch.setattr(store, "read", Mock(side_effect=failure))
    with pytest.raises(type(failure)):
        read_scores(store)


@pytest.mark.parametrize("code", ["NoSuchKey", "AccessDenied", "NoSuchBucket", "404", "500"])
def test_s3_only_no_such_key_is_absence(monkeypatch, code):
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    client = Mock()
    client.get_object.side_effect = ClientError({"Error": {"Code": code}}, "GetObject")
    monkeypatch.setattr("accounts_api.storage.boto3.client", lambda _: client)
    store = JsonStore()
    if code == "NoSuchKey":
        assert read_scores(store) == {}
    else:
        with pytest.raises(ClientError):
            read_scores(store)


def test_s3_network_failure_propagates(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    client = Mock()
    client.get_object.side_effect = EndpointConnectionError(endpoint_url="https://s3.example")
    monkeypatch.setattr("accounts_api.storage.boto3.client", lambda _: client)
    with pytest.raises(EndpointConnectionError):
        read_scores(JsonStore())


def seed_accounts(store):
    accounts = []
    for i in range(8):
        accounts.append({
            "id": f"acct-{i}", "name": "Cedar" if i != 7 else "Other",
            "industry": "technology" if i != 6 else "finance", "country": "US",
            "plan": "basic", "monthly_spend_usd": 10, "open_tickets": 0,
            "days_since_last_login": 1, "created_at": "2026-01-01",
        })
    store.write("accounts/accounts.json", accounts)


def test_join_filters_boundaries_and_pagination(store):
    seed_accounts(store)
    store.write("scores/latest.json", {"scores": [
        {"id": f"acct-{i}", "probability": 0.734, "risk_score": score}
        for i, score in reversed(list(enumerate([0, 39, 40, 69, 70, 100, 90, 80])))
    ] + [{"id": "extra", "probability": 1, "risk_score": 100}]})
    with TestClient(app) as client:
        page = client.get("/accounts").json()
        assert [a["risk_score"] for a in page["accounts"]] == [0, 39, 40, 69, 70, 100, 90, 80]
        assert client.get("/accounts?high_risk=false").json() == page
        page = client.get("/accounts", params={
            "high_risk": "true", "industry": "TECHNOLOGY", "q": "cedar",
            "limit": 1, "offset": 1,
        }).json()
        assert page["total"] == 2
        assert page["accounts"][0]["id"] == "acct-5"
        assert page["accounts"][0]["risk_score"] == 100
        assert client.get("/accounts/acct-0").json()["risk_score"] == 0
        assert client.get("/accounts?high_risk=garbage").status_code == 422
        assert client.get("/accounts?high_risk=true&offset=4").json()["accounts"] == []


def test_null_join_for_missing_and_legacy(store):
    seed_accounts(store)
    with TestClient(app) as client:
        assert all(a["risk_score"] is None for a in client.get("/accounts").json()["accounts"])
        assert client.get("/accounts/acct-0").json()["risk_score"] is None
        store.write("scores/latest.json", {"scores": [
            {"id": "acct-0", "probability": 1},
            {"id": "acct-1", "probability": 0.734, "risk_score": 73},
        ]})
        page = client.get("/accounts").json()
        assert page["accounts"][0]["risk_score"] is None
        assert page["accounts"][1]["risk_score"] == 73
        assert page["accounts"][2]["risk_score"] is None
        assert client.get("/accounts/acct-2").json()["risk_score"] is None
        assert client.get("/accounts?high_risk=true").json()["total"] == 1
        assert client.get("/accounts/missing").status_code == 404


@pytest.mark.parametrize("path", ["/accounts", "/accounts/acct-0", "/accounts?high_risk=true"])
def test_bad_artifact_returns_server_error(store, path):
    seed_accounts(store)
    store.write("scores/latest.json", {"scores": [
        {"id": "acct-0", "probability": 1, "risk_score": "100"},
    ]})
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get(path).status_code == 500


def test_s3_valid_scores_join(monkeypatch):
    import io

    monkeypatch.setenv("DATA_BUCKET", "test-bucket")
    client = Mock()
    client.get_object.return_value = {"Body": io.BytesIO(json.dumps({"scores": [
        {"id": "acct-001", "probability": 0.734, "risk_score": 73},
    ]}).encode())}
    monkeypatch.setattr("accounts_api.storage.boto3.client", lambda _: client)
    assert read_scores(JsonStore()) == {"acct-001": 73}
    client.get_object.assert_called_once_with(Bucket="test-bucket", Key="scores/latest.json")


@pytest.mark.parametrize("path", ["/accounts", "/accounts/acct-0"])
def test_score_permission_error_is_server_error(store, monkeypatch, path):
    seed_accounts(store)
    original_read = JsonStore.read

    def denied_scores(self, key):
        if key == "scores/latest.json":
            raise PermissionError("scores denied")
        return original_read(self, key)

    monkeypatch.setattr(JsonStore, "read", denied_scores)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get(path).status_code == 500
