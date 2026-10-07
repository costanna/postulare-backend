import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.types import GUID


class UserCv(Base):
    """CV guardado por el usuario en un idioma (es/ca/en). Se adjunta tal cual
    al enviar si la oferta va en ese idioma; si no hay, se genera uno."""

    __tablename__ = "user_cvs"
    __table_args__ = (UniqueConstraint("user_id", "language", name="uq_user_cvs_user_language"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="cvs")


class TargetCompany(Base):
    """Empresa para candidaturas espontáneas: consultoras y tech que aceptan
    CV por email. La gestiona cada usuario (nombre + email + idioma)."""

    __tablename__ = "target_companies"
    __table_args__ = (UniqueConstraint("user_id", "email", name="uq_targets_user_email"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False, default="es")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Etiquetas para el matching del piloto ("python", "backend", "remoto"...):
    # solo se envía a empresas que encajan con tu CV.
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="targets")


class EmailSend(Base):
    """Registro de cada envío por email: base del tope diario (5/día) y del
    margen de 15 días antes de volver a escribir a la misma empresa."""

    __tablename__ = "email_sends"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    match_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("matches.id", ondelete="SET NULL"), nullable=True
    )
    target_company_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("target_companies.id", ondelete="SET NULL"), nullable=True
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="offer")

    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="email_sends")
