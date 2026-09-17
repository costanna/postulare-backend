from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas.stats import SourceCount, StatsSummary, StatusCount, TimelinePoint
from app.services import stats as stats_service

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/summary", response_model=StatsSummary)
def summary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return stats_service.get_summary(db, current_user.id)


@router.get("/by-status", response_model=list[StatusCount])
def by_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    return stats_service.get_by_status(db, current_user.id)


@router.get("/timeline", response_model=list[TimelinePoint])
def timeline(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    return stats_service.get_timeline(db, current_user.id)


@router.get("/by-source", response_model=list[SourceCount])
def by_source(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[dict]:
    return stats_service.get_by_source(db, current_user.id)
