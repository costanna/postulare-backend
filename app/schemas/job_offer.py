import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobOfferRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    title: str
    company_name: str | None = None
    location: str | None = None
    description: str | None = None
    salary_range: str | None = None
    url: str | None = None
    fetched_at: datetime
