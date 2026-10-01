# Accounts API

Account service for the operations console. Serves customer accounts over a small REST API.

This is a demo repository with 200 synthetic, fictional accounts; it contains no real customer data.

## Local development

```sh
uv sync
uv run uvicorn accounts_api.main:app --reload --port 8000
uv run pytest
uv run ruff check .
python scripts/generate_accounts.py
```

Run commands from the repository root. Python 3.12 is selected by `.python-version`.
`LOCAL_DATA_DIR` defaults to `./data`; setting `DATA_BUCKET` selects S3 instead,
reading `accounts/accounts.json` using the default AWS credential chain.
`GET /accounts` returns `{accounts, total, limit, offset}` with `industry` (exact,
case-insensitive) and `q` (case-insensitive name substring) filters. `limit` defaults
to 50 (1–200) and `offset` to 0. All JSON fields are snake_case.
`GET /accounts/{id}` returns one account or 404; `/healthz` reports process health.

`openapi.json` is checked in. After an intentional schema change, regenerate it:

```sh
uv run python -c 'import json; from pathlib import Path; from accounts_api.main import app; Path("openapi.json").write_text(json.dumps(app.openapi(), indent=2) + "\n")'
BASE_URL=http://localhost:8000 uv run pytest tests/contract
```

Contract tests skip when `BASE_URL` is unset. See [DEPLOY.md](DEPLOY.md) for staging.

## Batch risk scores

The API joins accounts by `id` with `scores/latest.json` in the same local data
folder or S3 bucket. Batch publishes `model_version`, UTC `generated_at`, and
`scores` entries with `id`, `probability` (0–1) and `risk_score` (integer 0–100,
rounded half up from probability × 100). This API **does not** infer a score from
probability: an absent artifact, an unmatched account, or an old entry without
`risk_score` yields `risk_score: null`. Storage permissions, malformed JSON, and
other read failures are not treated as missing scores.

Both `GET /accounts` and `GET /accounts/{id}` include `risk_score`. The optional
`high_risk=true` query on the list selects scores >= 70 before pagination and
`total` calculation; omitted or `false` returns all accounts. It composes with
`industry` and `q`. Deploy Batch producer first, then accounts-api, then console;
old score artifacts show unknown scores until Batch republishes.
