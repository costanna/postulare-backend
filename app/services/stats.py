"""Cálculo de las estadísticas del dashboard.

Se hace la agregación en Python (no con GROUP BY específico de un dialecto de
SQL) para que el mismo código funcione igual en SQLite (tests) y PostgreSQL
(producción), dado el volumen de datos esperado (candidaturas de una persona).
"""
import uuid
from collections import Counter, defaultdict

from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.enums import ApplicationStatus

RESPONDED_STATUSES = {ApplicationStatus.interview, ApplicationStatus.offer, ApplicationStatus.rejected}


def _user_applications(db: Session, user_id: uuid.UUID) -> list[Application]:
    return db.query(Application).filter(Application.user_id == user_id).all()


def get_summary(db: Session, user_id: uuid.UUID) -> dict:
    applications = _user_applications(db, user_id)
    total = len(applications)
    total_applied = sum(1 for a in applications if a.status != ApplicationStatus.saved)
    responded = sum(1 for a in applications if a.status in RESPONDED_STATUSES)

    return {
        "total_applications": total,
        "total_applied": total_applied,
        "total_interviews": sum(1 for a in applications if a.status == ApplicationStatus.interview),
        "total_offers": sum(1 for a in applications if a.status == ApplicationStatus.offer),
        "total_rejected": sum(1 for a in applications if a.status == ApplicationStatus.rejected),
        "response_rate": round((responded / total_applied) * 100, 1) if total_applied else 0.0,
    }


def get_by_status(db: Session, user_id: uuid.UUID) -> list[dict]:
    applications = _user_applications(db, user_id)
    counts = Counter(a.status for a in applications)
    # Incluye todos los estados posibles (incluso con 0) para que el gráfico
    # de barras del frontend no tenga que rellenar huecos.
    return [{"status": s, "count": counts.get(s, 0)} for s in ApplicationStatus]


def get_timeline(db: Session, user_id: uuid.UUID) -> list[dict]:
    applications = _user_applications(db, user_id)
    counts: dict[str, int] = defaultdict(int)
    for application in applications:
        reference_date = application.applied_at or application.created_at.date()
        counts[reference_date.strftime("%Y-%m")] += 1
    return [{"month": month, "count": count} for month, count in sorted(counts.items())]


def get_by_source(db: Session, user_id: uuid.UUID) -> list[dict]:
    applications = _user_applications(db, user_id)
    # source=None se deja tal cual (en vez de una etiqueta fija tipo
    # "Desconocido"): el texto es cosa del frontend, que lo traduce según
    # el idioma activo.
    counts = Counter(a.source for a in applications)
    return [
        {"source": source, "count": count}
        for source, count in sorted(counts.items(), key=lambda item: (-item[1], item[0] or ""))
    ]
