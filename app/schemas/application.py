import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ApplicationStatus


class ApplicationCreate(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    position: str = Field(min_length=1, max_length=255)
    status: ApplicationStatus = ApplicationStatus.saved
    source: str | None = None
    salary_range: str | None = None
    job_url: str | None = None
    notes: str | None = None
    applied_at: date | None = None


class ApplicationUpdate(BaseModel):
    """PATCH parcial: solo se actualizan los campos enviados."""

    company_name: str | None = Field(default=None, min_length=1, max_length=255)
    position: str | None = Field(default=None, min_length=1, max_length=255)
    status: ApplicationStatus | None = None
    source: str | None = None
    salary_range: str | None = None
    job_url: str | None = None
    notes: str | None = None
    applied_at: date | None = None

    @field_validator("company_name", "position", "status")
    @classmethod
    def _not_null(cls, value):
        if value is None:
            raise ValueError("Este campo no puede ser nulo")
        return value


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    company_name: str
    position: str
    status: ApplicationStatus
    source: str | None = None
    salary_range: str | None = None
    job_url: str | None = None
    notes: str | None = None
    applied_at: date | None = None
    created_at: datetime
    updated_at: datetime


class FollowUpRead(BaseModel):
    """Candidatura que lleva días sin novedades y conviene reactivar."""

    application: ApplicationRead
    days_waiting: int
    last_activity: date
