"""Límites de envío: 5/día a empresas distintas y 15 días entre envíos a la misma.

Todo se apoya en la tabla email_sends (ver models/outreach.py), que comparten
los envíos a ofertas y las candidaturas espontáneas.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.outreach import EmailSend, UserCv
from app.services.duplicates import normalize

RESEND_COOLDOWN_DAYS = 15

# Sufijos legales que no distinguen empresas ("Acme SL" == "Acme S.A.").
_COMPANY_SUFFIXES = {
    "sl", "slu", "sa", "sau", "s l", "s a", "sc", "scoop", "cb",
    "gmbh", "ag", "ug", "ltd", "limited", "inc", "llc", "corp", "co",
    "bv", "nv", "sas", "sasu", "sarl", "srl", "spa", "ab", "oy", "as",
    "aps", "lda", "plc", "pty",
}


def normalize_company(name: str | None) -> str:
    tokens = normalize(name).split()
    # Sufijos legales en cualquier forma ("SL", "S.L.", "S.L.U.", "S.A."):
    # tras normalizar quedan como "sl" o como letras sueltas ("s l u").
    # Solo se pelan letras típicas de sufijos: un "0" final ("Empresa 0") sí distingue.
    while len(tokens) > 1 and (tokens[-1] in _COMPANY_SUFFIXES or tokens[-1] in ("s", "l", "a", "u")):
        tokens.pop()
    return " ".join(tokens)


def _today_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def sends_today(db: Session, user_id: object) -> int:
    return (
        db.query(EmailSend)
        .filter(EmailSend.user_id == user_id, EmailSend.sent_at >= _today_start())
        .count()
    )


def days_until_retry(db: Session, user_id: object, company_name: str | None) -> int:
    """Días que faltan para poder reenviar a esta empresa (0 = se puede)."""
    key = normalize_company(company_name)
    if not key:
        return 0
    last: datetime | None = (
        db.query(EmailSend.sent_at)
        .filter(EmailSend.user_id == user_id, EmailSend.company_key == key)
        .order_by(EmailSend.sent_at.desc())
        .limit(1)
        .scalar()
    )
    if last is None:
        return 0
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    elapsed = datetime.now(timezone.utc) - last
    remaining = RESEND_COOLDOWN_DAYS - elapsed.days
    return max(0, remaining)


def check_send_allowed(db: Session, user_id: object, company_name: str | None) -> tuple[bool, str]:
    """(permitido, motivo). El motivo sirve para el mensaje de error (409/429)."""
    if sends_today(db, user_id) >= settings.SEND_EMAIL_DAILY_LIMIT_PER_USER:
        return False, "daily_limit"
    waiting = days_until_retry(db, user_id, company_name)
    if waiting > 0:
        return False, f"cooldown:{waiting}"
    return True, ""


def record_email_send(
    db: Session,
    *,
    user_id: object,
    company_name: str,
    contact_email: str,
    language: str,
    kind: str,
    match_id: object | None = None,
    target_company_id: object | None = None,
) -> EmailSend:
    row = EmailSend(
        user_id=user_id,
        match_id=match_id,
        target_company_id=target_company_id,
        company_name=company_name,
        company_key=normalize_company(company_name),
        contact_email=contact_email,
        language=language,
        kind=kind,
    )
    db.add(row)
    db.flush()
    return row


def user_cv_for_language(db: Session, user_id: object, language: str) -> str | None:
    content = (
        db.query(UserCv.content)
        .filter(UserCv.user_id == user_id, UserCv.language == language)
        .scalar()
    )
    return content.strip() if content and content.strip() else None
