from datetime import date

from sqlalchemy import Date, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class AdzunaUsage(Base):
    """Llamadas REALES a Adzuna por día (UTC), sumadas entre todos los usuarios.

    Sirve para el tope global ADZUNA_DAILY_LIMIT: es la única defensa que no
    depende de quién llame ni desde dónde (los límites por IP y por usuario
    se pueden rodear; este contador no).
    """

    __tablename__ = "adzuna_usage"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
