"""Kit de envío gratuito: lo que SÍ se puede automatizar sin pagar ni romper TOS.

Ninguna API gratuita de ofertas permite pulsar "aplicar" en el portal ajeno
(Adzuna/EURES/Remotive/RemoteOK/Arbeitnow solo devuelven la URL; InfoJobs ha
cerrado el registro de apps nuevas). Este kit automatiza todo lo demás con
los datos que ya hay en Postulare, en el idioma de la oferta:

1. Carta plantilla (gratis, sin IA) en el idioma detectado en la oferta.
2. Resumen del CV con las etiquetas en ese idioma (el contenido del usuario
   no se traduce: solo las etiquetas que pone Postulare).
3. Asunto + cuerpo de email + enlace mailto en ese idioma.
4. Checklist de pasos en ese idioma para completar la postulación.

El envío en sí lo hace el usuario con su propio email (botón mailto o
copiar/pegar): el backend no tiene credenciales de correo de nadie.
"""
from urllib.parse import quote

from app.models.user import User
from app.services.cover_letter import Candidate, Offer, build_template_letter
from app.services.cv_document import CvData, render_cv_markdown
from app.services.lang_detect import detect_language

SUPPORTED_PACK_LANGUAGES = ("es", "ca", "en")

_EMAIL = {
    "es": {"subject_word": "Candidatura", "fallback_title": "Candidatura", "offer": "Oferta"},
    "ca": {"subject_word": "Candidatura", "fallback_title": "Candidatura", "offer": "Oferta"},
    "en": {"subject_word": "Application", "fallback_title": "Application", "offer": "Job posting"},
}

_CHECKLIST = {
    "es": [
        "Abre la oferta y revisa requisitos y ubicación antes de enviar nada.",
        "Pega la carta generada y el resumen del CV en el formulario del portal.",
        "O envíalo por email con el botón de abajo (lleva asunto y cuerpo listos).",
        "Marca la candidatura como «aplicada» en Postulare al terminar.",
        "Esta oferta no trae URL: busca la empresa y aplica desde su web.",
    ],
    "ca": [
        "Obre l'oferta i revisa requisits i ubicació abans d'enviar res.",
        "Enganxa la carta generada i el resum del CV al formulari del portal.",
        "O envia-ho per email amb el botó de sota (ja porta assumpte i cos llestos).",
        "Marca la candidatura com a «aplicada» a Postulare en acabar.",
        "Aquesta oferta no porta URL: cerca l'empresa i aplica des de la seva web.",
    ],
    "en": [
        "Open the posting and check requirements and location before sending anything.",
        "Paste the generated letter and CV summary into the portal form.",
        "Or send it by email with the button below (subject and body ready).",
        "Mark the application as “applied” in Postulare when done.",
        "This offer has no URL: find the company and apply from their site.",
    ],
}


def _lang(language: str) -> str:
    return language if language in SUPPORTED_PACK_LANGUAGES else "es"


def resolve_pack_language(user: User, offer: dict) -> tuple[str, str | None]:
    """Idioma del kit: el detectado en la oferta o el preferido del usuario.

    Devuelve (idioma_usado, idioma_detectado_or_None)."""
    detected = detect_language(offer.get("title"), offer.get("description"))
    if detected:
        return detected, detected
    fallback = user.preferred_language.value
    return _lang(fallback), None


def build_email_subject(position: str | None, full_name: str | None, language: str = "es") -> str:
    t = _EMAIL[_lang(language)]
    position = (position or "").strip() or t["fallback_title"]
    if full_name and full_name.strip():
        return f"{t['subject_word']}: {position} — {full_name.strip()}"
    return f"{t['subject_word']}: {position}"


def build_email_body(
    cover_letter: str, cv_markdown: str, offer_url: str | None, language: str = "es"
) -> str:
    t = _EMAIL[_lang(language)]
    parts = [cover_letter.strip(), "---", cv_markdown.strip()]
    if offer_url:
        parts.append(f"{t['offer']}: {offer_url}")
    return "\n\n".join(parts)


def build_mailto_link(subject: str, body: str) -> str:
    return f"mailto:?subject={quote(subject)}&body={quote(body[:1500])}"


def build_checklist(offer_url: str | None, language: str = "es") -> list[str]:
    steps = _CHECKLIST[_lang(language)]
    tail = steps[3] if offer_url else steps[4]
    return [steps[0], steps[1], steps[2], tail]


def build_apply_pack(user: User, offer: dict, cover_letter: str, language: str) -> dict:
    language = _lang(language)
    detected = detect_language(offer.get("title"), offer.get("description"))
    cv = CvData(
        full_name=user.full_name,
        desired_position=user.desired_position,
        location=user.location,
        seniority=user.seniority.value if user.seniority else None,
        skills=list(user.skills or []),
        about=user.about,
        email=user.email,
    )
    cv_markdown = render_cv_markdown(cv, language)
    subject = build_email_subject(offer.get("title"), user.full_name, language)
    body = build_email_body(cover_letter, cv_markdown, offer.get("url"), language)
    return {
        "cover_letter": cover_letter,
        "cover_letter_source": "template",
        "language": language,
        "detected_language": detected,
        "cv_markdown": cv_markdown,
        "email_subject": subject,
        "email_body": body,
        "mailto_link": build_mailto_link(subject, body),
        "offer_url": offer.get("url"),
        "checklist": build_checklist(offer.get("url"), language),
    }


def ensure_template_letter(user: User, offer: dict, language: str) -> str:
    candidate = Candidate(
        full_name=user.full_name,
        position=user.desired_position,
        seniority=user.seniority.value if user.seniority else None,
        location=user.location,
        skills=list(user.skills or []),
        about=user.about,
    )
    offer_data = Offer(
        title=offer.get("title") or "",
        company=offer.get("company_name"),
        location=offer.get("location"),
        description=offer.get("description"),
    )
    return build_template_letter(candidate, offer_data, _lang(language))
