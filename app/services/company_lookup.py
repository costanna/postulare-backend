"""Descubre el email de una empresa desde su propia web (solo si la oferta no lo trae).

Sin claves: Clearbit Autocomplete (dominio por nombre, gratis y sin key) +
lectura de la home y páginas de contacto para emails del propio dominio.
Solo se aceptan emails del dominio de la empresa y con prefijos de contacto
o empleo: nunca se inventa ni se adivina nada.

Todo va con caché: una empresa se busca una vez cada 6 h como máximo.
"""
import re

import httpx

from app.services.duplicates import normalize
from app.services.emails import extract_contact_email
from app.services.job_search import _cache_get, _cache_put

CLEARBIT_URL = "https://autocomplete.clearbit.com/v1/companies/suggest"

_TIMEOUT = 8.0
_CONTACT_PATHS = ("", "/contact", "/contacto", "/jobs", "/empleo", "/careers")
_MAX_PAGES = 5

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

# Prefijos que indican buzón de contacto/empleo (en cualquier idioma).
_GOOD_PREFIXES = (
    "job", "jobs", "career", "careers", "recruit", "talent", "hiring", "work",
    "empleo", "curriculum", "cv", "rrhh", "rh", "info", "contact", "hola",
    "hello", "treball", "feina",
)


def _best_domain(name: str, candidates: list[dict]) -> str | None:
    wanted = set(normalize(name).split())
    if not wanted:
        return None
    best: str | None = None
    best_score = 0
    for item in candidates:
        if not isinstance(item, dict):
            continue
        domain = item.get("domain")
        got = set(normalize(item.get("name")).split())
        score = len(wanted & got)
        if domain and score > best_score:
            best, best_score = domain, score
    return best


def domain_for_company(company_name: str | None) -> str | None:
    """Dominio de la empresa según Clearbit, o None."""
    if not company_name or not company_name.strip():
        return None
    cache_key = ("company_domain", company_name.strip().lower())
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached[0] if cached else None
    try:
        response = httpx.get(CLEARBIT_URL, params={"query": company_name.strip()}, timeout=_TIMEOUT)
        response.raise_for_status()
        domain = _best_domain(company_name, response.json())
    except (httpx.HTTPError, ValueError):
        domain = None
    _cache_put(cache_key, [domain] if domain else [])
    return domain


def _website_emails(domain: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for path in _CONTACT_PATHS[:_MAX_PAGES]:
        try:
            response = httpx.get(
                f"https://{domain}{path}",
                headers={"User-Agent": "Postulare/1.0 (job application; contact: postulare.app)"},
                follow_redirects=True,
                timeout=_TIMEOUT,
            )
            if response.status_code != 200:
                continue
            for match in _EMAIL_RE.findall(response.text):
                email = match.rstrip(".,;:!?()")
                lowered = email.lower()
                if not lowered.endswith("@" + domain.lower()):
                    continue
                prefix = lowered.split("@")[0]
                if not any(key in prefix for key in _GOOD_PREFIXES):
                    continue
                if lowered not in seen:
                    seen.add(lowered)
                    found.append(email)
        except (httpx.HTTPError, ValueError):
            continue
    return found


def discover_company_email(
    company_name: str | None, title: str | None = None, description: str | None = None
) -> tuple[str | None, str | None]:
    """(email, origen). Origen: "offer" (en la oferta), "website" (web propia) o None."""
    direct = extract_contact_email(description, title)
    if direct:
        return direct, "offer"
    domain = domain_for_company(company_name)
    if not domain:
        return None, None
    cache_key = ("company_emails", domain)
    cached = _cache_get(cache_key)
    emails = cached if cached is not None else None
    if emails is None:
        emails = _website_emails(domain)
        _cache_put(cache_key, emails)
    if not emails:
        return None, None
    return emails[0], "website"
