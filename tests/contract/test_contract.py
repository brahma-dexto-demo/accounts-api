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
