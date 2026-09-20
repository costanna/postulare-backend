"""Topes diarios de uso de la IA (cada llamada cuesta dinero).

Dos contadores por día (UTC) en la tabla llm_usage: uno global y otro por
usuario. `try_consume` es atómico en Postgres (SELECT ... FOR UPDATE); el
tope global es lo que acota el gasto máximo diario pase lo que pase.
"""
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.llm_usage import LlmUsage

GLOBAL_SCOPE = "global"


def user_scope(user_id: object) -> str:
    return f"user:{user_id}"


def _today():
    return datetime.now(timezone.utc).date()


def used_today(db: Session, scope: str) -> int:
    return db.query(LlmUsage.calls).filter(LlmUsage.day == _today(), LlmUsage.scope == scope).scalar() or 0


def remaining(db: Session, scope: str, limit: int) -> int | None:
    if limit <= 0:
        return None
    return max(0, limit - used_today(db, scope))


def try_consume(db: Session, scope: str, limit: int) -> bool:
    if limit <= 0:
        return True

    today = _today()

    def _row() -> LlmUsage | None:
        return (
            db.query(LlmUsage)
            .filter(LlmUsage.day == today, LlmUsage.scope == scope)
            .with_for_update()
            .first()
        )

    row = _row()
    if row is None:
        db.add(LlmUsage(day=today, scope=scope, calls=0))
        try:
            db.flush()
        except IntegrityError:  # otra petición creó la fila a la vez
            db.rollback()
        row = _row()

    if row.calls >= limit:
        return False
    row.calls += 1
    db.commit()
    return True


def release(db: Session, scope: str) -> None:
    row = db.query(LlmUsage).filter(LlmUsage.day == _today(), LlmUsage.scope == scope).with_for_update().first()
    if row is not None and row.calls > 0:
        row.calls -= 1
        db.commit()
