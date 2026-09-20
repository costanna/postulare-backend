import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.deps import get_current_user
from app.models.adzuna_usage import AdzunaUsage
from app.models.application import Application
from app.models.enums import ApplicationStatus, MatchStatus
from app.models.job_offer import JobOffer
from app.models.match import Match
from app.models.user import User
from app.schemas.application import ApplicationRead
from app.schemas.match import ConvertRequest, CoverLetterRead, CoverLetterRequest, MatchRead, MatchSearchResult
from app.schemas.search_filters import SearchFilters, SearchFiltersRead
from app.services import llm_quota
from app.services.application_status import stamp_applied_date
from app.services.cover_letter import Candidate, Offer, build_template_letter, generate_ai_letter
from app.services.duplicates import TrackedIndex, offer_key
from app.services.job_search import JobSearchError, build_search_query, search_job_offers
from app.services.scoring import score_job_offer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/matches", tags=["matches"])


def _to_read(match: Match, tracked: TrackedIndex) -> MatchRead:
    read = MatchRead.model_validate(match)
    offer = match.job_offer
    read.already_tracked = tracked.contains(offer.company_name, offer.title, offer.url)
    return read


def _load_filters(user: User) -> SearchFilters:
    try:
        return SearchFilters(**(user.search_filters or {}))
    except ValidationError:
        # JSON guardado que ya no valida (p. ej. cambió el esquema): vuelve al automático.
        return SearchFilters()


def _effective_query(user: User, filters: SearchFilters) -> str:
    return filters.keywords or build_search_query(user.desired_position, user.skills)


def _effective_location(user: User, filters: SearchFilters) -> str | None:
    return filters.location or user.location


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _daily_remaining(db: Session) -> int | None:
    limit = settings.ADZUNA_DAILY_LIMIT
    if limit <= 0:
        return None
    used = db.query(AdzunaUsage.calls).filter(AdzunaUsage.day == _today()).scalar() or 0
    return max(0, limit - used)


def _consume_daily_quota(db: Session) -> None:
    """Cuenta una llamada REAL a Adzuna contra el tope diario global.

    Se ejecuta solo cuando no hay respuesta en caché. Si el tope ya está
    alcanzado aborta la búsqueda con 503 (no 429: no es culpa de este
    usuario, es la cuota compartida de la demo).
    """
    limit = settings.ADZUNA_DAILY_LIMIT
    if limit <= 0:
        return

    today = _today()

    def _row() -> AdzunaUsage | None:
        return db.query(AdzunaUsage).filter(AdzunaUsage.day == today).with_for_update().first()

    row = _row()
    if row is None:
        db.add(AdzunaUsage(day=today, calls=0))
        try:
            db.flush()
        except IntegrityError:  # otra petición creó la fila a la vez
            db.rollback()
        row = _row()

    if row.calls >= limit:
        tomorrow = datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        retry_after = max(1, int((tomorrow - datetime.now(timezone.utc)).total_seconds()))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Se ha alcanzado el límite diario de búsquedas de esta demo. Vuelve mañana.",
            headers={"Retry-After": str(retry_after)},
        )

    row.calls += 1
    db.commit()


def _filters_read(user: User, filters: SearchFilters, db: Session) -> SearchFiltersRead:
    return SearchFiltersRead(
        filters=filters,
        effective_query=_effective_query(user, filters),
        effective_location=_effective_location(user, filters),
        daily_remaining=_daily_remaining(db),
    )


@router.get("/filters", response_model=SearchFiltersRead)
def get_search_filters(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SearchFiltersRead:
    return _filters_read(current_user, _load_filters(current_user), db)


@router.put("/filters", response_model=SearchFiltersRead)
def save_search_filters(
    payload: SearchFilters,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SearchFiltersRead:
    current_user.search_filters = payload.model_dump()
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return _filters_read(current_user, payload, db)


def _check_rate_limit(user: User) -> None:
    if user.last_match_search_at is None:
        return
    cooldown = timedelta(minutes=settings.MATCH_SEARCH_COOLDOWN_MINUTES)
    last = user.last_match_search_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    elapsed = datetime.now(timezone.utc) - last
    if elapsed < cooldown:
        wait_seconds = int((cooldown - elapsed).total_seconds())
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Espera {wait_seconds} segundos antes de volver a buscar ofertas",
        )


@router.post("/search", response_model=MatchSearchResult)
def search_matches(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MatchSearchResult:
    if current_user.is_demo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta demo no puede buscar ofertas reales. Crea una cuenta para usar la búsqueda.",
        )
    _check_rate_limit(current_user)

    filters = _load_filters(current_user)
    query = _effective_query(current_user, filters)
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Completa tu perfil (puesto deseado o skills) antes de buscar ofertas",
        )

    try:
        offers = search_job_offers(
            query=query,
            location=_effective_location(current_user, filters),
            seniority=current_user.seniority,
            radius_km=filters.radius_km,
            exclude=filters.exclude,
            exclude_other_levels=filters.exclude_other_levels,
            max_days_old=filters.max_days_old,
            before_request=lambda: _consume_daily_quota(db),
        )
    except JobSearchError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    current_user.last_match_search_at = datetime.now(timezone.utc)
    db.add(current_user)

    new_matches = 0
    updated_matches = 0
    skipped_duplicates = 0

    tracked = TrackedIndex.for_user(db, current_user.id)
    # Ofertas que el usuario ya tiene como match (cualquier estado), por clave empresa+título+ciudad
    known_keys = {
        offer_key(company, title, location)
        for company, title, location in db.query(JobOffer.company_name, JobOffer.title, JobOffer.location)
        .join(Match, Match.job_offer_id == JobOffer.id)
        .filter(Match.user_id == current_user.id)
    }
    seen_keys: set[str] = set()

    for offer_data in offers:
        key = offer_key(offer_data.get("company_name"), offer_data.get("title"), offer_data.get("location"))
        if key in seen_keys:  # la misma oferta repetida en esta misma búsqueda
            skipped_duplicates += 1
            continue
        seen_keys.add(key)

        job_offer = (
            db.query(JobOffer)
            .filter(JobOffer.source == offer_data["source"], JobOffer.external_id == offer_data["external_id"])
            .first()
        )
        match = None
        if job_offer is not None:
            match = (
                db.query(Match)
                .filter(Match.user_id == current_user.id, Match.job_offer_id == job_offer.id)
                .first()
            )

        if match is None and (
            key in known_keys  # reanuncio de una oferta que ya tienes (con otro id)
            or tracked.contains(offer_data.get("company_name"), offer_data.get("title"), offer_data.get("url"))
        ):
            skipped_duplicates += 1
            continue

        if job_offer is None:
            job_offer = JobOffer(**offer_data)
            db.add(job_offer)
            db.flush()  # asigna job_offer.id antes de referenciarlo en el match

        score, reasoning = score_job_offer(current_user, offer_data)

        if match is None:
            match = Match(user_id=current_user.id, job_offer_id=job_offer.id, score=score, reasoning=reasoning)
            db.add(match)
            new_matches += 1
        elif match.status == MatchStatus.new:
            # Solo refrescamos el score de matches que el usuario aun no ha gestionado.
            match.score = score
            match.reasoning = reasoning
            db.add(match)
            updated_matches += 1

    db.commit()
    return MatchSearchResult(
        fetched=len(offers),
        new_matches=new_matches,
        updated_matches=updated_matches,
        skipped_duplicates=skipped_duplicates,
    )


@router.get("", response_model=list[MatchRead])
def list_matches(
    status_filter: MatchStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MatchRead]:
    query = db.query(Match).filter(Match.user_id == current_user.id)
    if status_filter is not None:
        query = query.filter(Match.status == status_filter)
    matches = query.order_by(Match.score.desc(), Match.created_at.desc()).limit(limit).all()
    tracked = TrackedIndex.for_user(db, current_user.id)
    return [_to_read(match, tracked) for match in matches]


def _get_owned_match(match_id: uuid.UUID, db: Session, current_user: User) -> Match:
    match = db.query(Match).filter(Match.id == match_id, Match.user_id == current_user.id).first()
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match no encontrado")
    return match


@router.post("/{match_id}/convert", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
def convert_match(
    match_id: uuid.UUID,
    payload: ConvertRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Application:
    payload = payload or ConvertRequest()
    match = _get_owned_match(match_id, db, current_user)
    if match.status == MatchStatus.converted:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta oferta ya es una candidatura")
    offer = match.job_offer

    application = Application(
        user_id=current_user.id,
        company_name=offer.company_name or "Empresa desconocida",
        position=offer.title,
        status=ApplicationStatus.applied if payload.applied else ApplicationStatus.saved,
        source=offer.source,
        salary_range=offer.salary_range,
        job_url=offer.url,
        notes=offer.description,
    )
    stamp_applied_date(application, payload.applied_at)
    db.add(application)

    match.status = MatchStatus.converted
    db.add(match)

    db.commit()
    db.refresh(application)
    return application


@router.post("/{match_id}/dismiss", response_model=MatchRead)
def dismiss_match(
    match_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MatchRead:
    match = _get_owned_match(match_id, db, current_user)
    match.status = MatchStatus.dismissed
    db.add(match)
    db.commit()
    db.refresh(match)
    return _to_read(match, TrackedIndex.for_user(db, current_user.id))


def _ai_state(db: Session, user: User) -> tuple[bool, int | None]:
    """(¿se puede usar la IA ahora?, cartas con IA que le quedan hoy)."""
    if user.is_demo or not settings.ANTHROPIC_API_KEY:
        return False, None
    remaining = [
        llm_quota.remaining(db, llm_quota.user_scope(user.id), settings.COVER_LETTER_DAILY_LIMIT_PER_USER),
        llm_quota.remaining(db, llm_quota.GLOBAL_SCOPE, settings.LLM_DAILY_LIMIT),
    ]
    limits = [value for value in remaining if value is not None]
    return True, (min(limits) if limits else None)


def _letter_read(match: Match, user: User, db: Session, template_reason: str | None = None) -> CoverLetterRead:
    ai_available, ai_remaining = _ai_state(db, user)
    return CoverLetterRead(
        cover_letter=match.cover_letter or "",
        source=match.cover_letter_source or "template",
        generated_at=match.cover_letter_at or datetime.now(timezone.utc),
        template_reason=template_reason,
        ai_available=ai_available,
        ai_remaining=ai_remaining,
    )


@router.post("/{match_id}/cover-letter", response_model=CoverLetterRead)
def generate_cover_letter(
    match_id: uuid.UUID,
    payload: CoverLetterRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CoverLetterRead:
    """Carta de presentación para esta oferta. Siempre devuelve una: con IA (Claude) si
    hay clave y quedan cartas del día, y con una plantilla gratuita en cualquier otro caso."""
    payload = payload or CoverLetterRequest()
    match = _get_owned_match(match_id, db, current_user)

    if match.cover_letter and not payload.regenerate:
        return _letter_read(match, current_user, db)

    language = (payload.language or current_user.preferred_language).value
    offer = match.job_offer
    candidate = Candidate(
        full_name=current_user.full_name,
        position=current_user.desired_position,
        seniority=current_user.seniority.value if current_user.seniority else None,
        location=current_user.location,
        skills=list(current_user.skills or []),
        about=current_user.about,
    )
    offer_data = Offer(
        title=offer.title,
        company=offer.company_name,
        location=offer.location,
        description=offer.description,
    )

    letter: str | None = None
    source = "template"
    reason: str | None = None

    if current_user.is_demo:
        reason = "demo"
    elif not settings.ANTHROPIC_API_KEY:
        reason = "no_key"
    else:
        user_scope = llm_quota.user_scope(current_user.id)
        if not llm_quota.try_consume(db, user_scope, settings.COVER_LETTER_DAILY_LIMIT_PER_USER):
            reason = "user_limit"
        elif not llm_quota.try_consume(db, llm_quota.GLOBAL_SCOPE, settings.LLM_DAILY_LIMIT):
            llm_quota.release(db, user_scope)
            reason = "global_limit"
        else:
            try:
                letter = generate_ai_letter(candidate, offer_data, language)
                source = "ai"
            except Exception:  # cualquier fallo de la IA: devolvemos la plantilla, no un 500
                logger.exception("Fallo al generar la carta con IA; se usa la plantilla")
                # No se llegó a gastar nada útil: se devuelve la reserva de los dos topes
                llm_quota.release(db, user_scope)
                llm_quota.release(db, llm_quota.GLOBAL_SCOPE)
                reason = "ai_error"

    if letter is None:
        letter = build_template_letter(candidate, offer_data, language)

    match.cover_letter = letter
    match.cover_letter_source = source
    match.cover_letter_at = datetime.now(timezone.utc)
    db.add(match)
    db.commit()
    db.refresh(match)
    return _letter_read(match, current_user, db, template_reason=reason)
