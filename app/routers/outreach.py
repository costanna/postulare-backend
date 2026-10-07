"""Directorio de candidaturas espontáneas (consultoras y tech) + CVs por idioma.

Límites compartidos con el envío a ofertas: 5/día a empresas distintas y
15 días entre envíos a la misma empresa. Solo cuentas reales (403 en demo).
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.deps import get_current_user
from app.models.application import Application
from app.models.enums import ApplicationStatus
from app.models.outreach import TargetCompany, UserCv
from app.models.user import User
from app.schemas.outreach import (
    AutopilotRead,
    AutopilotRequest,
    BulkSendRead,
    BulkSendRequest,
    ImportRead,
    ImportRequest,
    SpontaneousSendRead,
    SuggestionRead,
    SuggestionsRead,
    TargetCreate,
    TargetRead,
    TargetSendRequest,
    TargetSendResult,
    TargetUpdate,
    UserCvRead,
    UserCvUpsert,
)
from app.services.application_status import stamp_applied_date
from app.services.apply_pack import (
    build_email_body,
    build_spontaneous_subject,
    extract_contact_email,
)
from app.services.ats import matched_keywords
from app.services.companies import (
    check_send_allowed,
    cv_for_sending,
    days_until_retry,
    normalize_company,
    record_email_send,
    score_target,
    sends_today,
)
from app.services.cover_letter import Candidate, build_spontaneous_letter
from app.services.cv_mailer import MailerError, send_application_email, smtp_configured
from app.services.cv_parser import CvParseError, extract_text
from app.services.hn_hiring import fetch_hn_suggestions
from app.services.job_search import JobSearchError
from app.services.lang_detect import detect_language

router = APIRouter(prefix="/targets", tags=["targets"])

CV_LANGUAGES = ("es", "ca", "en")


def _forbid_demo(user: User) -> None:
    if user.is_demo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta demo no puede enviar emails. Crea una cuenta para usar el envío.",
        )


def _get_owned_target(target_id: uuid.UUID, db: Session, user: User) -> TargetCompany:
    target = (
        db.query(TargetCompany)
        .filter(TargetCompany.id == target_id, TargetCompany.user_id == user.id)
        .first()
    )
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada")
    return target


def _last_sent_at(db: Session, user_id: object, company_name: str) -> datetime | None:
    from app.models.outreach import EmailSend

    row: datetime | None = (
        db.query(EmailSend.sent_at)
        .filter(EmailSend.user_id == user_id, EmailSend.company_key == normalize_company(company_name))
        .order_by(EmailSend.sent_at.desc())
        .limit(1)
        .scalar()
    )
    if row is not None and row.tzinfo is None:
        row = row.replace(tzinfo=timezone.utc)
    return row


def _to_read(db: Session, user: User, target: TargetCompany) -> TargetRead:
    retry = days_until_retry(db, target.user_id, target.name, settings.SPONTANEOUS_RESEND_DAYS)
    read = TargetRead.model_validate(target)
    read.last_sent_at = _last_sent_at(db, target.user_id, target.name)
    read.retry_in_days = retry
    read.can_send = retry == 0
    read.match_score = score_target(list(user.skills or []), user.desired_position, list(target.tags or []))
    return read


@router.get("/quota", response_model=dict)
def send_quota(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Cuota de envíos de hoy (compartida entre ofertas y espontáneas)."""
    _forbid_demo(current_user)
    limit = settings.SEND_EMAIL_DAILY_LIMIT_PER_USER
    used = sends_today(db, current_user.id)
    return {"daily_limit": limit, "sent_today": used, "daily_remaining": max(0, limit - used)}


@router.get("", response_model=list[TargetRead])
def list_targets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TargetRead]:
    _forbid_demo(current_user)
    targets = (
        db.query(TargetCompany)
        .filter(TargetCompany.user_id == current_user.id)
        .order_by(TargetCompany.name)
        .all()
    )
    return [_to_read(db, current_user, target) for target in targets]


@router.post("", response_model=TargetRead, status_code=status.HTTP_201_CREATED)
def create_target(
    payload: TargetCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TargetRead:
    _forbid_demo(current_user)
    target = TargetCompany(
        user_id=current_user.id,
        name=payload.name.strip(),
        email=payload.email.strip().lower(),
        language=payload.language,
        notes=payload.notes.strip() if payload.notes and payload.notes.strip() else None,
        tags=[t.strip() for t in (payload.tags or []) if t and t.strip()][:20],
    )
    db.add(target)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya tienes esa empresa en tu directorio")
    db.refresh(target)
    return _to_read(db, current_user, target)


@router.patch("/{target_id}", response_model=TargetRead)
def update_target(
    target_id: uuid.UUID,
    payload: TargetUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TargetRead:
    _forbid_demo(current_user)
    target = _get_owned_target(target_id, db, current_user)
    updates = payload.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"]:
        updates["name"] = updates["name"].strip()
    if "email" in updates and updates["email"]:
        updates["email"] = updates["email"].strip().lower()
    if "notes" in updates:
        updates["notes"] = updates["notes"].strip() or None if updates["notes"] else None
    if "tags" in updates and updates["tags"] is not None:
        updates["tags"] = [t.strip() for t in updates["tags"] if t and t.strip()][:20]
    for field, value in updates.items():
        setattr(target, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya tienes ese email en tu directorio")
    db.refresh(target)
    return _to_read(db, current_user, target)


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_target(
    target_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    _forbid_demo(current_user)
    db.delete(_get_owned_target(target_id, db, current_user))
    db.commit()


def _send_to_target(
    db: Session, user: User, target: TargetCompany, edited_letter: str | None = None
) -> tuple[Application, str, str, str, str]:
    """Envía la espontánea. Devuelve (candidatura, destino, asunto, idioma, cv_source)."""
    allowed, reason = check_send_allowed(db, user.id, target.name, settings.SPONTANEOUS_RESEND_DAYS)
    if not allowed:
        if reason == "daily_limit":
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Tope diario alcanzado ({settings.SEND_EMAIL_DAILY_LIMIT_PER_USER}/día). Vuelve mañana.",
            )
        waiting = reason.split(":")[1] if ":" in reason else "?"
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya escribiste a {target.name} hace poco: espera {waiting} días para reenviar.",
        )
    if not smtp_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Envío no configurado en el servidor (SMTP).",
        )
    language = target.language if target.language in CV_LANGUAGES else "es"
    candidate = Candidate(
        full_name=user.full_name,
        position=user.desired_position,
        seniority=user.seniority.value if user.seniority else None,
        location=user.location,
        skills=list(user.skills or []),
        about=user.about,
    )
    letter = (edited_letter or "").strip() or build_spontaneous_letter(candidate, target.name, language)
    display, pdf_bytes, pdf_name, cv_source = cv_for_sending(db, user, language)
    subject = build_spontaneous_subject(user.desired_position, user.full_name, language)
    body = build_email_body(letter, display, None, language)
    try:
        send_application_email(target.email, subject, body, pdf_bytes, pdf_name)
    except MailerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    record_email_send(
        db,
        user_id=user.id,
        company_name=target.name,
        contact_email=target.email,
        language=language,
        kind="spontaneous",
        target_company_id=target.id,
    )
    application = Application(
        user_id=user.id,
        company_name=target.name,
        position=user.desired_position or "Candidatura espontánea",
        status=ApplicationStatus.applied,
        source="spontaneous",
        job_url=None,
        notes=letter,
    )
    stamp_applied_date(application, None)
    db.add(application)
    db.commit()
    db.refresh(application)
    return application, target.email, subject, language, cv_source


@router.post("/{target_id}/send", response_model=SpontaneousSendRead, status_code=status.HTTP_201_CREATED)
def send_to_target(
    target_id: uuid.UUID,
    payload: TargetSendRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SpontaneousSendRead:
    _forbid_demo(current_user)
    target = _get_owned_target(target_id, db, current_user)
    edited = (payload.cover_letter if payload else None) or ""
    application, sent_to, subject, language, cv_source = _send_to_target(
        db, current_user, target, edited.strip() or None
    )
    return SpontaneousSendRead(
        application=application,
        target=_to_read(db, current_user, target),
        sent_to=sent_to,
        subject=subject,
        language=language,
        cv_source=cv_source,
    )


def _offer_suggestions(db: Session, user: User) -> list[SuggestionRead]:
    """Empresas de tus matches con email en la descripción + skills que casan."""
    from app.models.job_offer import JobOffer
    from app.models.match import Match

    rows = (
        db.query(JobOffer.company_name, JobOffer.title, JobOffer.description)
        .join(Match, Match.job_offer_id == JobOffer.id)
        .filter(Match.user_id == user.id)
        .all()
    )
    grouped: dict[str, dict] = {}
    for company, title, description in rows:
        key = normalize_company(company)
        if not key:
            continue
        entry = grouped.setdefault(key, {"name": (company or "").strip(), "titles": [], "descriptions": []})
        entry["titles"].append(title or "")
        entry["descriptions"].append(description or "")
    skills = list(user.skills or [])
    suggestions: list[SuggestionRead] = []
    for entry in grouped.values():
        email = extract_contact_email(*entry["descriptions"], *entry["titles"])
        if not email:
            continue
        tags = matched_keywords(" ".join(entry["titles"]), " ".join(entry["descriptions"]), skills)[:8]
        if not tags:
            continue
        suggestions.append(
            SuggestionRead(
                name=entry["name"],
                email=email,
                language=detect_language(*entry["titles"], *entry["descriptions"]),
                tags=tags,
                match_score=len(tags),
                offers_count=len(entry["titles"]),
                source="offers",
            )
        )
    suggestions.sort(key=lambda s: (-s.match_score, -s.offers_count))
    return suggestions[:20]


def _import_suggestions(db: Session, user: User, items: list[SuggestionRead]) -> tuple[int, int]:
    existing = {
        row[0].lower() for row in db.query(TargetCompany.email).filter(TargetCompany.user_id == user.id).all()
    }
    imported = skipped = 0
    for item in items[:20]:
        email = (item.email or "").strip().lower()
        if not email or email in existing:
            skipped += 1
            continue
        language = item.language if item.language in CV_LANGUAGES else "es"
        db.add(
            TargetCompany(
                user_id=user.id,
                name=item.name.strip()[:255],
                email=email,
                language=language,
                tags=[t.strip() for t in (item.tags or []) if t and t.strip()][:20],
            )
        )
        existing.add(email)
        imported += 1
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return imported, skipped


def _hn_suggestions(user: User) -> list[SuggestionRead]:
    try:
        items = fetch_hn_suggestions(list(user.skills or []))
    except JobSearchError:
        return []
    return [
        SuggestionRead(
            name=item["name"],
            email=item["email"],
            language=item["language"],
            tags=item.get("tags", []),
            match_score=item["match_score"],
            offers_count=0,
            source="hn_hiring",
        )
        for item in items
    ]


@router.get("/suggestions", response_model=SuggestionsRead)
def get_suggestions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SuggestionsRead:
    """Empresas descubiertas solas: de tus ofertas y del hilo HN mensual."""
    _forbid_demo(current_user)
    return SuggestionsRead(
        from_offers=_offer_suggestions(db, current_user),
        from_hn=_hn_suggestions(current_user),
    )


@router.post("/import", response_model=ImportRead)
def import_suggestions(
    payload: ImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportRead:
    _forbid_demo(current_user)
    imported, skipped = _import_suggestions(db, current_user, payload.items)
    return ImportRead(imported=imported, skipped=skipped)


@router.post("/autopilot", response_model=AutopilotRead, status_code=status.HTTP_201_CREATED)
def run_autopilot(
    payload: AutopilotRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AutopilotRead:
    """Piloto automático: envía (máx. 5, manda el tope diario) a las empresas
    que encajan con tu CV (tags vs skills/puesto), saltando las contactadas
    hace menos de 30 días. Sin ofertas de por medio. Se puede paralizar con
    PATCH /profile {auto_outreach_paused: true}."""
    _forbid_demo(current_user)
    if current_user.auto_outreach_paused:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Automatización paralizada: reactívala para usar el piloto.",
        )
    options = payload or AutopilotRequest()
    if not smtp_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Envío no configurado en el servidor (SMTP).",
        )
    if options.include_suggestions:
        _import_suggestions(db, current_user, _offer_suggestions(db, current_user) + _hn_suggestions(current_user))
    skills = list(current_user.skills or [])
    ranked = []
    for target in (
        db.query(TargetCompany).filter(TargetCompany.user_id == current_user.id).all()
    ):
        score = score_target(skills, current_user.desired_position, list(target.tags or []))
        if score <= 0:
            continue
        if days_until_retry(db, current_user.id, target.name, settings.SPONTANEOUS_RESEND_DAYS) > 0:
            continue
        ranked.append((score, target.name.lower(), target))
    ranked.sort(key=lambda item: (-item[0], item[1]))

    results: list[TargetSendResult] = []
    for _, _, target in ranked[: options.limit]:
        try:
            _, sent_to, _, _, _ = _send_to_target(db, current_user, target)
            results.append(TargetSendResult(target_id=target.id, ok=True, sent_to=sent_to))
        except HTTPException as exc:
            if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                break
            results.append(TargetSendResult(target_id=target.id, ok=False, error=str(exc.detail)))
    skipped = len(ranked[: options.limit]) - len(results)
    remaining = settings.SEND_EMAIL_DAILY_LIMIT_PER_USER - sends_today(db, current_user.id)
    return AutopilotRead(sent=results, skipped=skipped, daily_remaining=max(0, remaining))


@router.post("/send-bulk", response_model=BulkSendRead, status_code=status.HTTP_201_CREATED)
def send_bulk(
    payload: BulkSendRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BulkSendRead:
    """Envía a varias empresas de golpe, parando al llegar al tope diario."""
    _forbid_demo(current_user)
    results: list[TargetSendResult] = []
    for target_id in payload.target_ids[:20]:
        target = db.query(TargetCompany).filter(
            TargetCompany.id == target_id, TargetCompany.user_id == current_user.id
        ).first()
        if target is None:
            results.append(TargetSendResult(target_id=target_id, ok=False, error="no encontrada"))
            continue
        try:
            _, sent_to, _, _, _ = _send_to_target(db, current_user, target)
            results.append(TargetSendResult(target_id=target.id, ok=True, sent_to=sent_to))
        except HTTPException as exc:
            results.append(TargetSendResult(target_id=target.id, ok=False, error=str(exc.detail)))
            if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                break
    remaining = settings.SEND_EMAIL_DAILY_LIMIT_PER_USER - sends_today(db, current_user.id)
    return BulkSendRead(sent=results, daily_remaining=max(0, remaining))


# --- CVs por idioma (perfil) ---

cv_router = APIRouter(prefix="/profile/cvs", tags=["profile"])


def _cv_read(row: UserCv) -> dict:
    return {
        "language": row.language,
        "content": row.content,
        "updated_at": row.updated_at,
        "has_file": bool(row.file_data),
        "filename": row.filename,
    }


@cv_router.get("", response_model=list[UserCvRead])
def list_cvs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.query(UserCv).filter(UserCv.user_id == current_user.id).order_by(UserCv.language).all()
    return [_cv_read(row) for row in rows]


@cv_router.put("/{language}", response_model=UserCvRead)
def save_cv(
    language: str,
    payload: UserCvUpsert,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if language not in CV_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Idioma debe ser es, ca o en"
        )
    content = (payload.content or "").strip()
    existing = (
        db.query(UserCv)
        .filter(UserCv.user_id == current_user.id, UserCv.language == language)
        .first()
    )
    if not content:
        # Vacío = borrar el CV de ese idioma.
        if existing is not None:
            db.delete(existing)
            db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if existing is None:
        existing = UserCv(user_id=current_user.id, language=language, content=content)
        db.add(existing)
    else:
        # El texto manda: sustituye también el PDF si lo había.
        existing.content = content
        existing.file_data = None
        existing.filename = None
    db.commit()
    db.refresh(existing)
    return _cv_read(existing)


@cv_router.post("/{language}/file", response_model=UserCvRead)
def upload_cv_file(
    language: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Sube el CV en PDF para un idioma: se guarda el original (se adjunta al
    enviar) y se extrae el texto para mostrarlo y pegarlo."""
    if language not in CV_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Idioma debe ser es, ca o en"
        )
    data = file.file.read(settings.CV_MAX_BYTES + 1)
    if len(data) > settings.CV_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El PDF pesa demasiado (máximo {settings.CV_MAX_BYTES // 1_000_000} MB)",
        )
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="El fichero no es un PDF")
    try:
        text = extract_text(data, settings.CV_MAX_PAGES)
    except CvParseError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    filename = (file.filename or "CV.pdf").split("/")[-1].split("\\")[-1][:100] or "CV.pdf"
    existing = (
        db.query(UserCv)
        .filter(UserCv.user_id == current_user.id, UserCv.language == language)
        .first()
    )
    if existing is None:
        existing = UserCv(user_id=current_user.id, language=language, content=text[:10000])
        db.add(existing)
    else:
        existing.content = text[:10000]
    existing.file_data = data
    existing.filename = filename
    db.commit()
    db.refresh(existing)
    return _cv_read(existing)


@cv_router.delete("/{language}/file", status_code=status.HTTP_204_NO_CONTENT)
def delete_cv_file(
    language: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Quita el PDF pero conserva el texto extraído como CV de ese idioma."""
    row = (
        db.query(UserCv)
        .filter(UserCv.user_id == current_user.id, UserCv.language == language)
        .first()
    )
    if row is None or not row.file_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sin PDF en ese idioma")
    row.file_data = None
    row.filename = None
    db.commit()


@cv_router.delete("/{language}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cv(
    language: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    row = (
        db.query(UserCv)
        .filter(UserCv.user_id == current_user.id, UserCv.language == language)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sin CV en ese idioma")
    db.delete(row)
    db.commit()
