import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.deps import get_current_user
from app.models.application import Application
from app.models.enums import ApplicationStatus, MatchStatus
from app.models.job_offer import JobOffer
from app.models.match import Match
from app.models.user import User
from app.schemas.application import ApplicationRead
from app.schemas.match import MatchRead, MatchSearchResult
from app.services.job_search import JobSearchError, search_job_offers
from app.services.scoring import score_job_offer

router = APIRouter(prefix="/matches", tags=["matches"])


def _build_search_query(user: User) -> str:
    parts: list[str] = []
    if user.desired_position:
        parts.append(user.desired_position)
    if user.skills:
        parts.extend(user.skills[:5])
    query = " ".join(parts).strip()
    if not query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Completa tu perfil (puesto deseado o skills) antes de buscar ofertas",
        )
    return query


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
    _check_rate_limit(current_user)
    query = _build_search_query(current_user)

    try:
        offers = search_job_offers(query=query, location=current_user.location)
    except JobSearchError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    current_user.last_match_search_at = datetime.now(timezone.utc)
    db.add(current_user)

    new_matches = 0
    updated_matches = 0

    for offer_data in offers:
        job_offer = (
            db.query(JobOffer)
            .filter(JobOffer.source == offer_data["source"], JobOffer.external_id == offer_data["external_id"])
            .first()
        )
        if job_offer is None:
            job_offer = JobOffer(**offer_data)
            db.add(job_offer)
            db.flush()  # asigna job_offer.id antes de referenciarlo en el match

        score, reasoning = score_job_offer(current_user, offer_data)

        match = (
            db.query(Match)
            .filter(Match.user_id == current_user.id, Match.job_offer_id == job_offer.id)
            .first()
        )
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
    return MatchSearchResult(fetched=len(offers), new_matches=new_matches, updated_matches=updated_matches)


@router.get("", response_model=list[MatchRead])
def list_matches(
    status_filter: MatchStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Match]:
    query = db.query(Match).filter(Match.user_id == current_user.id)
    if status_filter is not None:
        query = query.filter(Match.status == status_filter)
    return query.order_by(Match.score.desc(), Match.created_at.desc()).limit(limit).all()


def _get_owned_match(match_id: uuid.UUID, db: Session, current_user: User) -> Match:
    match = db.query(Match).filter(Match.id == match_id, Match.user_id == current_user.id).first()
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match no encontrado")
    return match


@router.post("/{match_id}/convert", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
def convert_match(
    match_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Application:
    match = _get_owned_match(match_id, db, current_user)
    offer = match.job_offer

    application = Application(
        user_id=current_user.id,
        company_name=offer.company_name or "Empresa desconocida",
        position=offer.title,
        status=ApplicationStatus.saved,
        source=offer.source,
        salary_range=offer.salary_range,
        job_url=offer.url,
        notes=offer.description,
    )
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
) -> Match:
    match = _get_owned_match(match_id, db, current_user)
    match.status = MatchStatus.dismissed
    db.add(match)
    db.commit()
    db.refresh(match)
    return match
