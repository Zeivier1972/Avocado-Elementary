"""Render a Collaborative Planning Guide (the JSON produced by app.ai) into an
editable Word document, mirroring the district's planning-guide format."""
import io

from docx import Document
from docx.shared import Pt, RGBColor


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


def guide_to_docx(guide: dict) -> bytes:
    doc = Document()
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
        for m in guide["common_misconceptions"]:
            _label(doc, m.get("code", ""), m.get("note", ""))

    # Lessons
    for L in guide.get("lessons", []):
        doc.add_page_break()
        _heading(doc, f"Lesson {L.get('code','')} — {L.get('title','')}", 14)
        _label(doc, "Benchmarks", ", ".join(L.get("benchmarks", [])))
        _label(doc, "Focus", L.get("focus"))
        _label(doc, "Learning Goal", L.get("learning_goal"))
        if L.get("success_criteria"):
            _heading(doc, "Success Criteria", 11)
            _bullets(doc, L["success_criteria"])
        _label(doc, "Benchmark Clarification", L.get("benchmark_clarification"))
        if L.get("misconceptions"):
            _heading(doc, "Misconceptions & Fixes", 11)
            for mm in L["misconceptions"]:
                fix = f" → Fix: {mm['fix']}" if mm.get("fix") else ""
                doc.add_paragraph(f"{mm.get('misconception','')}{fix}", style="List Bullet")
        if L.get("teaching_strategy"):
            _heading(doc, "Teaching Strategy", 11)
            _bullets(doc, L["teaching_strategy"], style="List Number")
        cpa = L.get("cpa", {})
        if any(cpa.get(k) for k in ("concrete", "pictorial", "abstract")):
            _heading(doc, "CPA Model", 11)
            _label(doc, "Concrete", cpa.get("concrete"))
            _label(doc, "Pictorial", cpa.get("pictorial"))
            _label(doc, "Abstract", cpa.get("abstract"))
        _label(doc, "Level 3 Proficiency Example", L.get("level3_example"))
        if L.get("cfu"):
            _heading(doc, "Checks for Understanding", 11)
            _bullets(doc, L["cfu"])
        _label(doc, "You Do (Independent Practice)", L.get("you_do"))
        _label(doc, "Exit Ticket", L.get("exit_ticket"))

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
