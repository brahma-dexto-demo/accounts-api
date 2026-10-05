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


def test_live_risk_join_filter_and_pagination():
    import httpx

    with httpx.Client(base_url=base_url) as client:
        response = client.get("/accounts", params={"limit": 200})
        response.raise_for_status()
        accounts = response.json()["accounts"]
        for account in accounts:
            score = account["risk_score"]
            assert score is None or (type(score) is int and 0 <= score <= 100)
            assert "riskScore" not in account
        expected = [a for a in accounts if a["risk_score"] is not None and a["risk_score"] >= 70]
        page = client.get("/accounts", params={"high_risk": "true", "limit": 200}).json()
        assert page["accounts"] == expected
        assert page["total"] == len(expected)
        paged = client.get("/accounts", params={
            "high_risk": "true", "limit": 1, "offset": 1,
        }).json()
        assert paged["accounts"] == expected[1:2]
        assert paged["total"] == len(expected)
        assert client.get("/accounts", params={"high_risk": "false", "limit": 200}).json()[
            "accounts"
        ] == accounts
        if accounts:
            account = accounts[0]
            assert client.get(f"/accounts/{account['id']}").json() == account
        if expected:
            account = expected[0]
            filtered = client.get("/accounts", params={
                "high_risk": "true", "industry": account["industry"].upper(),
                "q": account["name"], "limit": 200,
            }).json()
            matches = [a for a in expected if a["industry"] == account["industry"]
                       and account["name"].casefold() in a["name"].casefold()]
            assert filtered["accounts"] == matches
            assert filtered["total"] == len(matches)
