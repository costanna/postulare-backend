"""Importar un CV en PDF para rellenar el perfil (sin IA, sin coste).

El PDF se lee en memoria y se descarta: no se guarda el fichero ni el texto
completo, solo se devuelve una PROPUESTA (puesto, ubicación, nivel, skills y
resumen) que el usuario revisa antes de guardarla en su perfil.

Es heurístico y tolerante a los CV reales (es/ca/en): usa un diccionario de
tecnologías con mayúsculas canónicas y ordena las skills para que las primeras
sean las que mejor sirven para buscar (lenguajes y frameworks) y las genéricas
(Git, Scrum, HTML...) o de IA queden al final - la búsqueda usa las primeras 5.
"""
import io
import re
from dataclasses import dataclass, field

from pypdf import PdfReader

MAX_SKILLS = 30
MAX_ABOUT_CHARS = 600


class CvParseError(Exception):
    """El PDF no se puede leer o no contiene texto."""


@dataclass
class CvProposal:
    full_name: str | None = None
    desired_position: str | None = None
    location: str | None = None
    seniority: str | None = None
    skills: list[str] = field(default_factory=list)
    about: str | None = None


# (nombre canónico, alias en minúsculas). Grupo: 0 lenguajes/frameworks, 1 datos/cloud/devops,
# 2 herramientas y metodologías genéricas, 3 IA.
_SKILLS: list[tuple[str, tuple[str, ...], int]] = [
    ("Python", ("python",), 0), ("Java", ("java",), 0), ("JavaScript", ("javascript",), 0),
    ("TypeScript", ("typescript",), 0), ("C#", ("c#",), 0), ("C++", ("c++",), 0), (".NET", (".net",), 0),
    ("PHP", ("php",), 0), ("Kotlin", ("kotlin",), 0), ("Swift", ("swift",), 0), ("Ruby", ("ruby",), 0),
    ("Go", ("golang",), 0), ("Rust", ("rust",), 0), ("R", (), 0),
    ("Angular", ("angular",), 0), ("React", ("react", "react.js", "reactjs"), 0), ("Vue.js", ("vue.js", "vue"), 0),
    ("Next.js", ("next.js", "nextjs"), 0), ("Node.js", ("node.js", "nodejs"), 0), ("Express", ("express",), 0),
    ("Spring Boot", ("spring boot",), 0), ("Spring", ("spring",), 0), ("FastAPI", ("fastapi",), 0),
    ("Django", ("django",), 0), ("Flask", ("flask",), 0), ("Laravel", ("laravel",), 0), (".NET Core", (), 0),
    ("Tailwind CSS", ("tailwind css", "tailwind"), 0), ("Bootstrap", ("bootstrap",), 0), ("MUI", ("mui",), 0),
    ("Angular Material", ("angular material",), 0), ("Pandas", ("pandas",), 0), ("NumPy", ("numpy",), 0),
    ("SQL", ("sql",), 1), ("PostgreSQL", ("postgresql", "postgres"), 1), ("MySQL", ("mysql",), 1),
    ("MongoDB", ("mongodb",), 1), ("SQLite", ("sqlite",), 1), ("Redis", ("redis",), 1), ("GraphQL", ("graphql",), 1),
    ("Docker", ("docker",), 1), ("Kubernetes", ("kubernetes", "k8s"), 1), ("AWS", ("aws",), 1),
    ("Azure", ("azure",), 1), ("GCP", ("gcp", "google cloud"), 1), ("Linux", ("linux",), 1),
    ("Firebase", ("firebase",), 1), ("Power BI", ("power bi",), 1), ("Tableau", ("tableau",), 1),
    ("Jest", ("jest",), 2), ("JUnit", ("junit",), 2), ("Vitest", ("vitest",), 2), ("Cypress", ("cypress",), 2),
    ("Selenium", ("selenium",), 2), ("Git", ("git",), 2), ("GitHub", ("github",), 2), ("GitLab", ("gitlab",), 2),
    ("Jira", ("jira",), 2), ("Scrum", ("scrum",), 2), ("Agile", ("agile", "ágil"), 2), ("Kanban", ("kanban",), 2),
    ("REST API", ("rest api", "rest", "restful"), 2), ("JWT", ("jwt",), 2), ("CI/CD", ("ci/cd",), 2),
    ("HTML5", ("html5", "html"), 2), ("CSS3", ("css3", "css"), 2), ("MVC", ("mvc",), 2), ("Axios", ("axios",), 2),
    ("Context API", ("context api",), 2), ("Figma", ("figma",), 2), ("Excel", ("excel",), 2),
    ("Machine Learning", ("machine learning",), 3), ("TensorFlow", ("tensorflow",), 3),
    ("PyTorch", ("pytorch",), 3), ("scikit-learn", ("scikit-learn", "sklearn"), 3),
    ("LLMs", ("llms", "llm"), 3), ("Claude", ("claude",), 3), ("ChatGPT", ("chatgpt",), 3),
    ("Prompt engineering", ("prompt engineering",), 3),
]
# "R" y ".NET Core" no tienen alias propio (se dejan fuera del reconocimiento: "R" casaría con cualquier cosa)
_SKILLS = [entry for entry in _SKILLS if entry[1]]

_ROLE_WORDS = re.compile(
    r"desarrollador|desenvolupador|developer|programador|programmer|engineer|ingenier|enginyer|analista|analyst|"
    r"arquitect|architect|dise[ñn]ador|dissenyador|designer|cient[ií]fic|scientist|t[eè]cnic|consultor|"
    r"devops|tester|\bqa\b|administrador|data\b",
    re.IGNORECASE,
)
_SEPARATORS = re.compile(r"\s*[·•|–—]\s*|\s+-\s+")
_ABOUT_HEADINGS = re.compile(
    r"^(perfil profesional|perfil professional|perfil|resumen profesional|resumen|resum professional|resum|"
    r"sobre m[ií]|sobre mi|objetivo profesional|objectiu professional|professional profile|profile|"
    r"professional summary|summary|about me)$",
    re.IGNORECASE,
)


def extract_text(pdf_bytes: bytes, max_pages: int) -> str:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if reader.is_encrypted:
            raise CvParseError("El PDF está protegido con contraseña")
        pages = reader.pages[:max_pages]
        text = "\n".join((page.extract_text() or "") for page in pages)
    except CvParseError:
        raise
    except Exception as exc:  # pypdf lanza tipos muy variados ante ficheros corruptos
        raise CvParseError("No se ha podido leer el PDF") from exc

    if len(text.strip()) < 40:
        raise CvParseError("El PDF no contiene texto (¿es un escaneo? Necesita ser un PDF de texto)")
    return text


def _lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def _is_heading(line: str) -> bool:
    letters = re.sub(r"[^A-Za-zÀ-ÿ]", "", line)
    return len(letters) >= 4 and line == line.upper() and len(line) <= 60


def _full_name(lines: list[str]) -> str | None:
    if not lines:
        return None
    first = lines[0]
    words = first.split()
    if 2 <= len(words) <= 5 and all(re.fullmatch(r"[A-Za-zÀ-ÿ'.-]+", w) for w in words):
        return first.title() if first.isupper() else first
    return None


def _position(lines: list[str]) -> str | None:
    for line in lines[1:7]:
        if "@" in line or line.count("|") >= 2:  # línea de contacto
            continue
        if _ROLE_WORDS.search(line):
            first_part = _SEPARATORS.split(line)[0].strip(" -–—·•|")
            if 3 <= len(first_part) <= 80:
                return first_part
    return None


def _location(lines: list[str]) -> str | None:
    for line in lines[1:8]:
        if "|" in line or "@" in line:
            head = line.split("|")[0].strip()
            if re.fullmatch(r"[A-Za-zÀ-ÿ' ,.-]{2,40}", head) and not re.search(r"\d|@", head):
                return head
    return None


def _seniority(lines: list[str], position: str | None) -> str | None:
    header = " ".join(lines[:8] + ([position] if position else [])).lower()
    if re.search(r"\b(senior|sènior|sr\.?|lead)\b", header):
        return "senior"
    if re.search(r"\b(junior|júnior|jr\.?|trainee|becari[oa]?|pr[aá]cticas|pràctiques)\b", header):
        return "junior"
    if re.search(r"\b(semi[- ]?senior|mid[- ]?level|intermedi[oa])\b", header):
        return "mid"
    return None


def _about(lines: list[str]) -> str | None:
    for i, line in enumerate(lines):
        if _ABOUT_HEADINGS.match(line.strip()) and _is_heading(line):
            chunk: list[str] = []
            for nxt in lines[i + 1 :]:
                if _is_heading(nxt):
                    break
                chunk.append(nxt)
            text = re.sub(r"\s+", " ", " ".join(chunk)).strip()
            if not text:
                return None
            if len(text) > MAX_ABOUT_CHARS:
                cut = text[:MAX_ABOUT_CHARS]
                end = max(cut.rfind(". "), cut.rfind("."))
                text = cut[: end + 1] if end > 200 else cut.rstrip() + "…"
            return text
    return None


def _skills_found(text: str) -> list[str]:
    lowered = text.lower()
    found: list[tuple[int, int, int, str]] = []  # (grupo, -apariciones, primera posición, nombre)
    for canonical, aliases, group in _SKILLS:
        count, first = 0, len(lowered)
        for alias in aliases:
            for match in re.finditer(rf"(?<![\w+#.]){re.escape(alias)}(?![\w+#])", lowered):
                count += 1
                first = min(first, match.start())
        if count:
            found.append((group, -count, first, canonical))
    found.sort()
    names = [name for *_rest, name in found]
    # "Spring" suelto sobra si ya está "Spring Boot"; "Angular Material" no sustituye a "Angular"
    if "Spring Boot" in names and "Spring" in names:
        names.remove("Spring")
    return names[:MAX_SKILLS]


def parse_cv_text(text: str) -> CvProposal:
    lines = _lines(text)
    position = _position(lines)
    return CvProposal(
        full_name=_full_name(lines),
        desired_position=position,
        location=_location(lines),
        seniority=_seniority(lines, position),
        skills=_skills_found(text),
        about=_about(lines),
    )


def parse_cv_pdf(pdf_bytes: bytes, max_pages: int) -> CvProposal:
    return parse_cv_text(extract_text(pdf_bytes, max_pages))
