"""Configuración de la aplicación, cargada desde variables de entorno (.env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    PROJECT_NAME: str = "Postulare API"
    API_V1_PREFIX: str = ""

    # Base de datos
    DATABASE_URL: str = "postgresql+psycopg2://postulare:postulare@localhost:5432/postulare"

    # JWT
    SECRET_KEY: str = "change-me-to-a-long-random-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    RESET_PASSWORD_TOKEN_EXPIRE_MINUTES: int = 30

    # CORS
    CORS_ORIGINS: str = "http://localhost:4200"

    # Adzuna
    ADZUNA_APP_ID: str = ""
    ADZUNA_APP_KEY: str = ""
    ADZUNA_COUNTRY: str = "es"

    # IA (opcional): cartas de presentación con Claude. Sin clave, o al agotar los
    # topes, se usa una plantilla sin IA (gratis) - la función nunca deja de responder.
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-opus-5"
    # Topes de gasto: llamadas reales a la IA por día, todos los usuarios juntos y por usuario.
    LLM_DAILY_LIMIT: int = 20
    COVER_LETTER_DAILY_LIMIT_PER_USER: int = 5

    # Cuentas demo temporales ("Prueba la demo")
    DEMO_ENABLED: bool = True
    DEMO_TTL_HOURS: int = 24
    DEMO_ACCOUNTS_DAILY_LIMIT: int = 200
    DEMO_LIMIT_PER_HOUR: int = 5

    # Recordatorios: días sin novedades tras aplicar a partir de los cuales toca hacer seguimiento
    FOLLOW_UP_DAYS: int = 7

    # Importar CV (PDF): solo se lee en memoria, nunca se guarda
    CV_MAX_BYTES: int = 2_000_000
    CV_MAX_PAGES: int = 6
    CV_IMPORT_LIMIT_PER_HOUR: int = 15

    # Rate limiting
    MATCH_SEARCH_COOLDOWN_MINUTES: int = 10
    # Tope GLOBAL de llamadas reales a Adzuna por día (todos los usuarios
    # juntos): red de seguridad para que una demo pública no agote la cuota
    # gratuita. 0 = sin límite. Las respuestas servidas desde la caché no cuentan.
    ADZUNA_DAILY_LIMIT: int = 50
    # Minutos que se reutiliza una búsqueda idéntica sin volver a llamar a Adzuna. 0 = sin caché.
    ADZUNA_CACHE_MINUTES: int = 360
    # Límites por IP en endpoints públicos (registro, login, recuperar contraseña).
    RATE_LIMIT_ENABLED: bool = True
    REGISTER_LIMIT_PER_HOUR: int = 10
    LOGIN_LIMIT_PER_MINUTE: int = 20
    FORGOT_PASSWORD_LIMIT_PER_HOUR: int = 5

    # Email
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "no-reply@postulare.app"

    FRONTEND_URL: str = "http://localhost:4200"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
