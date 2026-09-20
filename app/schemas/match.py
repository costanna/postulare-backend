import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import MatchStatus, PreferredLanguage
from app.schemas.job_offer import JobOfferRead


class MatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    score: int
    reasoning: str | None = None
    status: MatchStatus
    created_at: datetime
    job_offer: JobOfferRead
    cover_letter: str | None = None
    cover_letter_source: str | None = None
    cover_letter_at: datetime | None = None
    # Ya tienes una candidatura con esta misma oferta (misma URL o empresa + puesto)
    already_tracked: bool = False


class MatchSearchResult(BaseModel):
    fetched: int
    new_matches: int
    updated_matches: int
    # Ofertas descartadas por repetidas (reanuncios) o por estar ya en tus candidaturas
    skipped_duplicates: int = 0


class CoverLetterRequest(BaseModel):
    # Idioma de la carta; por defecto el idioma preferido del perfil
    language: PreferredLanguage | None = None
    # Sin esto, si ya hay una carta guardada se devuelve tal cual (sin gastar IA)
    regenerate: bool = False


class CoverLetterRead(BaseModel):
    cover_letter: str
    source: str  # "ai" | "template"
    generated_at: datetime
    # Por qu� se us� la plantilla en vez de la IA: no_key | demo | user_limit | global_limit | ai_error
    template_reason: str | None = None
    # ¿Se puede usar la IA ahora mismo? (hay clave configurada y la cuenta no es demo)
    ai_available: bool = False
    # Cartas con IA que le quedan hoy a este usuario (None = sin tope o IA no disponible)
    ai_remaining: int | None = None
