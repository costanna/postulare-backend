"""Reglas al cambiar una candidatura de estado: fecha de aplicación y rastro en la línea de tiempo."""
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.enums import ApplicationStatus, EventType
from app.models.event import Event

APPLIED_OR_LATER = {
    ApplicationStatus.applied,
    ApplicationStatus.interview,
    ApplicationStatus.offer,
    ApplicationStatus.rejected,
}


def stamp_applied_date(application: Application, fallback: date | None = None) -> None:
    if application.status in APPLIED_OR_LATER and application.applied_at is None:
        application.applied_at = fallback or datetime.now(timezone.utc).date()


def record_status_change(
    db: Session, application: Application, old: ApplicationStatus, new: ApplicationStatus
) -> None:
    if old != new:
        db.add(Event(application_id=application.id, type=EventType.status_change, description=f"{old.value} → {new.value}"))
