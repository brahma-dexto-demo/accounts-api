# Accounts API

Account service for the operations console. Serves customer accounts over a small REST API.

This is a demo repository with 200 synthetic, fictional accounts; it contains no real customer data.

## Local development

```sh
uv sync --locked
uv run uvicorn accounts_api.main:app --reload --port 8101
uv run pytest
uv run ruff check .
python scripts/generate_accounts.py
```

Run commands from the repository root. Python 3.12 is selected by `.python-version`.
`LOCAL_DATA_DIR` defaults to `./data`; setting `DATA_BUCKET` selects S3 instead,
reading `accounts/accounts.json` and `scores/latest.json` using the default AWS credential chain.
`GET /accounts` returns `{accounts, total, limit, offset}` with `industry` (exact,
case-insensitive), `q` (case-insensitive name substring), and `high_risk` (boolean,
default `false`) filters. `high_risk=true` selects `risk_score >= 70`, excludes
unknown scores, and combines with the other filters **before** pagination and `total`. `limit` defaults
to 50 (1–200) and `offset` to 0. All JSON fields are snake_case.
`GET /accounts/{id}` returns one account or 404; `/healthz` reports process health.

`openapi.json` is checked in. After an intentional schema change, regenerate it:

```sh
uv run python -c 'import json; from pathlib import Path; from accounts_api.main import app; Path("openapi.json").write_text(json.dumps(app.openapi(), indent=2) + "\n")'
BASE_URL=http://localhost:8101 uv run pytest tests/contract
```

Contract tests skip when `BASE_URL` is unset. See [DEPLOY.md](DEPLOY.md) for staging.

## Risk score contract

The risk engine owns calculation. Its `scores/latest.json` has `model_version`,
ISO timestamp `generated_at`, and `scores` entries such as:

```json
{"id": "acc-001", "probability": 0.734, "risk_score": 73}
```

Probability remains in [0,1]; the integer score is `floor(probability * 100 + 0.5)`.
The API validates that contract and joins by account `id`; it does not calculate scores.
Both account endpoints include snake_case `risk_score` (integer 0–100 or null).
A missing artifact or missing account score yields null, never zero. An empty scores
list is valid. Invalid JSON, invalid metadata/rows, duplicate IDs, out-of-range or
inconsistent scores, and non-missing storage errors return 503 (`Risk scores unavailable`).
Only local file absence or S3 `NoSuchKey` means missing; permission errors, missing
buckets and network failures are not treated as unknown. Unknown account IDs still
return 404, even if the score artifact is unavailable.

Consumers map `risk_score` to a nullable integer: Low 0–39 (green), Medium 40–69
(amber), High 70–100 (red), Unknown null (neutral). Rollout/merge order is
**risk-engine → accounts-api → ops-console**. The additive account field preserves
existing client compatibility. Publish the updated producer artifact before this
API: old artifacts lacking `risk_score` intentionally fail validation rather than
masking deployment errors.

For cross-repo local QA, point `LOCAL_DATA_DIR` at the shared producer output:

```sh
LOCAL_DATA_DIR=/absolute/shared/data uv run uvicorn accounts_api.main:app --host 0.0.0.0 --port 8101
BASE_URL=http://localhost:8101 uv run pytest tests/contract
```

Live tests check OpenAPI, score bounds, list/detail consistency, combined filters,
and high-risk pagination/total consistency against the demo dataset (up to 200 accounts).
They can run without scores, but producer-backed QA should include scored accounts.
