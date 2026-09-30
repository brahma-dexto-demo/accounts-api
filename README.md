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
