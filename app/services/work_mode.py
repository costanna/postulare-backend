"""Modalidad de trabajo de una oferta: remoto, híbrido o presencial.

Adzuna no tiene ese dato, así que se deduce del texto (título, ubicación y descripción; en las de InfoJobs
también entra su campo de teletrabajo). Solo se afirma lo que el texto dice: "remoto" y "híbrido" necesitan una
mención explícita. Una oferta que no dice nada se trata como presencial, que es lo habitual, pero no se etiqueta.
"""
import re

_FLAGS = re.IGNORECASE

_REMOTE = re.compile(
    r"\bremot[oa]s?\b|\bremote\b|teletrabaj|teletreball|trabajo a distancia|desde casa|work from home|"
    r"\bwfh\b|100\s?%\s?(en\s)?remot|totalmente en remoto",
    _FLAGS,
)
_HYBRID = re.compile(
    r"h[ií]brid|hybrid|semi-?presencial|modelo mixto|"
    r"\d\s+d[ií]as?\s+(a la semana\s+)?(de\s+|en\s+)?(la\s+)?(oficina|presencial|teletrabajo|remoto)|"
    r"(presencial|oficina)\s+(y|\+|/)\s+(teletrabajo|remoto|remote)|(teletrabajo|remoto|remote)\s+(y|\+|/)\s+(presencial|oficina)|"
    r"(parcialmente|parcial)\s+(en\s+)?(remot|teletrabaj)|teletrabajo\s+parcial",
    _FLAGS,
)
_ONSITE = re.compile(r"\bpresencial\b|\bon-?site\b|en (la |nuestra |nuestras )?oficinas?\b", _FLAGS)
_NEGATED_REMOTE = re.compile(
    r"(sin|no\s+(hay|es|se\s+ofrece|admite|ofrecemos))\s+(opci[oó]n\s+de\s+)?(teletrabaj|remot)|no\s+remot",
    _FLAGS,
)


def _text(offer: dict) -> str:
    return " ".join(str(offer.get(field) or "") for field in ("title", "location", "description"))


def detect_work_mode(offer: dict) -> str | None:
    """"remote" | "hybrid" | "onsite" si la oferta lo dice; None si no dice nada."""
    text = _text(offer)
    if _HYBRID.search(text):
        return "hybrid"
    if _NEGATED_REMOTE.search(text):
        return "onsite"
    remote, onsite = _REMOTE.search(text), _ONSITE.search(text)
    if remote and onsite:
        return "hybrid"
    if remote:
        return "remote"
    if onsite:
        return "onsite"
    return None


def filter_by_work_mode(offers: list[dict], mode: str) -> list[dict]:
    """"remote" y "hybrid" piden mención explícita; "onsite" incluye también las que no dicen nada."""
    if mode == "remote":
        return [offer for offer in offers if detect_work_mode(offer) == "remote"]
    if mode == "hybrid":
        return [offer for offer in offers if detect_work_mode(offer) == "hybrid"]
    if mode == "onsite":
        return [offer for offer in offers if detect_work_mode(offer) in ("onsite", None)]
    return offers
