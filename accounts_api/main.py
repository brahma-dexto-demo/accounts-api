"""Read-only customer account API. Wire names remain snake_case."""

from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

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


@app.get("/accounts", response_model=AccountsPage)
def list_accounts(
    industry: str | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    store: JsonStore = Depends(get_store),
):
    accounts = store.read("accounts/accounts.json")
    if industry:
        accounts = [a for a in accounts if a["industry"].casefold() == industry.casefold()]
    if q:
        accounts = [a for a in accounts if q.casefold() in a["name"].casefold()]
    return {
        "accounts": accounts[offset : offset + limit],
        "total": len(accounts),
        "limit": limit,
        "offset": offset,
    }


@app.get(
    "/accounts/{id}",
    response_model=Account,
    responses={404: {"model": ErrorResponse, "description": "Account not found"}},
)
def get_account(id: str, store: JsonStore = Depends(get_store)):
    for account in store.read("accounts/accounts.json"):
        if account["id"] == id:
            return account
    raise HTTPException(status_code=404, detail="Account not found")
