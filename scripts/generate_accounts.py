"""Generate 200 deterministic, entirely fictional customer accounts."""

import json
import random
from datetime import date, timedelta
from pathlib import Path


def generate(seed=858, count=200):
    rng = random.Random(seed)
    prefixes = ["Cedar", "Harbor", "Atlas", "Juniper", "Summit", "Orion", "Willow", "Beacon"]
    suffixes = ["Systems", "Labs", "Partners", "Works", "Group"]
    rows = []
    for i in range(1, count + 1):
        plan = rng.choice(["starter", "business", "enterprise"])
        rows.append(
            {
                "id": f"acct_{i:04d}",
                "name": f"{rng.choice(prefixes)} {rng.choice(suffixes)} {i:03d}",
                "industry": rng.choice(
                    ["technology", "healthcare", "retail", "finance", "manufacturing"]
                ),
                "country": rng.choice(["US", "GB", "IN", "DE", "CA", "AU"]),
                "plan": plan,
                "monthly_spend_usd": round(
                    rng.uniform(100, {"starter": 900, "business": 6000, "enterprise": 25000}[plan]),
                    2,
                ),
                "open_tickets": rng.randint(0, 14),
                "days_since_last_login": rng.randint(0, 100),
                "created_at": (date(2025, 1, 1) - timedelta(days=rng.randint(0, 1095))).isoformat(),
            }
        )
    return rows


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "data/accounts/accounts.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(generate(), indent=2) + "\n")
