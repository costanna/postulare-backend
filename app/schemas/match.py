import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import MatchStatus
from app.schemas.job_offer import JobOfferRead


class MatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    score: int
    reasoning: str | None = None
    status: MatchStatus
    created_at: datetime
    job_offer: JobOfferRead


class MatchSearchResult(BaseModel):
    fetched: int
    new_matches: int
    updated_matches: int
