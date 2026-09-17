import uuid
from datetime import date
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.models.application import Application
from app.models.enums import ApplicationStatus
from app.models.user import User
from app.schemas.application import ApplicationCreate, ApplicationRead, ApplicationUpdate
from app.schemas.common import Page

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
