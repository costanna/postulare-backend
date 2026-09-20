"""Cuentas demo temporales ("Prueba la demo").

Permiten a cualquiera (p. ej. un reclutador que mira el portfolio) probar la
app sin registrarse: se crea un usuario con datos de ejemplo ficticios. Para
que no cueste nada ni se pueda abusar:

- no pueden buscar ofertas reales (no gastan la cuota de Adzuna),
- las cartas se generan con plantilla, nunca con IA (no gastan la de Anthropic),
- caducan a las DEMO_TTL_HOURS y se borran solas,
- hay un límite por IP y un tope global de cuentas demo al día.
"""
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.application import Application
from app.models.enums import ApplicationStatus, EventType, PreferredLanguage, Seniority
from app.models.event import Event
from app.models.job_offer import JobOffer
from app.models.match import Match
from app.models.user import User
from app.services.scoring import score_job_offer

DEMO_SOURCE = "demo"
_PURGE_BATCH = 200

_SKILLS = ["Python", "FastAPI", "Angular", "TypeScript", "PostgreSQL", "Docker", "Git"]

# Ofertas y empresas FICTICIAS (la primera coincide a propósito con una candidatura
# de la demo para enseñar el aviso "ya la tienes en tus candidaturas").
_OFFERS = [
    ("Full Stack Developer", "Nubelia Systems", "Barcelona", "30.000 - 36.000 €",
     "Buscamos desarrollador/a Full Stack junior con Angular, TypeScript y Python (FastAPI). "
     "Trabajarás con PostgreSQL y Docker en un equipo ágil."),
    ("Backend Developer Python", "Ondas Digitales", "Barcelona", None,
     "Incorporamos desarrollador/a backend con Python, FastAPI y PostgreSQL para nuestra plataforma de datos. "
     "Se valora Docker y experiencia con APIs REST. Nivel junior."),
    ("Frontend Developer Angular", "Faro Software", "Remoto", "28.000 - 34.000 €",
     "Desarrollo de aplicaciones web con Angular y TypeScript. Testing con Jest y trabajo con Git en equipo."),
    ("Software Engineer Java Spring", "Argila Tech", "Girona", None,
     "Ingeniero/a de software con Java y Spring Boot, bases de datos SQL y metodologías ágiles."),
    ("Junior QA Automation", "Mistral Apps", "Barcelona", "24.000 - 28.000 €",
     "Automatización de pruebas con Python y Selenium en un entorno con Docker. Perfil junior."),
]

_TEXT = {
    "es": {
        "name": "Ana Demo",
        "about": "Desarrolladora Full Stack junior con experiencia en Python, FastAPI y Angular. "
        "Cuenta de demostración con datos ficticios.",
        "interview": "Entrevista técnica con el equipo de desarrollo",
        "follow_up": "Correo de seguimiento enviado a recursos humanos",
        "offer_note": "Oferta verbal; pendiente de recibir el contrato",
    },
    "ca": {
        "name": "Anna Demo",
        "about": "Desenvolupadora Full Stack júnior amb experiència en Python, FastAPI i Angular. "
        "Compte de demostració amb dades fictícies.",
        "interview": "Entrevista tècnica amb l'equip de desenvolupament",
        "follow_up": "Correu de seguiment enviat a recursos humans",
        "offer_note": "Oferta verbal; pendent de rebre el contracte",
    },
    "en": {
        "name": "Ana Demo",
        "about": "Junior Full Stack developer with experience in Python, FastAPI and Angular. "
        "Demo account with fictional data.",
        "interview": "Technical interview with the development team",
        "follow_up": "Follow-up email sent to HR",
        "offer_note": "Verbal offer; waiting for the contract",
    },
}


class DemoLimitReached(Exception):
    """Se han creado ya demasiadas cuentas demo hoy."""


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def is_demo_expired(user: User) -> bool:
    if not user.is_demo or user.created_at is None:
        return False
    return datetime.now(timezone.utc) - _utc(user.created_at) > timedelta(hours=settings.DEMO_TTL_HOURS)


def purge_expired(db: Session) -> int:
    """Borra las cuentas demo caducadas (con todos sus datos, en cascada)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.DEMO_TTL_HOURS)
    expired = db.query(User).filter(User.is_demo.is_(True), User.created_at < cutoff).limit(_PURGE_BATCH).all()
    for user in expired:
        db.delete(user)
    if expired:
        db.commit()
    return len(expired)


def _created_today(db: Session) -> int:
    start = datetime.combine(datetime.now(timezone.utc).date(), datetime.min.time(), tzinfo=timezone.utc)
    return db.query(User).filter(User.is_demo.is_(True), User.created_at >= start).count()


def _get_or_create_offers(db: Session) -> list[JobOffer]:
    offers: list[JobOffer] = []
    for index, (title, company, location, salary, description) in enumerate(_OFFERS, start=1):
        external_id = f"demo-{index}"
        offer = db.query(JobOffer).filter(JobOffer.source == DEMO_SOURCE, JobOffer.external_id == external_id).first()
        if offer is None:
            offer = JobOffer(
                source=DEMO_SOURCE,
                external_id=external_id,
                title=title,
                company_name=company,
                location=location,
                salary_range=salary,
                description=description,
            )
            db.add(offer)
            db.flush()
        offers.append(offer)
    return offers


def create_demo_user(db: Session, language: PreferredLanguage) -> User:
    purge_expired(db)
    limit = settings.DEMO_ACCOUNTS_DAILY_LIMIT
    if limit > 0 and _created_today(db) >= limit:
        raise DemoLimitReached

    text = _TEXT[language.value]
    user = User(
        email=f"demo-{uuid.uuid4().hex[:12]}@example.com",
        hashed_password=hash_password(secrets.token_urlsafe(24)),  # nadie la conoce: solo se entra por /auth/demo
        full_name=text["name"],
        skills=list(_SKILLS),
        location="Barcelona",
        desired_position="Full Stack Developer",
        seniority=Seniority.junior,
        preferred_language=language,
        about=text["about"],
        is_demo=True,
    )
    db.add(user)
    db.flush()

    today: date = datetime.now(timezone.utc).date()

    def add_application(
        company: str, position: str, status: ApplicationStatus, days_ago: int | None, **extra
    ) -> Application:
        application = Application(
            user_id=user.id,
            company_name=company,
            position=position,
            status=status,
            applied_at=today - timedelta(days=days_ago) if days_ago is not None else None,
            source="demo",
            **extra,
        )
        db.add(application)
        db.flush()
        return application

    def add_event(application: Application, type_: EventType, description: str, days_ago: int) -> None:
        when = datetime.now(timezone.utc) - timedelta(days=days_ago)
        db.add(Event(application_id=application.id, type=type_, description=description, event_date=when))

    # Sin novedades desde hace 12 días -> aparece en "Seguimientos pendientes"
    add_application(
        "Nubelia Systems", "Full Stack Developer", ApplicationStatus.applied, 12, salary_range="30.000 - 36.000 €"
    )
    interview = add_application("Cobalto Labs", "Backend Developer Python", ApplicationStatus.interview, 9)
    add_event(interview, EventType.interview, text["interview"], 3)
    add_application("Aurora Data", "Junior Frontend Developer", ApplicationStatus.applied, 4)
    offer = add_application(
        "Tramuntana Soft", "Software Engineer", ApplicationStatus.offer, 20,
        salary_range="32.000 - 36.000 €", notes=text["offer_note"],
    )
    add_event(offer, EventType.note, text["offer_note"], 2)
    add_application("Pixelforja", "Web Developer", ApplicationStatus.rejected, 25)
    add_application("Llumbrera Studio", "Full Stack Developer", ApplicationStatus.saved, None)
    followed = add_application("Vertex Norte", "Angular Developer", ApplicationStatus.applied, 16)
    add_event(followed, EventType.follow_up, text["follow_up"], 8)

    for job_offer in _get_or_create_offers(db):
        score, reasoning = score_job_offer(
            user, {"title": job_offer.title, "description": job_offer.description, "location": job_offer.location}
        )
        db.add(Match(user_id=user.id, job_offer_id=job_offer.id, score=score, reasoning=reasoning))

    db.commit()
    db.refresh(user)
    return user
