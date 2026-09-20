from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import limit_cv_import
from app.db.session import get_db
from app.deps import get_current_user
from app.models.enums import Seniority
from app.models.user import User
from app.schemas.user import CvImportResult, ProfileUpdate, UserRead
from app.services.cv_parser import CvParseError, parse_cv_pdf

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=UserRead)
def get_profile(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("", response_model=UserRead)
def update_profile(
    payload: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(current_user, field, value)

    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/import-cv", response_model=CvImportResult, dependencies=[Depends(limit_cv_import)])
def import_cv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> CvImportResult:
    """Lee un CV en PDF y PROPONE los datos del perfil. No guarda nada: ni el
    fichero ni el texto; el usuario revisa la propuesta y la guarda con PATCH /profile."""
    # Se lee un byte de más para distinguir "justo en el límite" de "demasiado grande"
    data = file.file.read(settings.CV_MAX_BYTES + 1)
    if len(data) > settings.CV_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"El PDF pesa demasiado (máximo {settings.CV_MAX_BYTES // 1_000_000} MB)",
        )
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="El fichero no es un PDF")

    try:
        proposal = parse_cv_pdf(data, settings.CV_MAX_PAGES)
    except CvParseError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return CvImportResult(
        full_name=proposal.full_name,
        desired_position=proposal.desired_position,
        location=proposal.location,
        seniority=Seniority(proposal.seniority) if proposal.seniority else None,
        skills=proposal.skills,
        about=proposal.about,
    )
