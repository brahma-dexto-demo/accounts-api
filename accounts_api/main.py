"""Read-only customer account API. Wire names remain snake_case."""

from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from accounts_api.scores import read_scores
from accounts_api.storage import JsonStore

app = FastAPI(title="Accounts API", version="0.1.0")


class Account(BaseModel):
    id: str
    name: str
    industry: str
    country: str
    plan: str
    monthly_spend_usd: float = Field(ge=0)
    open_tickets: int = Field(ge=0)
    days_since_last_login: int = Field(ge=0)
    created_at: date
    risk_score: int | None = Field(default=None, ge=0, le=100)


class ErrorResponse(BaseModel):
    detail: str


class AccountsPage(BaseModel):
    accounts: list[Account]
    total: int
    limit: int
    offset: int


def get_store():
    return JsonStore()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/accounts",
    response_model=AccountsPage,
    responses={503: {"model": ErrorResponse, "description": "Risk scores unavailable"}},
)
def list_accounts(
    industry: str | None = None,
    q: str | None = None,
    high_risk: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    store: JsonStore = Depends(get_store),
):
    scores = read_scores(store)
    accounts = [
        {**account, "risk_score": scores.get(account["id"])}
        for account in store.read("accounts/accounts.json")
    ]
    if industry:
        accounts = [a for a in accounts if a["industry"].casefold() == industry.casefold()]
    if q:
        accounts = [a for a in accounts if q.casefold() in a["name"].casefold()]
    if high_risk:
        accounts = [
            a for a in accounts if a["risk_score"] is not None and a["risk_score"] >= 70
        ]
    return {
        "accounts": accounts[offset : offset + limit],
        "total": len(accounts),
        "limit": limit,
        "offset": offset,
    }


@app.get(
    "/accounts/{id}",
    response_model=Account,
    responses={
        404: {"model": ErrorResponse, "description": "Account not found"},
        503: {"model": ErrorResponse, "description": "Risk scores unavailable"},
    },
)
def get_account(id: str, store: JsonStore = Depends(get_store)):
    for account in store.read("accounts/accounts.json"):
        if account["id"] == id:
            return {**account, "risk_score": read_scores(store).get(id)}
    raise HTTPException(status_code=404, detail="Account not found")
