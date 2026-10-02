"""Live semantic checks beyond the generated OpenAPI schema."""

import os

import httpx
import pytest

BASE_URL = os.getenv("BASE_URL")
pytestmark = pytest.mark.skipif(not BASE_URL, reason="Set BASE_URL for live contract tests")


def test_live_risk_filter_contract():
    with httpx.Client(base_url=BASE_URL, timeout=15) as client:
        response = client.get("/accounts", params={"limit": 200})
        response.raise_for_status()
        all_accounts = response.json()["accounts"]
        assert response.json()["total"] == len(all_accounts)
        for account in all_accounts:
            score = account["risk_score"]
            assert score is None or (type(score) is int and 0 <= score <= 100)
        expected = [a for a in all_accounts if a["risk_score"] is not None
                    and a["risk_score"] >= 70]
        # Gather the filtered set through several small pages: total precedes pagination.
        actual = []
        for offset in range(0, len(expected) + 7, 7):
            page = client.get("/accounts", params={"high_risk": True, "limit": 7,
                                                  "offset": offset})
            page.raise_for_status()
            assert page.json()["total"] == len(expected)
            actual.extend(page.json()["accounts"])
        assert actual == expected
        for account in all_accounts[:5]:
            detail = client.get(f'/accounts/{account["id"]}')
            detail.raise_for_status()
            assert detail.json() == account
        if all_accounts:
            first = all_accounts[0]
            filtered = client.get("/accounts", params={"high_risk": True, "limit": 200,
                                                       "q": first["name"],
                                                       "industry": first["industry"].upper()})
            filtered.raise_for_status()
            subset = [a for a in expected if first["name"].casefold() in a["name"].casefold()
                      and a["industry"].casefold() == first["industry"].casefold()]
            assert filtered.json()["accounts"] == subset
            assert filtered.json()["total"] == len(subset)
        assert client.get("/accounts/not-an-account").status_code == 404
