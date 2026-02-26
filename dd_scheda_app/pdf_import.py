from __future__ import annotations

from pathlib import Path
from pypdf import PdfReader


def read_pdf_fields(pdf_path: Path) -> dict:
    reader = PdfReader(str(pdf_path))
    fields = reader.get_fields() or {}
    out = {}
    for k, v in fields.items():
        val = v.get("/V", "")
        if val is None:
            val = ""
        out[k] = str(val)
    return out
