import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field

from app.services.work_mode import detect_work_mode


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

    @computed_field
    @property
    def work_mode(self) -> str | None:
        """"remote" | "hybrid" | "onsite" si la oferta lo dice; None si no."""
        return detect_work_mode({"title": self.title, "location": self.location, "description": self.description})
