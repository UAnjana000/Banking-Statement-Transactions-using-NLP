"""Minimal pure-Python PDF writer for synthetic test fixtures."""

from __future__ import annotations

from pathlib import Path


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_text_pdf(path: Path, lines: list[str], *, title: str = "Synthetic Statement") -> None:
    """Write a single-page PDF with embedded text (native text layer)."""
    content_lines = ["BT", "/F1 10 Tf", "50 750 Td"]
    for i, line in enumerate(lines):
        if i == 0:
            content_lines.append(f"({_escape_pdf_text(line)}) Tj")
        else:
            content_lines.append("0 -14 Td")
            content_lines.append(f"({_escape_pdf_text(line)}) Tj")
    content_lines.append("ET")
    stream = "\n".join(content_lines)
    stream_bytes = stream.encode("latin-1", errors="replace")

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objects.append(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
    )
    objects.append(
        f"<< /Length {len(stream_bytes)} >>\nstream\n".encode() + stream_bytes + b"\nendstream"
    )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode())
        out.extend(obj)
        out.extend(b"\nendobj\n")

    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())
    title_text = _escape_pdf_text(title)
    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info << /Title ({title_text}) >> >>\n"
    )
    out.extend(trailer.encode())
    out.extend(f"startxref\n{xref_pos}\n%%EOF\n".encode())
    path.write_bytes(bytes(out))
