"""Límites de envío: 5/día a empresas distintas y margen entre reenvíos.

Ofertas: 15 días entre envíos a la misma empresa (OFFER_RESEND_DAYS).
Espontáneas: 30 días (SPONTANEOUS_RESEND_DAYS). Todo se apoya en la tabla
email_sends (ver models/outreach.py), compartida por ambos flujos.
"""
from datetime import datetime, timezone
import re

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.outreach import EmailSend, UserCv
from app.services.duplicates import normalize

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


def days_until_retry(db: Session, user_id: object, company_name: str | None, cooldown_days: int) -> int:
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
    return max(0, cooldown_days - elapsed.days)


def check_send_allowed(
    db: Session, user_id: object, company_name: str | None, cooldown_days: int
) -> tuple[bool, str]:
    """(permitido, motivo). El motivo sirve para el mensaje de error (409/429)."""
    if sends_today(db, user_id) >= settings.SEND_EMAIL_DAILY_LIMIT_PER_USER:
        return False, "daily_limit"
    waiting = days_until_retry(db, user_id, company_name, cooldown_days)
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


def cv_for_sending(db: Session, user: object, language: str) -> tuple[str, bytes, str, str]:
    """CV a usar en el envío: (mostrar_md, pdf_bytes, pdf_nombre, origen).

    El adjunto siempre es PDF: el original subido o uno generado desde el
    texto (guardado o generado del perfil). Origen: "pdf", "saved" o "generated".
    """
    from app.services.cv_document import CvData, render_cv_markdown, render_cv_text
    from app.services.cv_pdf import text_to_pdf

    default_name = f"CV-{(user.full_name or 'candidatura').strip()}.pdf"
    row = (
        db.query(UserCv)
        .filter(UserCv.user_id == user.id, UserCv.language == language)
        .first()
    )
    if row is not None and row.file_data:
        text = row.content.strip() if row.content and row.content.strip() else ""
        return text, bytes(row.file_data), row.filename or "CV.pdf", "pdf"
    if row is not None and row.content and row.content.strip():
        text = row.content.strip()
        return text, text_to_pdf(text), default_name, "saved"
    cv = CvData(
        full_name=user.full_name,
        desired_position=user.desired_position,
        location=user.location,
        seniority=user.seniority.value if user.seniority else None,
        skills=list(user.skills or []),
        about=user.about,
        email=user.email,
    )
    return (
        render_cv_markdown(cv, language),
        text_to_pdf(render_cv_text(cv, language)),
        default_name,
        "generated",
    )


def score_target(skills: list[str], desired_position: str | None, tags: list[str]) -> int:
    """Afinidad empresa-CV para el piloto: tags que casan con tus skills (x2)
    y con tu puesto deseado (x1). 0 = no encaja, el piloto la salta."""
    skill_set = {s.strip().lower() for s in skills if s and s.strip()}
    position_words = set(re.findall(r"[\w+#.]+", (desired_position or "").lower()))
    score = 0
    for tag in tags:
        clean = (tag or "").strip().lower()
        if not clean:
            continue
        if clean in skill_set:
            score += 2
        elif clean in position_words:
            score += 1
    return score
