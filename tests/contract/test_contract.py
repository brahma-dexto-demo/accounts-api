"""Live OpenAPI contract coverage, opt-in via BASE_URL."""

import os

import pytest
import schemathesis
from hypothesis import settings

base_url = os.getenv("BASE_URL")
if not base_url:
    pytest.skip("Set BASE_URL to run live contract tests", allow_module_level=True)

schema = schemathesis.openapi.from_url(f"{base_url.rstrip('/')}/openapi.json")


@schema.parametrize()
@settings(max_examples=20, deadline=None)
def test_contract(case):
    case.call_and_validate()


def test_risk_score_contract():
    import requests

    root = base_url.rstrip("/")
    page = requests.get(f"{root}/accounts", params={"high_risk": "true", "limit": 1}, timeout=5)
    page.raise_for_status()
    payload = page.json()
    assert set(payload) == {"accounts", "total", "limit", "offset"}
    assert payload["limit"] == 1
    assert payload["total"] >= len(payload["accounts"])
    assert all(70 <= a["risk_score"] <= 100 for a in payload["accounts"])
    ordinary = requests.get(f"{root}/accounts", params={"limit": 1}, timeout=5)
    ordinary.raise_for_status()
    account = ordinary.json()["accounts"][0]
    assert "risk_score" in account
    assert account["risk_score"] is None or 0 <= account["risk_score"] <= 100
    detail = requests.get(f"{root}/accounts/{account['id']}", timeout=5)
    detail.raise_for_status()
    assert detail.json() == account
    missing = requests.get(f"{root}/accounts/missing", timeout=5)
    assert missing.status_code == 404
