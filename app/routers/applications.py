import csv
import io
import uuid
from datetime import date, datetime, timezone
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.db.session import get_db
from app.deps import get_current_user
from app.models.application import Application
from app.models.enums import ApplicationStatus
from app.models.user import User
from app.schemas.application import ApplicationCreate, ApplicationRead, ApplicationUpdate, FollowUpRead
from app.schemas.common import Page

# Marca de orden de bytes UTF-8: sin ella Excel abre el CSV con las tildes rotas
_BOM = chr(0xFEFF)

router = APIRouter(prefix="/applications", tags=["applications"])


def _get_owned_application(application_id: uuid.UUID, db: Session, current_user: User) -> Application:
    application = (
        db.query(Application)
        .filter(Application.id == application_id, Application.user_id == current_user.id)
        .first()
    )
    if application is None:
        # 404, no 403: nunca confirmamos que la candidatura existe si es de otro usuario.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidatura no encontrada")
    return application


@router.get("", response_model=Page[ApplicationRead])
def list_applications(
    status_filter: ApplicationStatus | None = Query(default=None, alias="status"),
    company: str | None = Query(default=None, description="Búsqueda parcial por nombre de empresa"),
    date_from: date | None = Query(default=None, description="applied_at >= date_from"),
    date_to: date | None = Query(default=None, description="applied_at <= date_to"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[ApplicationRead]:
    query = db.query(Application).filter(Application.user_id == current_user.id)

    if status_filter is not None:
        query = query.filter(Application.status == status_filter)
    if company:
        query = query.filter(or_(Application.company_name.ilike(f"%{company}%")))
    if date_from is not None:
        query = query.filter(Application.applied_at >= date_from)
    if date_to is not None:
        query = query.filter(Application.applied_at <= date_to)

    total = query.count()
    items = (
        query.order_by(Application.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return Page(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if total else 0,
    )


@router.post("", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
def create_application(
    payload: ApplicationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Application:
    application = Application(user_id=current_user.id, **payload.model_dump())
    db.add(application)
    db.commit()
    db.refresh(application)
    return application


@router.get("/follow-ups", response_model=list[FollowUpRead])
def list_follow_ups(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[FollowUpRead]:
    """Candidaturas abiertas (aplicada / en entrevistas) sin novedades desde hace FOLLOW_UP_DAYS
    o más. Cualquier evento (incluido un "seguimiento") reinicia la cuenta."""
    applications = (
        db.query(Application)
        .options(selectinload(Application.events))
        .filter(
            Application.user_id == current_user.id,
            Application.status.in_([ApplicationStatus.applied, ApplicationStatus.interview]),
        )
        .all()
    )

    today = datetime.now(timezone.utc).date()
    due: list[FollowUpRead] = []
    for application in applications:
        activity = [event.event_date.date() for event in application.events]
        activity.append(application.applied_at or application.created_at.date())
        last_activity = max(activity)
        days_waiting = (today - last_activity).days
        if days_waiting >= settings.FOLLOW_UP_DAYS:
            due.append(
                FollowUpRead(
                    application=ApplicationRead.model_validate(application),
                    days_waiting=days_waiting,
                    last_activity=last_activity,
                )
            )

    due.sort(key=lambda item: item.days_waiting, reverse=True)
    return due[:50]


def _csv_safe(value: object) -> str:
    """Neutraliza la inyección de fórmulas: Excel/Sheets ejecutan celdas que empiezan por = + - @."""
    text = "" if value is None else str(value)
    return f"'{text}" if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@router.get("/export")
def export_applications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Todas las candidaturas del usuario en CSV (UTF-8 con BOM para que Excel respete las tildes)."""
    applications = (
        db.query(Application)
        .filter(Application.user_id == current_user.id)
        .order_by(Application.created_at.desc())
        .all()
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["company", "position", "status", "applied_at", "source", "salary_range", "job_url", "notes", "created_at"]
    )
    for application in applications:
        writer.writerow(
            [
                _csv_safe(application.company_name),
                _csv_safe(application.position),
                application.status.value,
                application.applied_at.isoformat() if application.applied_at else "",
                _csv_safe(application.source),
                _csv_safe(application.salary_range),
                _csv_safe(application.job_url),
                _csv_safe(application.notes),
                application.created_at.date().isoformat() if application.created_at else "",
            ]
        )

    return Response(
        content=_BOM + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="postulare-candidaturas.csv"'},
    )


@router.get("/{application_id}", response_model=ApplicationRead)
def get_application(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Application:
    return _get_owned_application(application_id, db, current_user)


@router.patch("/{application_id}", response_model=ApplicationRead)
def update_application(
    application_id: uuid.UUID,
    payload: ApplicationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Application:
    application = _get_owned_application(application_id, db, current_user)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(application, field, value)

    db.add(application)
    db.commit()
    db.refresh(application)
    return application


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    application = _get_owned_application(application_id, db, current_user)
    db.delete(application)
    db.commit()
