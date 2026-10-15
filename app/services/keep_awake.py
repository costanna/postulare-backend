"""Keep-awake estilo woke-dyno para el plan gratuito de Render.

Render duerme el servicio tras ~15 min sin peticiones ENTRANTES. Un hilo
interno pide la URL pública del backend cada N minutos: la petición sale del
contenedor y vuelve a entrar por el balanceador, así que cuenta como
tráfico y el servicio no se duerme (adiós a los ~30 s de cold start).

Apagado por defecto: solo arranca si KEEP_AWAKE_ENABLED=true y hay
KEEP_AWAKE_URL (la URL pública, nunca localhost). Sin claves ni servicios
extra y sin dependencias nuevas (stdlib).

Ojo al consumo: despierto 24/7 gasta ~720 h/mes de las 750 h gratuitas.
Vale para un solo servicio; con más servicios en Render, replantearlo.
"""
import logging
import threading
import time
import urllib.request

from app.core.config import settings

logger = logging.getLogger("postulare.keep_awake")

_TIMEOUT_SECONDS = 10

_started = False
_lock = threading.Lock()


def keep_awake_configured() -> bool:
    url = (settings.KEEP_AWAKE_URL or "").strip()
    return bool(settings.KEEP_AWAKE_ENABLED) and url.startswith(("http://", "https://"))


def ping_once(url: str, timeout: int = _TIMEOUT_SECONDS) -> bool:
    """Una petición GET a la URL pública. True si responde 2xx."""
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "PostulareKeepAwake/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except Exception as exc:  # sin red, DNS caído, Render redesplegando...: se reintenta al siguiente ciclo
        logger.debug("Keep-awake ping fallido (%s): %s", url, exc)
        return False


def _run(
    url: str,
    interval_seconds: float,
    ping=ping_once,
    sleep=time.sleep,
    stop: threading.Event | None = None,
) -> None:
    while True:
        ping(url)
        if stop is not None and stop.is_set():
            break
        sleep(interval_seconds)


def start_keep_awake(
    url: str | None = None,
    minutes: int | None = None,
    ping=ping_once,
    sleep=time.sleep,
    stop: threading.Event | None = None,
) -> threading.Thread | None:
    """Arranca el hilo (daemon, uno solo por proceso). Devuelve el hilo o None si ya estaba."""
    global _started
    target_url = (url if url is not None else settings.KEEP_AWAKE_URL or "").strip()
    interval_minutes = minutes if minutes is not None else settings.KEEP_AWAKE_MINUTES
    if not target_url.startswith(("http://", "https://")) or interval_minutes <= 0:
        logger.warning("Keep-awake no arranca: URL o intervalo inválidos")
        return None
    with _lock:
        if _started:
            return None
        _started = True
    thread = threading.Thread(
        target=_run,
        args=(target_url, interval_minutes * 60),
        kwargs={"ping": ping, "sleep": sleep, "stop": stop},
        name="postulare-keep-awake",
        daemon=True,
    )
    thread.start()
    logger.info("Keep-awake arrancado: %s cada %s min", target_url, interval_minutes)
    return thread


def reset_keep_awake_state() -> None:
    """Solo para tests: permite rearrancar el hilo entre casos."""
    global _started
    with _lock:
        _started = False


def maybe_start_keep_awake() -> threading.Thread | None:
    """Lo que llama el startup de FastAPI: arranca solo si está configurado."""
    if not keep_awake_configured():
        return None
    return start_keep_awake()
