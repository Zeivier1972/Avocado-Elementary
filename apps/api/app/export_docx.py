"""Render a Collaborative Planning Guide (the JSON produced by app.ai) into an
editable Word document, mirroring the district's planning-guide format."""
import io
import os

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

# School logo shown at the top of every document, if the file is present.
# Set AVOCADO_LOGO to an absolute path, or drop it at app/data/school_logo.png.
_LOGO_PATHS = [
    os.environ.get("AVOCADO_LOGO", ""),
    os.path.join(os.path.dirname(__file__), "data", "school_logo.png"),
]


def _add_logo(doc):
    for p in _LOGO_PATHS:
        if p and os.path.exists(p):
            try:
                para = doc.add_paragraph()
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                para.add_run().add_picture(p, width=Inches(2.2))
                return
            except Exception:
                return


def _heading(doc, text, size, color=(0x38, 0x60, 0x1F), bold=True):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor(*color)
    return p


def _label(doc, label, value):
    if not value:
        return
    p = doc.add_paragraph()
    r = p.add_run(f"{label}: ")
    r.bold = True
    p.add_run(str(value))


def _bullets(doc, items, style="List Bullet"):
    for it in items or []:
        doc.add_paragraph(str(it), style=style)


def _misconception_table(doc, rows, code_col=False):
    """Render the 3-column Misconception | Example Error | Correction Strategy
    table (with an optional leading Benchmark column for the topic-level view)."""
    if not rows:
        return
    headers = (["Benchmark"] if code_col else []) + \
        ["Misconception", "Example Error", "Correction Strategy"]
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Light Grid Accent 1"
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = h
    for m in rows:
        cells = table.add_row().cells
        vals = ([m.get("code", "")] if code_col else []) + [
            m.get("misconception", ""), m.get("example", ""), m.get("fix", "")]
        for i, v in enumerate(vals):
            cells[i].text = str(v)


def _exit_ticket_text(et) -> str:
    if isinstance(et, dict):
        prob, ans = et.get("problem", ""), et.get("answer", "")
        return f"{prob}  →  {ans}" if ans else prob
    return str(et or "")


def guide_to_docx(guide: dict) -> bytes:
    doc = Document()
    _add_logo(doc)
    _heading(doc, guide.get("title", "Collaborative Planning Guide"), 16)
    meta = doc.add_paragraph()
    m = meta.add_run(
        f"Grade {guide.get('grade_level','')} {guide.get('subject','')}  ·  "
        + ("AI-generated draft" if guide.get("ai_generated") else "Draft")
    )
    m.italic = True
    m.font.size = Pt(9)

    # Quick Facts
    qf = guide.get("quick_facts", {})
    if qf:
        _heading(doc, "Quick Facts", 13)
        table = doc.add_table(rows=0, cols=2)
        table.style = "Light Grid Accent 1"
        rows = [
            ("Time Frame", qf.get("time_frame", "")),
            ("Assessment Date", qf.get("assessment_date", "")),
            ("Topic Focus", qf.get("topic_focus", "")),
            ("Key Benchmarks", ", ".join(qf.get("key_benchmarks", []))),
            ("ALD Focus", qf.get("ald_focus", "")),
            ("MTR Practices", " · ".join(qf.get("mtr_practices", []))),
            ("Materials", ", ".join(qf.get("materials", []))),
        ]
        for k, v in rows:
            if not v:
                continue
            cells = table.add_row().cells
            cells[0].text = k
            cells[1].text = str(v)

    _label(doc, "Learning Goal", guide.get("learning_goal"))
    if guide.get("success_criteria"):
        _heading(doc, "Success Criteria", 12)
        _bullets(doc, guide["success_criteria"])

    if guide.get("benchmark_clarifications"):
        _heading(doc, "Benchmark Clarifications", 12)
        for c in guide["benchmark_clarifications"]:
            _label(doc, c.get("code", ""), c.get("description", ""))
            _bullets(doc, c.get("clarifications", []))

    if guide.get("common_misconceptions"):
        _heading(doc, "Common Misconceptions", 12)
        _misconception_table(doc, guide["common_misconceptions"], code_col=True)

    # Lessons
    for L in guide.get("lessons", []):
        doc.add_page_break()
        _heading(doc, f"Lesson {L.get('code','')} — {L.get('title','')}", 14)
        _label(doc, "Benchmarks", ", ".join(L.get("benchmarks", [])))
        _label(doc, "Focus", L.get("focus"))
        _label(doc, "Learning Goal (Student-Friendly)", L.get("learning_goal"))
        if L.get("success_criteria"):
            _heading(doc, "Success Criteria", 11)
            _bullets(doc, L["success_criteria"])
        _label(doc, "Example", L.get("success_example"))
        _label(doc, "Benchmark Clarification", L.get("benchmark_clarification"))
        _label(doc, "Example", L.get("benchmark_example"))
        _label(doc, "Sentence Frame", L.get("sentence_frame"))
        if L.get("misconceptions"):
            _heading(doc, "Common Misconceptions & Fixes", 11)
            _misconception_table(doc, L["misconceptions"])
        # ACES gradual release: Assemble (I Do) -> Connect (We Do) -> Explore
        # (Y'all Do, teams) -> Share (You Do, independent).
        if any(L.get(k) for k in ("activate_prior_knowledge", "i_do", "we_do",
                                  "explore_yall_do", "you_do")):
            _heading(doc, "Teaching Strategy — ACES Gradual Release", 11)
            _label(doc, "Activate Prior Knowledge", L.get("activate_prior_knowledge"))
            _label(doc, "ASSEMBLE · I Do (Teacher Models)", L.get("i_do"))
            _label(doc, "CONNECT · We Do (Guided Practice)", L.get("we_do"))
            _label(doc, "EXPLORE · Y'all Do (Collaborative Teams)", L.get("explore_yall_do"))
            _label(doc, "SHARE · You Do (Independent Practice)", L.get("you_do"))
        elif L.get("teaching_strategy"):
            _heading(doc, "Teaching Strategy (Step-by-Step)", 11)
            _bullets(doc, L["teaching_strategy"], style="List Number")
        cpa = L.get("cpa", {})
        if any(cpa.get(k) for k in ("concrete", "pictorial", "abstract")):
            _heading(doc, "CPA Model", 11)
            _label(doc, "Concrete", cpa.get("concrete"))
            _label(doc, "Pictorial", cpa.get("pictorial"))
            _label(doc, "Abstract", cpa.get("abstract"))
        # Achievement Level Descriptors — what each level looks like for this
        # benchmark, with Level 3 (on-grade, the goal) emphasized.
        ald = L.get("ald") or {}
        if any(ald.get(k) for k in ("level2", "level3", "level4", "level5")):
            _heading(doc, "Achievement Level Descriptors (ALD)", 11)
            rows = [("Level 2 — below", ald.get("level2")),
                    ("Level 3 — ON GRADE (goal)", ald.get("level3")),
                    ("Level 4 — above", ald.get("level4")),
                    ("Level 5 — mastery", ald.get("level5"))]
            for lbl, val in rows:
                if not val:
                    continue
                p = doc.add_paragraph(style="List Bullet")
                r = p.add_run(f"{lbl}: ")
                r.bold = True
                if "ON GRADE" in lbl:
                    r.font.color.rgb = RGBColor(0x1F, 0x7A, 0x1F)
                p.add_run(str(val))
        _label(doc, "Level 3 Proficiency Example (student voice)", L.get("level3_example"))
        if L.get("cfu"):
            _heading(doc, "Checks for Understanding (CFU)", 11)
            _bullets(doc, L["cfu"])
        _label(doc, "Exit Ticket", _exit_ticket_text(L.get("exit_ticket")))

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
