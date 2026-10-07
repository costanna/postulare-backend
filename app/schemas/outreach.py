import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.application import ApplicationRead


class UserCvRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    language: str
    content: str
    updated_at: datetime


class UserCvUpsert(BaseModel):
    # Vacío = borrar el CV de ese idioma.
    content: str = Field(default="", max_length=10000)


class TargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr = Field(max_length=255)
    language: str = Field(default="es", pattern="^(es|ca|en)$")
    notes: str | None = Field(default=None, max_length=2000)
    # Etiquetas para el matching del piloto ("python", "backend"...).
    tags: list[str] = Field(default_factory=list, max_length=20)


class TargetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)
    language: str | None = Field(default=None, pattern="^(es|ca|en)$")
    notes: str | None = Field(default=None, max_length=2000)
    tags: list[str] | None = Field(default=None, max_length=20)


class TargetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    language: str
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    last_sent_at: datetime | None = None
    # Días para poder reenviar a esta empresa (0 = se puede hoy)
    retry_in_days: int = 0
    can_send: bool = True
    # Afinidad con tu CV (tags vs skills/puesto). 0 = el piloto la salta.
    match_score: int = 0


class TargetSendResult(BaseModel):
    target_id: uuid.UUID
    ok: bool
    sent_to: str | None = None
    error: str | None = None


class BulkSendRequest(BaseModel):
    target_ids: list[uuid.UUID] = Field(max_length=20)


class BulkSendRead(BaseModel):
    sent: list[TargetSendResult]
    daily_remaining: int | None = None


class SpontaneousSendRead(BaseModel):
    application: ApplicationRead
    target: TargetRead
    sent_to: str
    subject: str
    language: str
    cv_source: str = "generated"


class AutopilotRequest(BaseModel):
    # Cuántas como máximo (el tope diario de 5/día manda igualmente).
    limit: int = Field(default=5, ge=1, le=5)


class AutopilotRead(BaseModel):
    sent: list[TargetSendResult]
    skipped: int = 0
    daily_remaining: int | None = None
