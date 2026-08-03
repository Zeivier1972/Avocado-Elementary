"""Extract plain text from an uploaded document (pacing guide, resource, etc.)
so the planning-guide generator can be grounded in what the coach uploaded.

Supports PDF (pypdf), Word (.docx), Excel (.xlsx), and plain text/CSV. Returns
("", reason) when the file has no extractable text (e.g. a scanned/image-only
PDF) so the caller can explain it to the user."""
from __future__ import annotations

import io


def extract_document_text(filename: str, content_type: str, data: bytes) -> tuple[str, str]:
    name = (filename or "").lower()
    ct = (content_type or "").lower()

    # PDF
    if name.endswith(".pdf") or "pdf" in ct:
        return _from_pdf(data)
    # Word
    if name.endswith(".docx") or "wordprocessingml" in ct:
        return _from_docx(data)
    # Excel
    if name.endswith((".xlsx", ".xlsm")) or "spreadsheetml" in ct:
        return _from_xlsx(data)
    # Plain text / CSV
    if name.endswith((".txt", ".csv", ".md")) or ct.startswith("text/"):
        try:
            return data.decode("utf-8-sig", errors="replace"), ""
        except Exception as e:  # pragma: no cover
            return "", f"could not decode text file: {e}"
    # Fallback: try PDF, then text
    txt, _ = _from_pdf(data)
    if txt:
        return txt, ""
    try:
        return data.decode("utf-8-sig", errors="replace"), ""
    except Exception:
        return "", "unsupported file type — upload a PDF, Word, Excel, or text pacing guide"


def _from_pdf(data: bytes) -> tuple[str, str]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "", "PDF support not installed (pypdf)"
    try:
        reader = PdfReader(io.BytesIO(data))
        parts = [(p.extract_text() or "") for p in reader.pages]
        text = "\n".join(parts).strip()
        if not text:
            return "", ("this PDF has no selectable text (it looks scanned/"
                        "image-only) — upload a text-based PDF or a Word version")
        return text, ""
    except Exception as e:
        return "", f"could not read PDF: {e}"


def _from_docx(data: bytes) -> tuple[str, str]:
    try:
        from docx import Document
    except ImportError:
        return "", "Word support not installed (python-docx)"
    try:
        doc = Document(io.BytesIO(data))
        lines = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells]
                if any(cells):
                    lines.append(" | ".join(cells))
        text = "\n".join(lines).strip()
        return (text, "") if text else ("", "the Word document has no text")
    except Exception as e:
        return "", f"could not read Word document: {e}"


def _from_xlsx(data: bytes) -> tuple[str, str]:
    try:
        from openpyxl import load_workbook
    except ImportError:
        return "", "Excel support not installed (openpyxl)"
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        lines = []
        for ws in wb.worksheets:
            lines.append(f"# Sheet: {ws.title}")
            for row in ws.iter_rows(values_only=True):
                cells = [str(c) for c in row if c not in (None, "")]
                if cells:
                    lines.append(" | ".join(cells))
        text = "\n".join(lines).strip()
        return (text, "") if text else ("", "the spreadsheet has no data")
    except Exception as e:
        return "", f"could not read spreadsheet: {e}"
