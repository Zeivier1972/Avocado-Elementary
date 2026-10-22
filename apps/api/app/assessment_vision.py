"""See the test, not just its text.

The plain text parser (assessment_import.parse_test_questions) recovers the
WORDING of each question but loses every figure — and most K-2 math items ARE
the figure ("Which group is greater?" over two piles of apples). Without the
picture we can't know the quantities, the objects, or what the choices show, so
a packet rebuilt from the test can't match the real items.

This module renders each test page to an image and asks the vision model to read
the graphics, returning a per-question description that INCLUDES the visual
facts: each group/set with its object and exact count, the numbers shown, and
what every answer choice depicts. That enriched stem flows straight into the DI
pipeline (number-range detection for Kinder, real_items for grades 1-3), so the
recreation reflects what is actually on the page.

It is best-effort and fails safe: if AI is off, the SDK is missing, the PDF
won't render, or the model errors, it returns {} and the caller keeps the
text-only stems.
"""
from __future__ import annotations

import base64
import json
import re

from app.core.config import settings

# Keep the request bounded: cap pages and downscale so a whole topic test is one
# affordable call. 150 DPI is enough to count small objects without huge images.
_MAX_PAGES = 16
_DPI = 150


def _render_pages(data: bytes) -> list[bytes]:
    """Each PDF page -> PNG bytes, via pymupdf (already a project dependency)."""
    try:
        import pymupdf as _mu  # pymupdf >= 1.24
    except Exception:
        try:
            import fitz as _mu   # older import name
        except Exception:
            return []
    out: list[bytes] = []
    try:
        doc = _mu.open(stream=data, filetype="pdf")
    except Exception:
        return []
    for page in doc:
        if len(out) >= _MAX_PAGES:
            break
        try:
            pix = page.get_pixmap(dpi=_DPI)
            out.append(pix.tobytes("png"))
        except Exception:
            continue
    return out


_SYSTEM = (
    "You are a meticulous assistant that reads a scanned elementary-school math "
    "test and reports EXACTLY what each numbered question shows — the words AND "
    "the pictures. Count every object carefully. You output ONLY a valid JSON "
    "array, no prose, no code fences."
)


def _prompt(positions: list[int], standards: dict) -> str:
    known = ""
    if positions:
        pairs = ", ".join(
            f"Q{p}" + (f" ({standards[p]})" if standards.get(p) else "")
            for p in positions)
        known = ("\n\nThe answer key says this test has these questions (and the "
                 f"benchmark each assesses): {pairs}. Use the SAME question "
                 "numbers you see printed on the page.")
    return (
        "Read every numbered question on these test pages. Skip cover pages and "
        "teacher administration pages. For EACH question return an object:\n"
        '{"position": <the printed question number>,\n'
        ' "stem": "<the question wording>",\n'
        ' "visual": "<describe the figure: list each group/set as \'<object> x '
        '<count>\' (e.g. \'red apples x7\'), or the numbers shown; say what is '
        'being compared, counted, or classified>",\n'
        ' "choices": "<what each lettered choice shows, e.g. \'A: 1 apple  B: 1 '
        'white apple\' or \'A: 5  B: 9\' or \'A: yes  B: no\'>"}\n'
        "Count objects EXACTLY — the counts are the whole point. If a question is "
        "purely numeric (comparing written numerals), put the numerals in "
        '"visual". Return ONLY the JSON array, ordered by position.' + known)


def _coerce(obj: dict) -> tuple[int, str] | None:
    try:
        pos = int(obj.get("position"))
    except (TypeError, ValueError):
        return None
    stem = str(obj.get("stem") or "").strip()
    visual = str(obj.get("visual") or "").strip()
    choices = str(obj.get("choices") or "").strip()
    parts = [p for p in (stem, f"Picture: {visual}" if visual else "",
                         f"Choices: {choices}" if choices else "") if p]
    text = " ".join(parts).strip()
    text = re.sub(r"\s+", " ", text)
    return (pos, text[:2000]) if text else None


def enrich_questions_with_vision(data: bytes, items: list | None = None) -> dict:
    """position -> enriched stem (wording + described figure + choices).

    `items` is the answer-key blueprint (each with position + standard); it only
    steers the model toward the right question numbers. Returns {} on any
    failure so the caller falls back to the text-only stems.
    """
    if not (settings.ai_provider == "anthropic" and settings.ai_api_key):
        return {}
    images = _render_pages(data)
    if not images:
        return {}
    positions = sorted(int(it["position"]) for it in (items or [])
                       if str(it.get("position", "")).strip().isdigit())
    standards = {int(it["position"]): (it.get("standard") or "")
                 for it in (items or [])
                 if str(it.get("position", "")).strip().isdigit()}
    try:
        import anthropic
    except Exception:
        return {}
    content: list = [
        {"type": "image",
         "source": {"type": "base64", "media_type": "image/png",
                    "data": base64.b64encode(png).decode("ascii")}}
        for png in images
    ]
    content.append({"type": "text", "text": _prompt(positions, standards)})
    try:
        client = anthropic.Anthropic(api_key=settings.ai_api_key, timeout=480.0,
                                     max_retries=2)
    except Exception:
        return {}
    # Try the configured model first; if it can't read images (or otherwise
    # errors), fall back to a known vision-capable model so reading the test
    # figures still works regardless of how AI_MODEL is set. De-duplicated and
    # order-preserving.
    models = list(dict.fromkeys(
        m for m in (settings.ai_model_vision, settings.ai_model,
                    "claude-sonnet-5") if m))
    msg = None
    for mdl in models:
        try:
            msg = client.messages.create(
                model=mdl, max_tokens=6000, system=_SYSTEM,
                messages=[{"role": "user", "content": content}])
            break
        except Exception:
            msg = None
            continue
    if msg is None:
        return {}
    text = "".join(getattr(b, "text", "") for b in msg.content
                   if getattr(b, "type", "") == "text").strip()
    arr = _parse_json_array(text)
    if not arr:
        return {}
    out: dict = {}
    for obj in arr:
        if isinstance(obj, dict):
            got = _coerce(obj)
            if got:
                out[got[0]] = got[1]
    return out


def _parse_json_array(text: str):
    """Tolerant array extraction (mirrors ai._parse_json_array's intent)."""
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    try:
        v = json.loads(s)
        return v if isinstance(v, list) else None
    except Exception:
        pass
    i, j = s.find("["), s.rfind("]")
    if 0 <= i < j:
        try:
            v = json.loads(s[i:j + 1])
            return v if isinstance(v, list) else None
        except Exception:
            return None
    return None
