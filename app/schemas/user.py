import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import PreferredLanguage, Seniority


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str | None = None
    skills: list[str] = Field(default_factory=list)
    location: str | None = None
    desired_position: str | None = None
    seniority: Seniority | None = None
    min_salary: int | None = None
    preferred_language: PreferredLanguage
    created_at: datetime


class ProfileUpdate(BaseModel):
    """Todos los campos son opcionales: PATCH parcial del perfil."""

    full_name: str | None = None
    skills: list[str] | None = None
    location: str | None = None
    desired_position: str | None = None
    seniority: Seniority | None = None
    min_salary: int | None = Field(default=None, ge=0)
    preferred_language: PreferredLanguage | None = None
