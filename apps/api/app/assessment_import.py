"""Parse a topic-test ANSWER KEY (and optionally the test itself) into an
assessment blueprint: which standard each item assesses, the correct response,
and the points. This is the backbone for tracking standards all year and, later,
scoring class results to find the deficient standard per class for DI.

The answer-key export is a fixed table:
  Item Label | Item Id | Standard(s) | Interaction Type | Correct Response(s) | Possible Points
e.g.  "3. 21488374FL.20.BEST.MA.3.NSO.2.2Choice/Multi-ResponseD 1.0"
"""
from __future__ import annotations

import io
import re

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover
    PdfReader = None


def _pymupdf_text(data: bytes) -> str:
    """pymupdf (fitz) reads fonts/encodings that pypdf returns empty for."""
    try:
        import pymupdf as _mu  # pymupdf >= 1.24
    except Exception:
        try:
            import fitz as _mu   # older import name
        except Exception:
            return ""
    try:
        doc = _mu.open(stream=data, filetype="pdf")
        return "\n".join(p.get_text() for p in doc)
    except Exception:
        return ""


def _pdf_text(data: bytes) -> str:
    text = ""
    if PdfReader is not None:
        try:
            r = PdfReader(io.BytesIO(data))
            text = "\n".join((p.extract_text() or "") for p in r.pages)
        except Exception:
            text = ""
    # Some test PDFs extract as empty under pypdf (font/encoding it can't decode);
    # fall back to pymupdf, which reads them. Already a project dependency.
    if not text.strip():
        text = _pymupdf_text(data)
    return text


def normalize_standard(raw: str) -> str:
    """'FL.20.BEST.MA.3.NSO.2.2' -> 'MA.3.NSO.2.2'; 'No Standard' -> ''."""
    raw = (raw or "").strip()
    if not raw or raw.lower().startswith("no standard"):
        return ""
    m = re.search(r"(MA\.[A-Z0-9]+\.[A-Z]+\.\d+\.\d+)", raw)
    if m:
        return m.group(1)
    return raw.replace("FL.20.BEST.", "").strip()


def _grade_topic_subject(test_name: str) -> tuple[str, str, str]:
    """From '2026-2027-T-Math-Gr03-T1-PBT' -> ('3', 'Topic 1', 'MATH')."""
    grade, topic, subject = "", "", "MATH"
    m = re.search(r"Gr(\w{1,2})", test_name)
    if m:
        g = m.group(1).upper()
        if g in ("KG", "00", "0K", "K"):
            grade = "K"
        else:
            grade = str(int(g)) if g.isdigit() else g
    m = re.search(r"-T(\d+)", test_name)
    if m:
        topic = f"Topic {int(m.group(1))}"
    m = re.search(r"-(Math|Reading|ELA|Science)-", test_name, re.I)
    if m:
        subject = m.group(1).upper()
    return grade, topic, subject


# One answer-key row: number, item id, standard-or-"No Standard", the interaction
# type, then the correct response(s) and the points (float) — responses may wrap
# across lines, so match lazily up to the trailing float. The item id, standard
# and interaction type may be concatenated (older exports) OR space/newline
# separated (Performance Matters K-2 exports: "14800394 FL.20.BEST.MA.K.NSO.1.1
# Choice/Multi-Response C"), so allow optional whitespace between every field.
_ROW = re.compile(
    r"(?P<pos>\d+)\.\s*(?P<item>\d+)\s*"
    r"(?P<std>FL\.20\.BEST\.[A-Z0-9.]+|No Standard)"
    r"\s*Choice/Multi-Response"
    r"(?P<resp>.*?)"
    r"(?P<pts>\d+\.\d+)",
    re.S,
)


def parse_answer_key(data: bytes) -> dict:
    """Return the blueprint: test meta + one row per item."""
    text = _pdf_text(data)
    if not text.strip():
        return {"items": [], "reason": "could not read text from the answer-key PDF"}

    test_name = ""
    m = re.search(r"Test Name:\s*(\S+)", text)
    if m:
        test_name = m.group(1).strip()
    test_id = ""
    m = re.search(r"Test Id:\s*(\d+)", text, re.I)
    if m:
        test_id = m.group(1).strip()
    grade, topic_code, subject = _grade_topic_subject(test_name)

    items = []
    for m in _ROW.finditer(text):
        resp_letters = re.findall(r"[A-E]", m.group("resp"))
        std_raw = m.group("std").strip()
        std = normalize_standard(std_raw)
        pts = float(m.group("pts"))
        items.append({
            "position": int(m.group("pos")),
            "item_id": m.group("item").strip(),
            "standard": std,
            "standard_raw": std_raw,
            "correct_response": ",".join(resp_letters),
            "points": pts,
            "scored": bool(std) and pts > 0,
        })
    items.sort(key=lambda x: x["position"])
    if not items:
        return {"items": [], "reason": "no answer-key rows found"}

    total_points = sum(i["points"] for i in items)
    standards = []
    for i in items:
        if i["standard"] and i["standard"] not in standards:
            standards.append(i["standard"])
    return {
        "test_name": test_name, "test_id": test_id, "grade": grade,
        "topic_code": topic_code, "subject": subject,
        "item_count": len(items), "total_points": total_points,
        "standards": standards, "items": items, "reason": None,
    }


# --- Optional: pull each question's text from the student test PDF -------------

_HEADER_LINE = re.compile(
    r"^\s*(20\d\d-.*-PBT|Test ID:.*|Name _.*|\d+\s*)$", re.M)
_DASHES = re.compile(r"_{5,}")

# Circled answer bullets Ⓐ Ⓑ Ⓒ Ⓓ (U+24B6–24B9) used on Performance Matters
# paper tests. Their presence marks a real question (vs. a cover/admin page).
_CIRCLED = "ⒶⒷⒸⒹ"


def _questions_by_blocks(raw: str) -> dict:
    """Fallback for test PDFs with NO inline item numbers (Performance Matters
    paper tests number items with a graphic badge that doesn't extract, so only
    page numbers show as text). Split on page headers (each page repeats
    'Test ID: …') and the answer dividers, then every chunk carrying the circled
    answer bullets (Ⓐ–Ⓓ) is the next question in order — position 1, 2, 3, ….
    Order matches the answer key, which is also 1..N in order."""
    marked = re.sub(r"Test ID:\s*\d+", "\x00", raw, flags=re.I)
    marked = _DASHES.sub("\x00", marked)
    out: dict = {}
    pos = 0
    for chunk in marked.split("\x00"):
        if sum(1 for c in _CIRCLED if c in chunk) < 2:
            continue  # no answer choices → cover / admin-instructions page
        body = re.sub(r"20\d\d-\S*", " ", chunk)                 # running test name
        body = re.sub(r"^\s*\d+\s*$", " ", body, flags=re.M)     # page #s / loose options
        body = re.sub(r"Name\b.*?Date\b\S*", " ", body, flags=re.I | re.S)
        body = re.sub(r"You have reached the end.*", " ", body, flags=re.I | re.S)
        body = re.sub(f"[{_CIRCLED}]", " ", body)                # drop the choice bullets
        body = re.sub(r"^[\W_]+", "", body)
        body = re.sub(r"\s+", " ", body).strip()
        if len(body) < 6:
            continue
        pos += 1
        out[pos] = body[:1200]
    return out


def parse_test_questions(data: bytes) -> dict:
    """Best-effort: map question number -> its text (stem + choices). Figures in
    the PDF are lost, but the wording is enough to pick items for DI packets.

    Handles BOTH numbering styles: '12. Which…' (period) AND the Performance
    Matters style where the item number is a graphic badge that extracts as a
    bare number ('1 Count the starfish…'). A question starts at a 1-2 digit
    number followed by a capital-letter word (the stem), which avoids splitting
    on answer choices like '1 2 3 4' or on page numbers."""
    raw = _pdf_text(data)
    if not raw.strip():
        return {"questions": {}}
    text = _DASHES.sub("\n", raw)
    text = _HEADER_LINE.sub("", text)
    text = "\n" + text
    # A question starts at a 1-2 digit number (with optional . or )) then a
    # CAPITAL letter — the start of the stem. Using [A-Z] (not [A-Z][a-z]) so a
    # stem that opens with a one-letter word ("A package…", "I have…") is still
    # detected; a digit after the number (answer rows like "1 2 3 4", page refs)
    # still fails the lookahead, so those don't split.
    pat = re.compile(r"\n\s*(\d{1,2})[.)]?\s+(?=[A-Z])")
    matches = list(pat.finditer(text))
    questions: dict = {}
    for idx, mt in enumerate(matches):
        try:
            num = int(mt.group(1))
        except ValueError:
            continue
        start = mt.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = re.sub(r"\s+", " ", text[start:end]).strip()
        body = body.split("You have reached the end")[0].strip()
        # Strip the running test-name / Test ID header and stray page numbers that
        # land inside a stem when a question spans a page break.
        body = re.sub(r"20\d\d-\S*-PBT", " ", body)
        body = re.sub(r"Test ID:\s*\d+", " ", body, flags=re.I)
        # Drop a leading 'Name ___ Date ___' and any leading punctuation/underscores.
        body = re.sub(r"^\s*Name\b.*?Date\b\S*\s*", "", body, flags=re.I)
        body = re.sub(r"^[\W_]+", "", body).strip()
        body = re.sub(r"\s{2,}", " ", body).strip()
        if body and len(body) > 8 and (num not in questions or
                                       len(body) > len(questions[num])):
            questions[num] = body[:1200]
    # If the inline-number approach found little (e.g. a paper test whose item
    # numbers are graphic badges, so only page numbers extract), fall back to
    # splitting by page headers + answer dividers and numbering sequentially.
    if len(questions) < 3:
        blocks = _questions_by_blocks(raw)
        if len(blocks) > len(questions):
            questions = blocks
    return {"questions": questions}
