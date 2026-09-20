import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

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
    about: str | None = None
    is_demo: bool = False
    created_at: datetime


class ProfileUpdate(BaseModel):
    full_name: str | None = None
    skills: list[str] | None = None
    location: str | None = None
    desired_position: str | None = None
    seniority: Seniority | None = None
    min_salary: int | None = Field(default=None, ge=0)
    preferred_language: PreferredLanguage | None = None
    about: str | None = Field(default=None, max_length=2000)

    @field_validator("skills", "preferred_language")
    @classmethod
    def _not_null(cls, value):
        if value is None:
            raise ValueError("Este campo no puede ser nulo")
        return value


class CvImportResult(BaseModel):
    full_name: str | None = None
    desired_position: str | None = None
    location: str | None = None
    seniority: Seniority | None = None
    skills: list[str] = Field(default_factory=list)
    about: str | None = None
