from pydantic import BaseModel, Field, field_validator


class SearchFilters(BaseModel):
    """Filtros de "Buscar ofertas" que el usuario puede editar.

    Todo es opcional: sin tocar nada, la búsqueda se construye sola a partir
    del perfil (puesto deseado + skills, ubicación, seniority).
    """

    # Sustituye a la consulta automática (puesto + skills). Basta con que
    # aparezca ALGUNA de las palabras en la oferta.
    keywords: str | None = Field(default=None, max_length=200)
    # Sustituye a la ubicación del perfil solo para buscar.
    location: str | None = Field(default=None, max_length=100)
    radius_km: int = Field(default=30, ge=1, le=200)
    # Palabras que descartan una oferta (p. ej. "php sap comercial"). Separadas por espacios o comas.
    exclude: str | None = Field(default=None, max_length=200)
    # Descarta automáticamente los otros niveles (perfil junior -> quita "senior", "lead"...).
    exclude_other_levels: bool = True
    # Solo ofertas publicadas en los últimos N días. None = sin límite.
    max_days_old: int | None = Field(default=None, ge=1, le=365)
    # Oculta en el listado las ofertas con puntuación menor. Solo afecta a la vista.
    min_score: int = Field(default=0, ge=0, le=100)

    @field_validator("keywords", "location", "exclude", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            value = " ".join(value.split())  # colapsa espacios/saltos de línea
            return value or None
        return value


class SearchFiltersRead(BaseModel):
    filters: SearchFilters
    # Lo que se enviará de verdad a Adzuna con estos filtros (para que el
    # usuario vea el efecto de lo que toca sin tener que lanzar una búsqueda).
    effective_query: str
    effective_location: str | None
    # Búsquedas reales que quedan hoy en el tope global; None = sin tope.
    daily_remaining: int | None
