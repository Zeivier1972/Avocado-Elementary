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


def _phase(doc, header, phase):
    """Render one fully-scripted ACES phase: the problem, the teacher's spoken
    script, what the teacher does, the Concrete/Pictorial/Abstract for that
    problem, CUBS (Solo), and the look-fors. Tolerates the legacy string shape."""
    if not phase:
        return
    _heading(doc, header, 11)
    if isinstance(phase, str):
        doc.add_paragraph(phase)
        return
    if phase.get("structure"):
        _label(doc, "Collaborative structure", phase.get("structure"))
        _label(doc, "Each partner/group role", phase.get("roles"))
    _label(doc, "Problem worked", phase.get("problem"))
    say = phase.get("say")
    if say:
        p = doc.add_paragraph()
        p.add_run("Teacher says:").bold = True
        for line in (say if isinstance(say, list) else [say]):
            doc.add_paragraph(f"“{line}”", style="List Bullet")
    _label(doc, "Teacher does", phase.get("do"))
    _label(doc, "Concrete (manipulative)", phase.get("concrete"))
    _label(doc, "Pictorial (drawing)", phase.get("pictorial"))
    _label(doc, "Abstract (equation)", phase.get("abstract"))
    _label(doc, "CUBS on this problem", phase.get("cubs"))
    _label(doc, "Look for", phase.get("look_for"))


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
        if L.get("vocabulary") or L.get("vocabulary_integration"):
            _heading(doc, "Vocabulary (from the pacing guide)", 11)
            _label(doc, "Terms", ", ".join(L.get("vocabulary", [])))
            _label(doc, "How to integrate", L.get("vocabulary_integration"))
        if L.get("misconceptions"):
            _heading(doc, "Common Misconceptions & Fixes", 11)
            _misconception_table(doc, L["misconceptions"])
        # ACES gradual release: Assemble (I Do) -> Connect (We Do) -> Explore
        # (Y'all Do, collaborative pairs/groups of 4) -> Solo (You Do + CUBS).
        if any(L.get(k) for k in ("activate_prior_knowledge", "i_do", "we_do",
                                  "explore_yall_do", "you_do")):
            _heading(doc, "Teaching Strategy — ACES Gradual Release (Scripted)", 12)
            _label(doc, "Activate Prior Knowledge", L.get("activate_prior_knowledge"))
            _phase(doc, "ASSEMBLE · I Do (Teacher Models)", L.get("i_do"))
            _phase(doc, "CONNECT · We Do (Guided Practice)", L.get("we_do"))
            _phase(doc, "EXPLORE · Y'all Do (Collaborative — pairs or groups of 4)",
                   L.get("explore_yall_do"))
            _phase(doc, "SOLO · You Do (Independent Practice + CUBS)", L.get("you_do"))
            # Legacy top-level CUBS string only when You Do isn't a scripted phase.
            if not isinstance(L.get("you_do"), dict):
                _label(doc, "SOLO · Apply CUBS to the problem", L.get("cubs"))
        elif L.get("teaching_strategy"):
            _heading(doc, "Teaching Strategy (Step-by-Step)", 11)
            _bullets(doc, L["teaching_strategy"], style="List Number")
        # Lesson-level CPA only when phases aren't already scripted with their own
        # Concrete/Pictorial/Abstract (avoids duplicating it four times over).
        cpa = L.get("cpa", {})
        if not isinstance(L.get("i_do"), dict) and any(
                cpa.get(k) for k in ("concrete", "pictorial", "abstract")):
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
        l3 = L.get("level3_look_like") or {}
        if l3.get("problem"):
            _heading(doc, "What a Level 3 (On-Grade) Looks Like — This Lesson", 11)
            _label(doc, "Problem", l3.get("problem"))
            _label(doc, "Worked solution", l3.get("solution"))
            _label(doc, "Student explanation", l3.get("student_explanation"))
        else:
            _label(doc, "Level 3 Proficiency Example (student voice)",
                   L.get("level3_example"))
        if L.get("cfu"):
            _heading(doc, "Checks for Understanding (CFU)", 11)
            _bullets(doc, L["cfu"])
        _label(doc, "Exit Ticket", _exit_ticket_text(L.get("exit_ticket")))

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def coach_summary_to_docx(summary: dict, narrative: dict,
                          framework_lens: dict | None = None) -> bytes:
    """Render the one-page Coach Summary (essentials + how-to-present narrative +
    this week's coaching-framework lens) a coach uses to lead planning."""
    doc = Document()
    _add_logo(doc)
    _heading(doc, "Coach One-Pager", 16)
    meta = doc.add_paragraph()
    m = meta.add_run(
        f"Grade {summary.get('grade_level','')} {summary.get('subject','')}  ·  "
        f"{summary.get('title','')}"
        + (f"  ·  Assessment: {summary['assessment_date']}"
           if summary.get("assessment_date") else ""))
    m.italic = True
    m.font.size = Pt(9)

    if narrative.get("big_idea"):
        _heading(doc, "Big Idea — what teachers must understand", 13)
        doc.add_paragraph(str(narrative["big_idea"]))
        if narrative.get("why_it_matters"):
            _label(doc, "Why it matters", narrative["why_it_matters"])

    if narrative.get("talking_points"):
        _heading(doc, "How to present it (your talking points)", 12)
        _bullets(doc, narrative["talking_points"], style="List Number")

    # This week's coaching-framework lens, scripted to this topic.
    if framework_lens and framework_lens.get("content"):
        c = framework_lens["content"]
        _heading(doc, f"Coaching Lens — {framework_lens.get('component_name','')} "
                 f"({framework_lens.get('week_focus','')})", 12)
        if c.get("how_it_shows_up"):
            doc.add_paragraph(str(c["how_it_shows_up"]))
        if c.get("look_fors"):
            _label(doc, "Look-fors", "")
            _bullets(doc, c["look_fors"])
        if c.get("coaching_questions"):
            _label(doc, "Coaching questions", "")
            _bullets(doc, c["coaching_questions"])
        if c.get("teacher_talking_points"):
            _label(doc, "Say this in the meeting", "")
            _bullets(doc, c["teacher_talking_points"])

    if summary.get("strategies"):
        _heading(doc, "Strategies to reinforce", 12)
        for s in summary["strategies"]:
            p = doc.add_paragraph(style="List Bullet")
            r = p.add_run(f"{s['name']} — ")
            r.bold = True
            p.add_run(s["what"])

    if summary.get("vocabulary"):
        _heading(doc, "Vocabulary (from the pacing guide)", 12)
        doc.add_paragraph(" · ".join(summary["vocabulary"]))

    if summary.get("sentence_frames"):
        _heading(doc, "Sentence frames / stems", 12)
        _bullets(doc, summary["sentence_frames"])

    watch = narrative.get("watch_fors") or [m["misconception"] for m in summary.get("misconceptions", [])]
    if watch:
        _heading(doc, "Watch-fors (misconceptions to flag)", 12)
        _bullets(doc, watch)
    if summary.get("misconceptions"):
        _misconception_table(
            doc, [{"misconception": m["misconception"], "example": "", "fix": m["fix"]}
                  for m in summary["misconceptions"]])

    if summary.get("level3"):
        l3 = summary["level3"]
        _heading(doc, "What a Level 3 (on-grade) looks like", 12)
        _label(doc, "Problem", l3.get("problem"))
        _label(doc, "Solution", l3.get("solution"))
        _label(doc, "Student explanation", l3.get("student_explanation"))

    if summary.get("models"):
        _heading(doc, "Worked models — how to show it (so you can model it)", 12)
        for mdl in summary["models"]:
            p = doc.add_paragraph()
            r = p.add_run(f"Lesson {mdl.get('code','')} — {mdl.get('title','')}")
            r.bold = True
            _label(doc, "Model this problem", mdl.get("problem"))
            _label(doc, "Teacher move", mdl.get("teacher_move"))
            _label(doc, "Concrete (manipulative)", mdl.get("concrete"))
            _label(doc, "Pictorial (drawing)", mdl.get("pictorial"))
            _label(doc, "Abstract (equation)", mdl.get("abstract"))

    if summary.get("lessons"):
        _heading(doc, "Lessons at a glance", 12)
        table = doc.add_table(rows=1, cols=4)
        table.style = "Light Grid Accent 1"
        for i, h in enumerate(["#", "Learning goal", "Model this", "Exit ticket"]):
            table.rows[0].cells[i].text = h
        for L in summary["lessons"]:
            c = table.add_row().cells
            c[0].text = str(L.get("code", ""))
            c[1].text = str(L.get("learning_goal", "") or L.get("title", ""))
            c[2].text = str(L.get("model_focus", ""))
            c[3].text = str(L.get("exit", ""))

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
