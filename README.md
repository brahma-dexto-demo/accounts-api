# Accounts API

Account service for the operations console. Serves customer accounts over a small REST API.

This is a demo repository with 200 synthetic, fictional accounts; it contains no real customer data.

## Local development

```sh
uv sync --locked
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

## Account risk scores

Both account endpoints expose `risk_score` as an integer in 0–100 or JSON null.
The API reads `scores/latest.json` from the same local directory or S3 bucket as
accounts and joins its `scores` array by `id`. Risk-engine alone calculates scores
using `floor(clamp(probability, 0, 1) * 100 + 0.5)`; the API never derives a score
from probability. Example artifact (existing metadata is retained by the engine):

```json
{"model_version":"example","generated_at":"2026-10-05T00:00:00Z","scores":[{"id":"acct-001","probability":0.734,"risk_score":73}]}
```

A missing local score file or S3 `NoSuchKey`, an account absent from the scores,
or a legacy row without `risk_score` yields null, never zero. A real score of zero
remains zero. Rows require a unique, nonempty string id, finite probability in
[0, 1], and, if present, an integer `risk_score` in [0, 100] (no coercion or explicit
null). Extra rows and metadata are tolerated. Invalid JSON/rows, duplicate ids,
permission errors, network failures, and other S3 errors fail the request (500),
rather than presenting accounts as unscored. `/healthz` remains process-only.

`GET /accounts?high_risk=true` selects only scored accounts with scores >=70,
combined with `q` and `industry`, **before** pagination and total calculation.
The boolean defaults to false. Missing/legacy scores are excluded when true.
The console interprets 0–39 as Low, 40–69 as Medium, 70–100 as High, and null as
Not scored; those labels/colors are not API fields.

Merge/roll out in order: **risk-engine -> accounts-api -> ops-console**.
The API's runtime role needs `s3:GetObject` on `scores/latest.json` in addition to
account input. See DEPLOY.md; no deployment is performed by local tests.

For isolated local validation use port 8102:

```sh
uv sync --locked
LOCAL_DATA_DIR=./data uv run uvicorn accounts_api.main:app --host 127.0.0.1 --port 8102
# In another terminal:
BASE_URL=http://127.0.0.1:8102 uv run pytest tests/contract
```

The bundled dataset has no score file, so it exercises nulls by default. To test
scored/legacy cases live, point `LOCAL_DATA_DIR` at an isolated fixture directory
containing `accounts/accounts.json` and the artifact above at `scores/latest.json`.
