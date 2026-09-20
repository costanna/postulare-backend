import logging

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import limit_demo, limit_forgot_password, limit_login, limit_register
from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_reset_token,
    decode_token,
    hash_password,
    reset_token_matches,
    verify_password,
)
from app.db.session import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas.auth import (
    AccessTokenOnly,
    DemoRequest,
    ForgotPasswordRequest,
    RefreshRequest,
    ResetPasswordRequest,
    TokenPair,
    UserLogin,
    UserRegister,
)
from app.schemas.user import UserRead
from app.services.demo import DemoLimitReached, create_demo_user, is_demo_expired
from app.services.email import send_password_reset_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_register)],
)
def register(payload: UserRegister, db: Session = Depends(get_db)) -> User:
    existing = db.query(User).filter(func.lower(User.email) == payload.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ese email ya está registrado")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenPair, dependencies=[Depends(limit_login)])
def login(payload: UserLogin, db: Session = Depends(get_db)) -> TokenPair:
    user = db.query(User).filter(func.lower(User.email) == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email o contraseña incorrectos")

    return TokenPair(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/demo", response_model=TokenPair, dependencies=[Depends(limit_demo)])
def start_demo(payload: DemoRequest | None = None, db: Session = Depends(get_db)) -> TokenPair:
    """Crea una cuenta temporal con datos de ejemplo y devuelve sus tokens (sin registro)."""
    if not settings.DEMO_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="La demo no está disponible")

    language = (payload or DemoRequest()).language
    try:
        user = create_demo_user(db, language)
    except DemoLimitReached as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Se han creado demasiadas cuentas demo hoy. Inténtalo mañana o crea una cuenta.",
        ) from exc

    return TokenPair(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/refresh", response_model=AccessTokenOnly)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> AccessTokenOnly:
    try:
        user_id = decode_token(payload.refresh_token, expected_type="refresh")
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token inválido o caducado"
        ) from exc

    user = db.get(User, user_id)
    if user is None or is_demo_expired(user):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no encontrado")

    return AccessTokenOnly(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(limit_forgot_password)])
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> dict:
    user = db.query(User).filter(func.lower(User.email) == payload.email).first()
    # Respuesta genérica siempre, exista o no el email, para no filtrar qué
    # correos están registrados.
    if user:
        reset_token = create_reset_token(str(user.id), user.hashed_password)
        try:
            send_password_reset_email(user.email, reset_token)
        except Exception:
            # Un fallo del SMTP no puede distinguirse desde fuera: si no, revelaría qué emails existen
            logger.exception("No se pudo enviar el email de restablecimiento")
    return {"message": "Si el email existe, recibirás instrucciones para restablecer tu contraseña."}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> dict:
    try:
        user_id = decode_token(payload.token, expected_type="reset")
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Enlace de restablecimiento inválido o caducado"
        ) from exc

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuario no encontrado")
    if not reset_token_matches(payload.token, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Enlace de restablecimiento inválido o caducado"
        )

    user.hashed_password = hash_password(payload.new_password)
    db.add(user)
    db.commit()
    return {"message": "Contraseña actualizada correctamente"}
