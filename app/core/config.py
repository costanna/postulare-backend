from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    PROJECT_NAME: str = "Postulare API"
    API_V1_PREFIX: str = ""

    DATABASE_URL: str = "postgresql+psycopg2://postulare:postulare@localhost:5432/postulare"

    SECRET_KEY: str = "change-me-to-a-long-random-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    RESET_PASSWORD_TOKEN_EXPIRE_MINUTES: int = 30

    CORS_ORIGINS: str = "http://localhost:4200"

    ADZUNA_APP_ID: str = ""
    ADZUNA_APP_KEY: str = ""
    ADZUNA_COUNTRY: str = "es"

    INFOJOBS_CLIENT_ID: str = ""
    INFOJOBS_CLIENT_SECRET: str = ""
    INFOJOBS_DAILY_LIMIT: int = 50

    # IA (opcional): cartas de presentación con Claude. Sin clave, o al agotar los
    # topes, se usa una plantilla sin IA (gratis) - la función nunca deja de responder.
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-opus-5"
    LLM_DAILY_LIMIT: int = 20
    COVER_LETTER_DAILY_LIMIT_PER_USER: int = 5

    DEMO_ENABLED: bool = True
    DEMO_TTL_HOURS: int = 24
    DEMO_ACCOUNTS_DAILY_LIMIT: int = 200
    DEMO_LIMIT_PER_HOUR: int = 5

    FOLLOW_UP_DAYS: int = 7

    CV_MAX_BYTES: int = 2_000_000
    CV_MAX_PAGES: int = 6
    CV_IMPORT_LIMIT_PER_HOUR: int = 15

    MATCH_SEARCH_COOLDOWN_MINUTES: int = 10
    # Tope GLOBAL de llamadas reales a Adzuna por día (todos los usuarios
    # juntos): red de seguridad para que una demo pública no agote la cuota
    # gratuita. 0 = sin límite. Las respuestas servidas desde la caché no cuentan.
    ADZUNA_DAILY_LIMIT: int = 50
    ADZUNA_CACHE_MINUTES: int = 360
    RATE_LIMIT_ENABLED: bool = True
    REGISTER_LIMIT_PER_HOUR: int = 10
    LOGIN_LIMIT_PER_MINUTE: int = 20
    FORGOT_PASSWORD_LIMIT_PER_HOUR: int = 5

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
