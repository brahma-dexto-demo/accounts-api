import io
from unittest.mock import Mock

from accounts_api.storage import JsonStore


def test_local_roundtrip(tmp_path, monkeypatch):
    monkeypatch.delenv("DATA_BUCKET", raising=False)
    monkeypatch.setenv("LOCAL_DATA_DIR", str(tmp_path))
    store = JsonStore()
    store.write("accounts/accounts.json", [{"id": "acct_0001"}])
    assert store.read("accounts/accounts.json") == [{"id": "acct_0001"}]


def test_s3_selection(monkeypatch):
    monkeypatch.setenv("DATA_BUCKET", "brahma-demo-data-test")
    monkeypatch.setenv("LOCAL_DATA_DIR", "/unused")
    client = Mock()
    client.get_object.return_value = {"Body": io.BytesIO(b'[{"id":"acct_0001"}]')}
    monkeypatch.setattr("accounts_api.storage.boto3.client", lambda service: client)
    store = JsonStore()
    assert store.read("accounts/accounts.json")[0]["id"] == "acct_0001"
    client.get_object.assert_called_once_with(
        Bucket="brahma-demo-data-test", Key="accounts/accounts.json"
    )
    store.write("scores/latest.json", {"scores": []})
    assert client.put_object.call_args.kwargs["Key"] == "scores/latest.json"
