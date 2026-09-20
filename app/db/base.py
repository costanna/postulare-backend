"""Importa todos los modelos para que Alembic (autogenerate) y create_all los conozcan."""
from app.db.base_class import Base  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.application import Application  # noqa: F401
from app.models.event import Event  # noqa: F401
from app.models.job_offer import JobOffer  # noqa: F401
from app.models.match import Match  # noqa: F401
from app.models.adzuna_usage import AdzunaUsage  # noqa: F401
from app.models.llm_usage import LlmUsage  # noqa: F401
