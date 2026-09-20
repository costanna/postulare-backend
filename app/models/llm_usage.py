from datetime import date

from sqlalchemy import Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class LlmUsage(Base):
    """Llamadas REALES a la IA (Claude) y a InfoJobs por día (UTC).

    `scope` = "global" (todos los usuarios juntos, tope LLM_DAILY_LIMIT), "user:<id>"
    (tope COVER_LETTER_DAILY_LIMIT_PER_USER) o "infojobs" (tope INFOJOBS_DAILY_LIMIT).
    A diferencia de Adzuna (gratis), cada llamada a la IA cuesta dinero: el tope global
    es la garantía de que el gasto máximo diario es conocido.
    """

    __tablename__ = "llm_usage"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    scope: Mapped[str] = mapped_column(String(64), primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
