"""Optimización ATS del email: texto plano + palabras clave reales de la oferta.

Los ATS puntúan por coincidencias exactas con lo publicado (título del puesto,
skills, herramientas). Todo lo añadido son datos reales del usuario: solo sus
skills que la oferta menciona, nunca inventadas. Sin tablas ni formato raro:
el cuerpo ya es texto plano, que es lo que mejor parsean.
"""
import re

from app.services.scoring import _mentions

MAX_KEYWORDS = 12

_LABELS = {
    "es": {"keywords": "Coincidencias clave", "profile": "Perfil", "re": "Re"},
    "ca": {"keywords": "Coincidències clau", "profile": "Perfil", "re": "Re"},
    "en": {"keywords": "Key matches", "profile": "Profile", "re": "Re"},
}


def matched_keywords(
    title: str | None, description: str | None, user_skills: list[str], max_n: int = MAX_KEYWORDS
) -> list[str]:
    """Skills del usuario mencionadas en la oferta, en orden de aparición."""
    text = f"{title or ''} {description or ''}".lower()
    found: list[tuple[int, str]] = []
    seen: set[str] = set()
    for skill in user_skills:
        clean = (skill or "").strip()
        key = clean.lower()
        if not clean or key in seen:
            continue
        if _mentions(key, text):
            match = re.search(rf"(?<![\w+#]){re.escape(key)}(?![\w+#])", text)
            found.append((match.start() if match else 0, clean))
            seen.add(key)
    found.sort(key=lambda item: item[0])
    return [skill for _, skill in found[:max_n]]


def profile_line(
    desired_position: str | None, seniority: str | None, location: str | None
) -> str | None:
    parts = [p.strip() for p in (desired_position, seniority, location) if p and p.strip()]
    return " · ".join(parts) or None


def ats_block(
    user_position: str | None,
    seniority: str | None,
    location: str | None,
    offer_title: str | None,
    company: str | None,
    keywords: list[str],
    language: str,
) -> list[str]:
    """Líneas ATS (Re + keywords + perfil) localizadas. Vacías si no hay datos."""
    t = _LABELS.get(language, _LABELS["es"])
    lines: list[str] = []
    title = (offer_title or "").strip()
    if title:
        ref = f"{t['re']}: {title}"
        if company and company.strip():
            ref += f" — {company.strip()}"
        lines.append(ref)
    if keywords:
        lines.append(f"{t['keywords']}: {', '.join(keywords)}")
    profile = profile_line(user_position, seniority, location)
    if profile:
        lines.append(f"{t['profile']}: {profile}")
    return lines
