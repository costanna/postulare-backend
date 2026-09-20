"""Nivel 1 de scoring: keyword matching, gratis y sin dependencias externas.

Compara el perfil del usuario (skills, ubicación, seniority) con el
título/descripción de una oferta y devuelve un score de 0 a 100 junto con una
explicación en texto. El nivel 2 (scoring razonado con la API de Claude) se
añadirá más adelante como mejora, sin tocar esta función.
"""
import re

from app.models.enums import Seniority
from app.models.user import User

# Puntos máximos que aporta cada bloque; suman como máximo 100.
_MAX_SKILLS_POINTS = 70
_LOCATION_POINTS = 15
_SENIORITY_POINTS = 15

# Nº de skills que se toman como "lo esperable" en una oferta. Un CV real
# lista 20-30 skills y ninguna oferta las menciona todas: si el denominador
# fuera el total, un buen encaje (5 coincidencias) puntuaría ~12 sobre 70.
_SKILLS_TARGET = 5

_SENIORITY_KEYWORDS: dict[Seniority, list[str]] = {
    Seniority.junior: ["junior", "jr.", "jr ", "trainee", "entry level", "entry-level", "becario"],
    Seniority.mid: ["mid level", "mid-level", "semi senior", "semi-senior", "intermedio"],
    Seniority.senior: ["senior", "sr.", "sr ", "lead", "principal"],
}


def _mentions(skill: str, text: str) -> bool:
    """¿Aparece la skill como palabra completa? Con `in` a secas, "java" casaba
    con "javascript" y "sql" con "postgresql"/"mysql", que son skills distintas."""
    return re.search(rf"(?<![\w+#]){re.escape(skill)}(?![\w+#])", text) is not None


def score_job_offer(profile: User, offer: dict) -> tuple[int, str]:
    """Devuelve (score 0-100, reasoning) para una oferta normalizada (dict con
    title/description/location) comparada con el perfil del usuario."""
    text = f"{offer.get('title') or ''} {offer.get('description') or ''}".lower()

    skills = [s.strip().lower() for s in (profile.skills or []) if s and s.strip()]
    matched_skills = [s for s in skills if _mentions(s, text)]
    skills_score = 0
    if skills:
        expected = min(len(skills), _SKILLS_TARGET)
        skills_score = round(min(1.0, len(matched_skills) / expected) * _MAX_SKILLS_POINTS)

    location_score = 0
    offer_location = (offer.get("location") or "").lower()
    if profile.location and offer_location and profile.location.strip().lower() in offer_location:
        location_score = _LOCATION_POINTS

    seniority_score = 0
    if profile.seniority is not None:
        own_keywords = _SENIORITY_KEYWORDS.get(profile.seniority, [])
        other_keywords = [
            kw for level, kws in _SENIORITY_KEYWORDS.items() if level != profile.seniority for kw in kws
        ]
        if any(kw in text for kw in own_keywords):
            seniority_score = _SENIORITY_POINTS
        elif not any(kw in text for kw in other_keywords):
            # La oferta no menciona seniority: no penalizamos, damos crédito parcial.
            seniority_score = _SENIORITY_POINTS // 2

    score = min(100, skills_score + location_score + seniority_score)

    reasoning_parts: list[str] = []
    if skills:
        matched_label = ", ".join(matched_skills) if matched_skills else "ninguna"
        if len(skills) <= _SKILLS_TARGET:
            reasoning_parts.append(f"{len(matched_skills)}/{len(skills)} skills coinciden ({matched_label})")
        else:
            # "3/28" leería como un suspenso cuando en realidad es un buen encaje.
            reasoning_parts.append(f"{len(matched_skills)} de tus skills coinciden ({matched_label})")
    if location_score:
        reasoning_parts.append("ubicación compatible con tu perfil")
    if seniority_score >= _SENIORITY_POINTS:
        reasoning_parts.append("seniority de la oferta coincide con el tuyo")

    reasoning = "; ".join(reasoning_parts) if reasoning_parts else "Coincidencia limitada con tu perfil"
    return score, reasoning
