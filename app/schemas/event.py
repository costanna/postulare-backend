import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import EventType


class EventCreate(BaseModel):
    type: EventType
    description: str | None = None
    event_date: datetime | None = None


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    type: EventType
    description: str | None = None
    event_date: datetime
