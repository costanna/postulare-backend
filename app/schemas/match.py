import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import MatchStatus, PreferredLanguage
from app.schemas.application import ApplicationRead
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
    cover_letter_language: str | None = None
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
    language: PreferredLanguage | None = None
    # Sin esto, si ya hay una carta guardada se devuelve tal cual (sin gastar IA)
    regenerate: bool = False


class CoverLetterRead(BaseModel):
    cover_letter: str
    source: str  # "ai" | "template"
    language: str | None = None
    generated_at: datetime
    # Por qu� se us� la plantilla en vez de la IA: no_key | demo | user_limit | global_limit | ai_error
    template_reason: str | None = None
    # ¿Se puede usar la IA ahora mismo? (hay clave configurada y la cuenta no es demo)
    ai_available: bool = False
    # Cartas con IA que le quedan hoy a este usuario (None = sin tope o IA no disponible)
    ai_remaining: int | None = None


class ConvertRequest(BaseModel):
    # True = ya has aplicado a la oferta: la candidatura nace como "enviada" en vez de "guardada"
    applied: bool = False
    # Fecha local de la usuaria; si no llega, se usa la de hoy (UTC)
    applied_at: date | None = None


class ApplyPackRead(BaseModel):
    cover_letter: str
    cover_letter_source: str = "template"
    language: str | None = None
    # Idioma detectado en la oferta (None = no se detectó, se usó el preferido)
    detected_language: str | None = None
    # Email de contacto extraído de la oferta (None = la oferta no lo trae)
    contact_email: str | None = None
    # "saved" = tu CV guardado en ese idioma; "generated" = generado del perfil
    cv_source: str = "generated"
    cv_markdown: str
    email_subject: str
    email_body: str
    mailto_link: str
    offer_url: str | None = None
    checklist: list[str] = []


class AutoApplyRead(BaseModel):
    application: ApplicationRead
    pack: ApplyPackRead
    # Aviso honesto: Postulare deja todo listo, pero el clic final en el
    # portal es manual (ninguna API gratuita permite aplicar por ti).
    needs_manual_step: bool = True


class BulkAutoApplyRequest(BaseModel):
    min_score: int = 60
    limit: int = 5


class BulkAutoApplyRead(BaseModel):
    converted: list[AutoApplyRead]
    skipped: int = 0


class SendEmailRead(BaseModel):
    application: ApplicationRead
    sent_to: str
    subject: str
    language: str | None = None
    detected_language: str | None = None
    cv_source: str = "generated"
