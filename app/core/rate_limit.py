"""Límite de peticiones por IP para endpoints públicos (registro, login...).

Ventana deslizante en memoria: sin dependencias ni infraestructura extra. Con
un único proceso (el plan gratuito de Render) es exacto; con varios procesos
cada uno cuenta por su lado, lo cual sigue frenando el abuso.

Es una defensa de primera línea, NO la garantía: la IP viene de
X-Forwarded-For, que un atacante decidido puede falsear para rotar de IP. Lo
que de verdad acota el daño es el tope diario global de llamadas a Adzuna
(ADZUNA_DAILY_LIMIT) y las cuotas de los planes gratuitos.
"""
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.core.config import settings

_hits: dict[str, deque[float]] = defaultdict(deque)


def reset_rate_limits() -> None:
    _hits.clear()


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


_MAX_TRACKED_KEYS = 5000


def _drop_expired(now: float, window_seconds: int) -> None:
    for key in [k for k, hits in _hits.items() if not hits or now - hits[-1] > window_seconds]:
        del _hits[key]


def _check(bucket: str, ip: str, limit: int, window_seconds: int) -> None:
    if not settings.RATE_LIMIT_ENABLED or limit <= 0:
        return

    now = time.monotonic()
    if len(_hits) > _MAX_TRACKED_KEYS:
        _drop_expired(now, 3600)
    hits = _hits[f"{bucket}:{ip}"]
    while hits and now - hits[0] > window_seconds:
        hits.popleft()

    if len(hits) >= limit:
        retry_after = max(1, int(window_seconds - (now - hits[0])))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiadas peticiones. Inténtalo de nuevo más tarde.",
            headers={"Retry-After": str(retry_after)},
        )
    hits.append(now)


def limit_register(request: Request) -> None:
    _check("register", client_ip(request), settings.REGISTER_LIMIT_PER_HOUR, 3600)


def limit_login(request: Request) -> None:
    _check("login", client_ip(request), settings.LOGIN_LIMIT_PER_MINUTE, 60)


def limit_forgot_password(request: Request) -> None:
    _check("forgot", client_ip(request), settings.FORGOT_PASSWORD_LIMIT_PER_HOUR, 3600)


def limit_demo(request: Request) -> None:
    _check("demo", client_ip(request), settings.DEMO_LIMIT_PER_HOUR, 3600)


def limit_cv_import(request: Request) -> None:
    _check("cv-import", client_ip(request), settings.CV_IMPORT_LIMIT_PER_HOUR, 3600)
