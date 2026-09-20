"""Genera PDFs mínimos válidos con texto, para probar el importador de CV sin
depender de ningún CV real (nunca se copian datos personales al repositorio)."""


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(lines: list[str]) -> bytes:
    """PDF de una página: una línea de texto por elemento de `lines` (vacío = PDF sin texto)."""
    body = "".join(f"({_escape(line)}) Tj T*\n" for line in lines)
    content = f"BT /F1 11 Tf 50 780 Td 14 TL\n{body}ET" if lines else ""

    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content.encode('latin-1'))} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{obj}\nendobj\n".encode("latin-1")

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1")
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode("latin-1")
    )
    return bytes(out)


FAKE_CV_LINES = [
    "LAURA EJEMPLO",
    "Desarrolladora Full Stack Junior",
    "Girona | laura@example.com | 600 000 000",
    "PERFIL PROFESIONAL",
    "Desarrolladora junior con proyectos en Python y Angular. Me gusta aprender y trabajar en equipo.",
    "HABILIDADES",
    "Python, FastAPI, Angular, TypeScript, PostgreSQL, Docker, Git, Scrum, Java",
    "Uso JavaScript a diario y Angular en todos mis proyectos.",
    "EXPERIENCIA",
    "Proyecto personal con Docker y PostgreSQL.",
]
