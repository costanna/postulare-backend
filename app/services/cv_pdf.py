"""Genera un PDF sencillo desde texto plano, sin dependencias nuevas.

Se usa cuando no hay PDF subido: el adjunto del email siempre es PDF (mejor
ante ATS y reclutadores que un .txt). Helvetica + WinAnsi: texto real y
seleccionable, con saltos de página automáticos.
"""

_PAGE_W, _PAGE_H = 595, 842
_MARGIN = 50
_FONT_SIZE = 11
_LINE_HEIGHT = 14
_MAX_CHARS_PER_LINE = 85

# Fuera de WinAnsi se sustituyen por equivalentes seguros.
_REPLACEMENTS = {
    "\u2014": "-",
    "\u2013": "-",
    "\u2019": "'",
    "\u2018": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2026": "...",
    "\u00a0": " ",
    "\u200b": "",
    "\u00b7": "-",
}


def _sanitize(text: str) -> str:
    for bad, good in _REPLACEMENTS.items():
        text = text.replace(bad, good)
    return "".join(ch if ord(ch) < 256 else "?" for ch in text)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap(text: str) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines():
        if not paragraph.strip():
            lines.append("")
            continue
        words, current = paragraph.split(), ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) > _MAX_CHARS_PER_LINE and current:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
    return lines


def _page_stream(lines: list[str]) -> str:
    body = "".join(f"({_escape(line)}) Tj T*\n" for line in lines)
    return f"BT /F1 {_FONT_SIZE} Tf {_MARGIN} {_PAGE_H - _MARGIN} Td {_LINE_HEIGHT} TL\n{body}ET"


def text_to_pdf(text: str) -> bytes:
    """Texto plano (uno o varios párrafos) a PDF de una o más páginas."""
    lines = _wrap(_sanitize(text)) or [""]
    per_page = (_PAGE_H - 2 * _MARGIN) // _LINE_HEIGHT
    pages = [lines[i : i + per_page] for i in range(0, len(lines), per_page)]

    objects: list[str] = ["<< /Type /Catalog /Pages 2 0 R >>"]
    kids: list[str] = []
    for i, page_lines in enumerate(pages):
        page_obj = 3 + i * 2
        content_obj = page_obj + 1
        kids.append(f"{page_obj} 0 R")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_PAGE_W} {_PAGE_H}] "
            f"/Contents {content_obj} 0 R /Resources << /Font << /F1 {3 + len(pages) * 2} 0 R >> >> >>"
        )
        content = _page_stream(page_lines)
        objects.append(f"<< /Length {len(content.encode('latin-1'))} >>\nstream\n{content}\nendstream")
    objects.insert(1, f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1")
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("latin-1")
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode("latin-1")
    return bytes(out)
