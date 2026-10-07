"""Idioma de una oferta (ca/es/en) por marcadores. Sin dependencias ni IA.

Cuenta palabras y expresiones distintivas en el título + la descripción.
Si no hay señales claras (título corto tipo "Python Developer", empate),
devuelve None y quien llama usa el idioma preferido del usuario.
"""
import html
import re

_MARKERS: dict[str, tuple[str, ...]] = {
    "ca": (
        "amb",
        "però",
        "perquè",
        "dels",
        "pels",
        "coneixements",
        "requisits",
        "cerquem",
        "busquem",
        "oferim",
        "teletreball",
        "incorporació",
        "experiència",
        "l'empresa",
        "jornada completa",
        "lloc de treball",
    ),
    "es": (
        "buscamos",
        "conocimientos",
        "requisitos",
        "se ofrece",
        "incorporación",
        "puesto de trabajo",
        "teletrabajo",
        "salario",
        "contrato",
        "experiencia",
        "jornada completa",
        "imprescindible",
        "se valorará",
    ),
    "en": (
        "looking for",
        "we offer",
        "requirements",
        "benefits",
        "join our",
        "full-time",
        "skills",
        "experience",
        "apply now",
        "you will",
        "we are",
    ),
}

# Palabras cortas pero muy distintivas: solo cuentan con límites de palabra.
_SHORT_MARKERS: dict[str, tuple[str, ...]] = {
    "ca": (),
    "es": ("con", "pero", "porque"),
    "en": ("with", "and", "the", "for"),
}


def _clean(text: str | None) -> str:
    if not text:
        return ""
    no_html = re.sub(r"<[^>]+>", " ", text)
    return html.unescape(no_html).lower()


def detect_language(*texts: str | None) -> str | None:
    """Idioma dominante ("ca", "es" o "en") o None si no hay señales claras."""
    body = " ".join(_clean(text) for text in texts if text)
    if not body:
        return None
    scores: dict[str, int] = {}
    for lang, markers in _MARKERS.items():
        scores[lang] = sum(body.count(marker) for marker in markers)
    words = set(re.findall(r"[a-zà-ÿ']+", body))
    for lang, markers in _SHORT_MARKERS.items():
        scores[lang] += sum(1 for marker in markers if marker in words)
    best = max(scores, key=lambda lang: scores[lang])
    if scores[best] == 0:
        return None
    if sum(1 for score in scores.values() if score == scores[best]) > 1:
        return None
    return best
