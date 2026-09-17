import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.models.event import Event
from app.models.user import User
from app.routers.applications import _get_owned_application
from app.schemas.event import EventCreate, EventRead

router = APIRouter(tags=["events"])


@router.get("/applications/{application_id}/events", response_model=list[EventRead])
def list_events(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Event]:
    application = _get_owned_application(application_id, db, current_user)
    return (
        db.query(Event)
        .filter(Event.application_id == application.id)
        .order_by(Event.event_date.desc())
        .all()
    )


@router.post(
    "/applications/{application_id}/events",
    response_model=EventRead,
    status_code=status.HTTP_201_CREATED,
)
def create_event(
    application_id: uuid.UUID,
    payload: EventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Event:
    application = _get_owned_application(application_id, db, current_user)

    data = payload.model_dump(exclude_unset=True)
    event = Event(application_id=application.id, **data)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(
    event_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    event = (
        db.query(Event)
        .join(Event.application)
        .filter(Event.id == event_id, Event.application.has(user_id=current_user.id))
        .first()
    )
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evento no encontrado")

    db.delete(event)
    db.commit()
