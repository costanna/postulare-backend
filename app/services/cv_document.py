"""CV generado en local a partir del perfil. 100% gratis, sin IA ni librerías nuevas.

No se guarda el PDF original del usuario (se descarta tras importar): este
documento se construye solo con los campos del perfil y sirve como base
para copiar/pegar al aplicar. El frontend lo muestra y el navegador lo
imprime a PDF (Ctrl+P) sin coste.
"""
from dataclasses import dataclass


@dataclass
class CvData:
    full_name: str | None = None
    desired_position: str | None = None
    location: str | None = None
    seniority: str | None = None
    skills: list[str] | None = None
    about: str | None = None
    email: str | None = None


# Solo las etiquetas las pone Postulare: el contenido (about, skills) es del
# usuario y no se traduce sin IA. `language` viene del idioma detectado en la
# oferta o del preferido del usuario.
_LABELS = {
    "es": {"skills": "Habilidades", "untitled": "Candidatura"},
    "ca": {"skills": "Habilitats", "untitled": "Candidatura"},
    "en": {"skills": "Skills", "untitled": "Application"},
}


def _labels(language: str) -> dict:
    return _LABELS.get(language, _LABELS["es"])


def _line(value: str | None) -> str:
    return (value or "").strip()


def render_cv_markdown(cv: CvData, language: str = "es") -> str:
    t = _labels(language)
    name = _line(cv.full_name) or t["untitled"]
    position = _line(cv.desired_position)
    parts = [f"# {name}"]
    if position:
        level = f" ({cv.seniority})" if cv.seniority else ""
        parts.append(f"**{position}{level}**")
    meta = " · ".join(p for p in [_line(cv.location), _line(cv.email)] if p)
    if meta:
        parts.append(meta)
    if cv.about and cv.about.strip():
        parts.append(f"\n{cv.about.strip()}")
    skills = [s.strip() for s in (cv.skills or []) if s and s.strip()]
    if skills:
        parts.append(f"\n## {t['skills']}\n\n" + ", ".join(skills))
    return "\n\n".join(parts).strip() + "\n"


def render_cv_text(cv: CvData, language: str = "es") -> str:
    markdown = render_cv_markdown(cv, language)
    # Versión plana para pegar en portales que solo aceptan texto.
    return markdown.replace("#", "").replace("**", "").strip() + "\n"


def render_cv_html(cv: CvData, language: str = "es") -> str:
    t = _labels(language)
    name = _line(cv.full_name) or t["untitled"]
    position = _line(cv.desired_position)
    skills = [s.strip() for s in (cv.skills or []) if s and s.strip()]
    skills_html = "".join(f"<li>{s}</li>" for s in skills)
    return (
        "<article>"
        f"<h1>{name}</h1>"
        + (f"<p><strong>{position}</strong></p>" if position else "")
        + "".join(
            f"<p>{p}</p>"
            for p in [_line(cv.location), _line(cv.email), (cv.about or '').strip()]
            if p
        )
        + (f"<h2>{t['skills']}</h2><ul>{skills_html}</ul>" if skills_html else "")
        + "</article>"
    )
