import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.types import GUID
from app.models.enums import MatchStatus


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("user_id", "job_offer_id", name="uq_matches_user_job_offer"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_offer_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("job_offers.id", ondelete="CASCADE"), nullable=False, index=True
    )

    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[MatchStatus] = mapped_column(
        Enum(MatchStatus, name="match_status_enum"), default=MatchStatus.new, nullable=False, index=True
    )

    # Carta de presentación generada para esta oferta ("ai" = Claude, "template" = plantilla sin IA)
    cover_letter: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_letter_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cover_letter_language: Mapped[str | None] = mapped_column(String(2), nullable=True)
    cover_letter_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="matches")
    job_offer: Mapped["JobOffer"] = relationship(back_populates="matches")
