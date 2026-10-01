"""Join the latest Batch scores to accounts without deriving scores from probability."""

from accounts_api.storage import JsonStore


def risk_scores(store: JsonStore) -> dict[str, int]:
    artifact = store.read_optional("scores/latest.json")
    if artifact is None:
        return {}
    scores = artifact["scores"]
    result = {}
    for entry in scores:
        account_id = entry["id"]
        if not isinstance(account_id, str):
            raise ValueError("Score id must be a string")
        score = entry.get("risk_score")
        if score is not None and (type(score) is not int or not 0 <= score <= 100):
            raise ValueError("risk_score must be an integer between 0 and 100")
        if score is not None:
            result[account_id] = score
    return result


def with_risk(account: dict, scores: dict[str, int]) -> dict:
    return {**account, "risk_score": scores.get(account["id"])}
