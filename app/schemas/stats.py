from pydantic import BaseModel

from app.models.enums import ApplicationStatus


class StatsSummary(BaseModel):
    total_applications: int
    total_applied: int
    total_interviews: int
    total_offers: int
    total_rejected: int
    response_rate: float  # porcentaje 0-100


class StatusCount(BaseModel):
    status: ApplicationStatus
    count: int


class TimelinePoint(BaseModel):
    month: str  # formato YYYY-MM
    count: int


class SourceCount(BaseModel):
    source: str | None  # None = candidatura sin origen indicado
    count: int
