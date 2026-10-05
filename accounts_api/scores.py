"""Validate engine-owned scores without calculating or coercing risk scores."""

import math

from accounts_api.storage import JsonStore


def read_scores(store: JsonStore) -> dict[str, int | None]:
    artifact = store.read_optional_scores()
    if not isinstance(artifact, dict) or not isinstance(artifact.get("scores"), list):
        raise ValueError("Score artifact must contain a scores array")
    scores = {}
    for row in artifact["scores"]:
        if not isinstance(row, dict):
            raise ValueError("Score row must be an object")
        account_id = row.get("id")
        if not isinstance(account_id, str) or not account_id.strip() or account_id in scores:
            raise ValueError("Score ids must be nonempty, unique strings")
        probability = row.get("probability")
        if (
            type(probability) not in (int, float)
            or not math.isfinite(probability)
            or not 0 <= probability <= 1
        ):
            raise ValueError("Score probability must be finite and in [0, 1]")
        risk_score = row.get("risk_score")
        if "risk_score" in row and (type(risk_score) is not int or not 0 <= risk_score <= 100):
            raise ValueError("risk_score must be an integer in [0, 100]")
        scores[account_id] = risk_score
    return scores


def scored_accounts(store: JsonStore) -> list[dict]:
    accounts = store.read("accounts/accounts.json")
    scores = read_scores(store)
    return [{**account, "risk_score": scores.get(account["id"])} for account in accounts]
