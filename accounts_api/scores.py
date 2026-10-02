"""Validate the producer contract; never calculate or default a missing score."""

import math
from datetime import datetime

from fastapi import HTTPException
from pydantic import BaseModel, Field, StrictFloat, StrictInt, StrictStr, model_validator

from accounts_api.storage import JsonStore


class Score(BaseModel):
    id: StrictStr = Field(min_length=1)
    probability: StrictFloat = Field(ge=0, le=1, allow_inf_nan=False)
    risk_score: StrictInt = Field(ge=0, le=100)

    @model_validator(mode="after")
    def consistent_score(self):
        if self.risk_score != math.floor(self.probability * 100 + 0.5):
            raise ValueError("risk_score does not match probability")
        return self


class ScoreArtifact(BaseModel):
    model_version: StrictStr = Field(min_length=1)
    generated_at: datetime
    scores: list[Score]

    @model_validator(mode="before")
    @classmethod
    def timestamp_is_string(cls, value):
        if isinstance(value, dict) and not isinstance(value.get("generated_at"), str):
            raise ValueError("generated_at must be an ISO timestamp string")
        return value

    @model_validator(mode="after")
    def unique_ids(self):
        if len({score.id for score in self.scores}) != len(self.scores):
            raise ValueError("duplicate score ids")
        return self


def read_scores(store: JsonStore) -> dict[str, int]:
    try:
        value = store.read("scores/latest.json")
    except FileNotFoundError:
        return {}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Risk scores unavailable") from exc
    try:
        artifact = ScoreArtifact.model_validate(value)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Risk scores unavailable") from exc
    return {score.id: score.risk_score for score in artifact.scores}
