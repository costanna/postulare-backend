import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.types import GUID
from app.models.enums import PreferredLanguage, Seniority


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Perfil - base del matching
    skills: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    desired_position: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seniority: Mapped[Seniority | None] = mapped_column(Enum(Seniority, name="seniority_enum"), nullable=True)
    min_salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preferred_language: Mapped[PreferredLanguage] = mapped_column(
        Enum(PreferredLanguage, name="preferred_language_enum"),
        default=PreferredLanguage.es,
        nullable=False,
    )

    last_match_search_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    applications: Mapped[list["Application"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    matches: Mapped[list["Match"]] = relationship(back_populates="user", cascade="all, delete-orphan")
