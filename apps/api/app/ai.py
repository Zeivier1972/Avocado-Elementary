"""AI integration seam (docs/11-ai-integration-strategy.md).

Guardrails baked in:
- De-identified input only: callers pass attributes/flags, never student names.
- Grounded: the standard's own metadata is the context.
- Graceful degradation: with no provider configured, a structured, editable
  template is returned so the product is fully usable without AI.
- Human-in-the-loop: output is always a draft for the educator to edit.
"""
from __future__ import annotations

from app.core.config import settings

# The 7-day cycle from docs/03-feature-list.md.
CYCLE = {
    1: ("Error Analysis · Mini-Lesson · Guided Practice",
        "Analyze the most common error on {code}; teach the target explicitly; "
        "guided practice with immediate feedback."),
    2: ("Teacher Small Group · Independent Rotation",
        "Pull the group for targeted reteach of {code} while others rotate "
        "through independent practice."),
    3: ("Hands-on Activity · Vocabulary · Manipulatives",
        "Concrete/representational work on {code}; front-load key vocabulary."),
    4: ("Application · Word Problems · Reading Task",
        "Apply {code} in context — word problems / authentic reading task."),
    5: ("Collaborative Learning · Centers · Partner Work",
        "Peer practice on {code} via structured centers and partner talk."),
    6: ("Independent Practice · Progress Monitoring",
        "Independent practice on {code}; quick progress-monitoring check."),
    7: ("Reassessment · Growth Report · New Recommendation",
        "Reassess {code}; record growth; generate the next recommendation."),
}

ARTIFACTS = [
    "teacher_guide", "student_packet", "manipulative_list",
    "independent_practice", "center_activity", "homework",
    "quick_check", "exit_ticket", "progress_monitoring", "reassessment",
]

# Avocado Elementary's word-problem routine, integrated into each lesson.
CUBS_ROUTINE = (
    "CUBS Hero Routine (understand the story before choosing an operation): "
    "C — CIRCLE the important numbers/quantities and say what each represents "
    "(not label-only numbers); "
    "U — UNDERLINE exactly what to find, restate the question, name the unknown; "
    "B — BOX the words that show the relationship (joining, separating, comparing, "
    "grouping, sharing) — keywords are clues, not automatic rules; "
    "S — SOLVE & CHECK: choose a model/strategy/equation, solve and label, then "
    "check that the answer is reasonable and answers the question."
)


def generate_di_plan(standard: dict, group_size: int,
                     student_profiles: list[dict]) -> dict:
    """Return a 7-day DI plan. Uses the configured LLM when available, else a
    structured template. Never receives student names."""
    if settings.ai_provider == "anthropic" and settings.ai_api_key:
        plan = _llm_plan(standard, group_size, student_profiles)
        if plan:
            return plan
    return _template_plan(standard, group_size, student_profiles)


def _template_plan(standard: dict, group_size: int,
                   student_profiles: list[dict]) -> dict:
    code = standard["code"]
    ell = [p for p in student_profiles if (p.get("flags") or {}).get("ell")]
    scaffolds = []
    if ell:
        scaffolds.append("Language scaffolds / sentence frames for ELL students.")
    return {
        "generated_by": "template",
        "ai_generated": False,
        "standard": code,
        "group_size": group_size,
        "grounding": {"standard": code, "description": standard["description"]},
        "scaffolds": scaffolds,
        "days": [
            {
                "day": d,
                "focus": title,
                "plan": body.format(code=code),
                "artifacts": _artifacts_for_day(d),
            }
            for d, (title, body) in CYCLE.items()
        ],
        "note": "Editable draft — review before teaching (human-in-the-loop).",
    }


def _artifacts_for_day(day: int) -> list[str]:
    mapping = {
        1: ["teacher_guide", "student_packet"],
        2: ["teacher_guide", "independent_practice"],
        3: ["manipulative_list", "center_activity"],
        4: ["student_packet", "homework"],
        5: ["center_activity", "quick_check"],
        6: ["independent_practice", "progress_monitoring"],
        7: ["reassessment", "exit_ticket"],
    }
    return mapping.get(day, [])


def parse_pacing_schedule(pacing_text: str, year_start: int):
    """Read a pacing guide's day-by-day schedule out of its text: for each dated
    instructional day, the lesson/activity scheduled. Dates like 'August 13' are
    resolved to the school year (Aug-Dec -> year_start, Jan-Jul -> year_start+1).
    Returns (entries | None, reason). Entries: {date 'YYYY-MM-DD', lesson_code,
    title, kind}."""
    if not (settings.ai_provider == "anthropic" and settings.ai_api_key):
        return None, "AI not enabled — set AI_API_KEY to read dates from the pacing guide."
    try:
        import anthropic
    except ImportError:
        return None, "anthropic SDK not installed"
    try:
        client = anthropic.Anthropic(api_key=settings.ai_api_key)
        prompt = (
            "You are reading a school PACING GUIDE. Extract the day-by-day teaching "
            "schedule EXACTLY as written in the document. For every dated "
            "instructional day, output what is scheduled that day.\n\n"
            f"School year starts in August {year_start}. Resolve dates written like "
            f"'August 13' or '8/13' to ISO YYYY-MM-DD using this rule: months "
            f"August-December use {year_start}; January-July use {year_start + 1}. "
            "If the document already gives full dates, use them.\n\n"
            "For each day return an object: {\"date\":\"YYYY-MM-DD\", "
            "\"lesson_code\":\"e.g. 1.1 or blank\", \"title\":\"the lesson/activity "
            "as written\", \"kind\":\"lesson|review|assessment|note\"}. Use "
            "\"assessment\" for topic/chapter assessment days, \"review\" for review "
            "days. Only include days that have a real date in the document. Do not "
            "invent dates or lessons.\n\n"
            "PACING GUIDE:\n" + pacing_text.strip()[:14000]
        )
        with client.messages.stream(
            model=settings.ai_model, max_tokens=8000,
            system=("You output ONLY a single valid JSON array. No prose, no "
                    "markdown fences."),
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            msg = stream.get_final_message()
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        entries = _parse_json_array(text)
        if not entries:
            tail = text[-160:].replace("\n", " ") if text else "(empty)"
            return None, f"could not read a dated schedule from the guide. Ends with: …{tail}"
        # keep only rows with a plausible ISO date
        import re as _re
        clean = [e for e in entries
                 if isinstance(e, dict) and _re.match(r"\d{4}-\d{2}-\d{2}", str(e.get("date", "")))]
        return (clean, None) if clean else (None, "no dated rows found in the guide")
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:200]}"


def generate_guide_from_pacing(pacing_text: str, standards: list[dict],
                               grade: str, subject: str, topic_name: str) -> dict:
    """Generate a Collaborative Planning Guide grounded in the coach's UPLOADED
    pacing guide text (plus the B1G-M benchmark detail + FLDOE ALDs). The AI
    reads the pacing content and writes the ACES lesson-by-lesson guide."""
    std_by_code = {s["code"]: s for s in standards}
    clarifications = [
        {"code": s["code"], "description": s.get("description", ""),
         "clarifications": s.get("clarifications", [])}
        for s in standards
    ]
    misconceptions = []
    for s in standards:
        for row in _parse_misconceptions(s.get("misconceptions", "")):
            misconceptions.append({"code": s["code"], **row})
    base = {
        "title": f"Grade {grade} Collaborative Planning Guide — {topic_name}",
        "grade_level": grade, "subject": subject,
        "quick_facts": {
            "topic_focus": topic_name,
            "key_benchmarks": [s["code"] for s in standards],
            "ald_focus": "ALD Level 3 In-Class Practice",
        },
        "benchmark_clarifications": clarifications,
        "common_misconceptions": misconceptions,
        "from_document": True,
    }
    if settings.ai_provider == "anthropic" and settings.ai_api_key:
        lessons, err = _llm_lessons(
            {"grade_level": grade, "subject": subject, "topic_code": "",
             "name": topic_name, "learning_target": "", "success_criteria": [],
             "vocabulary": [], "mtr_practices": [], "materials": [], "lessons": []},
            standards, pacing_text=pacing_text)
        if lessons:
            for L in lessons:
                code = (L.get("benchmarks") or [""])[0]
                L["ald"] = std_by_code.get(code, {}).get("alds", {})
                _ensure_lesson_extras(L, [])
            base.update({"generated_by": settings.ai_model, "ai_generated": True,
                         "ai_status": "ok", "lessons": lessons,
                         "note": "AI-generated from your uploaded pacing guide — "
                                 "review with your team before teaching."})
            return base
        ai_status = f"AI unavailable — showing benchmark detail only. Reason: {err}"
    else:
        ai_status = ("AI not enabled — set AI_PROVIDER=anthropic and AI_API_KEY "
                     "to auto-write the lesson-by-lesson guide from your pacing document.")
    base.update({"generated_by": "template", "ai_generated": False,
                 "ai_status": ai_status, "lessons": [],
                 "note": "Benchmark clarifications, misconceptions, and ALDs are "
                         "shown; turn on the AI key to write the ACES lessons."})
    return base


def generate_planning_guide(topic: dict, standards: list[dict]) -> dict:
    """Generate a full lesson-by-lesson Collaborative Planning Guide matching the
    M-DCPS format (Quick Facts, benchmark clarifications, misconceptions, and a
    per-lesson breakdown with Teaching Strategy, CPA model, ALD Level 3 example,
    CFU, You Do, Exit Ticket). Grounded in the pacing guide + B1G-M content."""
    std_by_code = {s["code"]: s for s in standards}
    quick_facts = {
        "time_frame": topic.get("time_frame", ""),
        "assessment_date": topic.get("assessment_date", ""),
        "topic_focus": topic.get("topic_focus", ""),
        "key_benchmarks": [s["code"] for s in standards],
        "ald_focus": topic.get("ald_focus", "ALD Level 3 In-Class Practice"),
        "mtr_practices": topic.get("mtr_practices", []),
        "materials": topic.get("materials", []),
    }
    clarifications = [
        {"code": s["code"], "description": s.get("description", ""),
         "clarifications": s.get("clarifications", [])}
        for s in standards
    ]
    # Topic-level Common Misconceptions as the 3-column table (Misconception |
    # Example Error | Correction Strategy), grounded in each B1G-M standard.
    misconceptions = []
    for s in standards:
        for row in _parse_misconceptions(s.get("misconceptions", "")):
            misconceptions.append({"code": s["code"], **row})
    base = {
        "title": f"Grade {topic.get('grade_level','')} Collaborative Planning Guide — "
                 f"{topic['topic_code']}: {topic['name']}",
        "grade_level": topic.get("grade_level", ""),
        "subject": topic.get("subject", ""),
        "quick_facts": quick_facts,
        "learning_goal": topic.get("learning_target", ""),
        "success_criteria": topic.get("success_criteria", []),
        "benchmark_clarifications": clarifications,
        "common_misconceptions": misconceptions,
    }

    if settings.ai_provider == "anthropic" and settings.ai_api_key:
        lessons, err = _llm_lessons(topic, standards)
        if lessons:
            # Attach the AUTHORITATIVE FLDOE ALDs (don't let the model invent
            # them) so each lesson shows the official "what Level 3 looks like".
            for L in lessons:
                code = (L.get("benchmarks") or [""])[0]
                L["ald"] = std_by_code.get(code, {}).get("alds", {})
                _ensure_lesson_extras(L, topic.get("vocabulary", []))
            base.update({"generated_by": settings.ai_model, "ai_generated": True,
                         "ai_status": "ok", "lessons": lessons,
                         "note": "AI-generated draft — review with your team before teaching."})
            return base
        ai_status = f"AI unavailable — showing template. Reason: {err}"
    elif settings.ai_provider != "anthropic":
        ai_status = "AI not enabled (set AI_PROVIDER=anthropic and AI_API_KEY)."
    else:
        ai_status = "AI key missing (set AI_API_KEY)."

    # Template fallback: grounded skeleton from the pacing lesson outline.
    base.update({"generated_by": "template", "ai_generated": False,
                 "ai_status": ai_status,
                 "lessons": _template_lessons(topic, std_by_code),
                 "note": "Structured draft — add instructional detail with your team."})
    return base


def _one_pager_fallback(summary: dict) -> dict:
    """A useful coach narrative built straight from the guide when AI is off."""
    strat = ", ".join(s["name"] for s in summary.get("strategies", [])) or "the lesson routines"
    tp = [f"Open with the big idea: {summary.get('focus','the week’s focus')}."]
    if summary.get("strategies"):
        tp.append(f"Anchor teachers in {strat} — show one example of each in action.")
    if summary.get("vocabulary"):
        tp.append("Post and pre-teach the vocabulary; require it in student talk "
                  "using the sentence frames.")
    if summary.get("misconceptions"):
        tp.append("Name the top misconception up front and the exact fix, so "
                  "teachers plan for it.")
    tp.append("Point every lesson at the exit ticket — that's the daily proof.")
    return {
        "big_idea": summary.get("focus", ""),
        "why_it_matters": "These lessons build the on-grade (Level 3) skill the "
                          "benchmark is assessed on; keeping the strategies and "
                          "vocabulary consistent is what makes it stick.",
        "talking_points": tp,
        "watch_fors": [m["misconception"] for m in summary.get("misconceptions", [])][:3],
        "ai_generated": False,
    }


def coach_one_pager_narrative(summary: dict) -> dict:
    """A short coach-facing 'how to present this' narrative on top of the
    deterministic one-pager. One quick call; falls back to a built narrative."""
    if not (settings.ai_provider == "anthropic" and settings.ai_api_key):
        return _one_pager_fallback(summary)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ai_api_key)
    except Exception:
        return _one_pager_fallback(summary)
    strat = "; ".join(f"{s['name']}: {s['what']}" for s in summary.get("strategies", []))
    prompt = (
        "You are coaching a K-3 math coach on how to present ONE planning topic to "
        "teachers in a short PLC. Be specific and practical so the coach sounds "
        "expert. Return ONLY a JSON object:\n"
        '{"big_idea":"1-2 sentences: the single most important thing teachers must '
        'understand for this topic",'
        '"why_it_matters":"1-2 sentences tying it to on-grade (Level 3) proficiency",'
        '"talking_points":["4-6 short things the coach should say/do when presenting, '
        'in order"],'
        '"watch_fors":["3-4 pitfalls or misconceptions to flag to teachers"]}\n\n'
        f"TOPIC: Grade {summary.get('grade_level','')} {summary.get('subject','')} — "
        f"{summary.get('title','')}\n"
        f"Focus: {summary.get('focus','')}\n"
        f"Benchmarks: {[b['code'] for b in summary.get('benchmarks', [])]}\n"
        f"Strategies in the guide: {strat}\n"
        f"Vocabulary: {summary.get('vocabulary', [])}\n"
        f"Top misconceptions: {[m['misconception'] for m in summary.get('misconceptions', [])]}\n"
    )
    try:
        with client.messages.stream(
            model=settings.ai_model, max_tokens=1200,
            system="You output ONLY one valid JSON object, no prose or fences.",
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            msg = stream.get_final_message()
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        import json as _json
        import re as _re
        m = _re.search(r"\{.*\}", text, _re.S)
        data = _json.loads(m.group(0)) if m else None
        if isinstance(data, dict) and data.get("big_idea"):
            data["ai_generated"] = True
            return data
    except Exception:
        pass
    return _one_pager_fallback(summary)


def ask_assistant(message: str, history: list[dict], context: dict) -> dict:
    """The in-system Expert AI Coach. Grounded in the school's aggregate data;
    helps manage teachers/students/standards/pacing and drafts communications.
    Student data is aggregate-only (compliance, docs/00)."""
    system = (
        "You are the Avocado AI Coach — an expert instructional coach, data "
        "analyst, and assistant for a K-3 elementary school (Miami-Dade / Florida "
        "B.E.S.T.). You have a LIVE SNAPSHOT of this coach's whole system below: "
        "the school goal and progress, every teacher's standing, pacing, saved "
        "planning guides, the coach's own notes and follow-ups, and upcoming "
        "calendar dates. Answer the coach's questions directly FROM this snapshot "
        "— name specific teachers, grades, percentages, and dates when they are "
        "in the data. If something isn't in the snapshot, say so plainly and "
        "point to where in the app it lives (Reports, a teacher's page, Key "
        "Dates, Planning) rather than guessing. Be concise, practical, and "
        "action-oriented. Never invent individual student names or scores — "
        "student data here is aggregate/teacher-level by design; for a single "
        "student, direct the coach to that teacher's tracker. When asked, draft "
        "teacher emails with a clear subject line and a body ready to send.\n\n"
        f"TODAY: {context.get('today','')}   COACH: {context.get('coach','')}\n\n"
        f"LIVE SYSTEM SNAPSHOT:\n{_context_text(context)}"
    )
    if settings.ai_provider == "anthropic" and settings.ai_api_key:
        reply, err = _llm_chat(system, history, message)
        if reply:
            return {"reply": reply, "ai_generated": True}
        return {"reply": _assistant_fallback(context, err), "ai_generated": False}
    return {"reply": _assistant_fallback(context, None), "ai_generated": False}


def _context_text(ctx: dict) -> str:
    lines = [
        f"School: {ctx.get('school','')}",
        f"Students: {ctx.get('students',0)} | Teachers (with students): "
        f"{ctx.get('teachers',0)} | Classes: {ctx.get('classes',0)}",
        f"Students by grade: {ctx.get('by_grade', {})}",
    ]
    # School goal.
    if ctx.get("goal_statement"):
        lines.append(f"\nSCHOOL GOAL: {ctx['goal_statement']}")
        lines.append(f"School-wide meeting goal: {ctx.get('goal_school_pct')}%")
        if ctx.get("goal_by_grade"):
            lines.append(f"Meeting goal by grade: {ctx['goal_by_grade']}")
        if ctx.get("fast_math_by_grade"):
            lines.append(f"FAST Math % Level 3+ by grade/period: {ctx['fast_math_by_grade']}")
        if ctx.get("iready_math_by_grade"):
            lines.append(f"i-Ready Math % Level 3+ by grade/period: {ctx['iready_math_by_grade']}")
    # Teachers.
    td = ctx.get("teachers_detail") or []
    if td:
        lines.append("\nTEACHERS (name · grades · #students · % at Level 3+ FAST Math):")
        for t in td:
            grades = ",".join(t.get("grades", []))
            pct = t.get("pct_level_3_plus")
            pct_s = f"{pct}%" if pct is not None else "no data"
            lines.append(f"  - {t['name']} · G{grades} · {t.get('students',0)} · {pct_s}")
    # Coaching notes / follow-ups.
    fu = ctx.get("open_followups") or []
    if fu:
        lines.append("\nOPEN FOLLOW-UPS (coach's next steps):")
        for f in fu:
            due = f" (due {f['due']}{', OVERDUE' if f.get('overdue') else ''})" if f.get("due") else ""
            lines.append(f"  - {f['teacher']}: {f['task']}{due}")
    fa = ctx.get("focus_areas") or []
    if fa:
        lines.append("\nFOCUS AREAS logged per teacher:")
        for f in fa:
            lines.append(f"  - {f['teacher']}: {f['focus']}")
    # Pacing & guides.
    if ctx.get("pacing_topics"):
        lines.append("\nPACING TOPICS: " + "; ".join(ctx["pacing_topics"]))
    if ctx.get("saved_guides_by_grade"):
        lines.append(f"Saved planning guides by grade: {ctx['saved_guides_by_grade']}")
    if ctx.get("standards_count"):
        lines.append(f"Standards loaded: {ctx['standards_count']}")
    # Math + Math-DI schedule.
    ms = ctx.get("math_schedule") or []
    if ms:
        lines.append("\nMATH & MATH-DI SCHEDULE (Math-DI runs during Science/Social "
                     "Studies time):")
        for s in ms:
            tag = " (ASD)" if s.get("program") == "ASD" else ""
            lines.append(
                f"  - G{s['grade']} Rm {s['room']} {s['teacher']}{tag}: "
                f"Math {', '.join(s['math_times']) or '—'}; "
                f"DI window {', '.join(s['di_windows']) or '—'}")
    pbg = ctx.get("planning_by_grade") or {}
    if pbg:
        lines.append("\nGRADE-LEVEL PLANNING TIMES (when the math team is free): "
                     + "; ".join(f"G{g}: {', '.join(v)}" for g, v in sorted(pbg.items())))
    fw = ctx.get("framework") or {}
    if fw.get("this_week"):
        tw = fw["this_week"]
        pf = fw.get("planning_for") or tw
        lines.append(
            f"\nFRAMEWORK OF EFFECTIVE INSTRUCTION. Teachers are currently teaching "
            f"week {tw['week']} (lens: {tw['component_name']} — {tw['focus']}). "
            f"IMPORTANT: the coach plans a WEEK AHEAD — this week's planning "
            f"meetings are about NEXT week (week {pf['week']}, lens: "
            f"{pf['component_name']} — {pf['focus']}; {pf['why']}). So when helping "
            "the coach prepare for a planning meeting, lead with NEXT week's lens "
            "and next week's lessons, and be the expert on it. The six components: "
            + "; ".join(f"{c['name']} — {c['essence']}" for c in fw.get("components", [])))
    cm = ctx.get("collab_meetings") or {}
    if cm.get("this_week"):
        lines.append(
            f"\nCOLLABORATIVE PLANNING MEETINGS this week (rotation side "
            f"{cm.get('current_week','?')}): "
            + "; ".join(
                f"{m['day']} {m['time']} G{m['grade']} {m['group']}"
                + (f" (host {m['host']})" if m.get('host') else "")
                for m in cm["this_week"]))
    # Upcoming dates.
    ud = ctx.get("upcoming_dates") or []
    if ud:
        lines.append("\nUPCOMING KEY DATES:")
        for d in ud:
            window = f"–{d['end_date']}" if d.get("end_date") else ""
            when = "now open" if d.get("active") else (
                f"in {d['days_until']}d" if d.get("days_until") is not None else "")
            grade = f" [{d['grade']}]" if d.get("grade") else ""
            lines.append(f"  - {d['date']}{window} {d['title']}{grade} ({when})")
    return "\n".join(lines)


def _assistant_fallback(ctx: dict, err: str | None) -> str:
    note = f" (AI unavailable: {err})" if err else ""
    return (
        "I'm the Avocado AI Coach, but live AI responses aren't enabled right "
        f"now{note}. Here's what I can see in your school: "
        f"{ctx.get('students',0)} students, {ctx.get('teachers',0)} teachers, "
        f"{ctx.get('classes',0)} classes across grades "
        f"{', '.join(ctx.get('by_grade', {}).keys()) or 'none loaded'}. "
        "Once the AI key is active I can analyze this, plan with you, and draft "
        "teacher communications."
    )


def _llm_chat(system: str, history: list[dict], message: str):
    try:
        import anthropic
    except ImportError:
        return None, "anthropic SDK not installed"
    try:
        client = anthropic.Anthropic(api_key=settings.ai_api_key)
        msgs = []
        for h in (history or [])[-10:]:
            role = "assistant" if h.get("role") == "assistant" else "user"
            msgs.append({"role": role, "content": str(h.get("content", ""))[:4000]})
        msgs.append({"role": "user", "content": message[:4000]})
        resp = client.messages.create(
            model=settings.ai_model, max_tokens=1500, system=system, messages=msgs,
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        return text.strip(), None
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:200]}"


def ai_diagnostics() -> dict:
    """Report AI configuration and attempt a minimal live call for diagnosis."""
    out = {
        "provider": settings.ai_provider,
        "model": settings.ai_model,
        "key_present": bool(settings.ai_api_key),
        "sdk_installed": False,
        "test_call": "not_attempted",
    }
    try:
        import anthropic
        out["sdk_installed"] = True
        out["sdk_version"] = getattr(anthropic, "__version__", "?")
    except ImportError:
        out["test_call"] = "anthropic SDK not installed"
        return out
    if settings.ai_provider != "anthropic" or not settings.ai_api_key:
        out["test_call"] = "skipped (provider/key not configured)"
        return out
    try:
        client = anthropic.Anthropic(api_key=settings.ai_api_key)
        msg = client.messages.create(
            model=settings.ai_model, max_tokens=16,
            messages=[{"role": "user", "content": "Reply with the word OK."}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        out["test_call"] = "ok"
        out["reply"] = text.strip()[:40]
    except Exception as e:
        out["test_call"] = "error"
        out["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    return out


def _split_example(text: str):
    """Pull a worked 'example error' out of a misconception sentence — usually a
    parenthetical like '(says the 6 in 3,674 is \"6\")'. Returns (statement,
    example) to fill the guide's Misconception | Example | Correction columns."""
    import re as _re
    m = _re.search(r"\(([^)]*)\)", text)
    if m and any(ch.isdigit() for ch in m.group(1)):
        example = m.group(1).strip()
        statement = _re.sub(r"\s*\([^)]*\)", "", text).strip()
        return statement, example
    return text.strip(), ""


def _parse_misconceptions(raw: str) -> list[dict]:
    """Turn a B1G-M misconception string ('... Fix: ... Next mistake. Fix: ...')
    into structured {misconception, example, fix} rows — the 3-column
    Misconception | Example Error | Correction Strategy table in the guide."""
    import re as _re
    if not raw:
        return []
    rows = []
    parts = _re.split(r"\bFix:\s*", raw)
    lead = parts[0].strip()
    for i in range(1, len(parts)):
        chunk = parts[i].strip()
        if i < len(parts) - 1:
            m = _re.match(r"(.*?[.!?])\s+(.*)$", chunk, _re.S)
            if m:
                fix, nxt = m.group(1).strip(), m.group(2).strip()
            else:
                fix, nxt = chunk, ""
        else:
            fix, nxt = chunk, ""
        if lead:
            statement, example = _split_example(lead)
            rows.append({"misconception": statement, "example": example, "fix": fix})
        lead = nxt
    if not rows and raw.strip():
        statement, example = _split_example(raw.strip())
        rows.append({"misconception": statement, "example": example, "fix": ""})
    return rows


_VOCAB_INTEGRATION_DEFAULT = (
    "Add these terms to the math word wall with a student-friendly definition and a "
    "picture/model. Introduce them during Assemble (I Do), use them in the sentence "
    "frame during Connect/Explore, and require students to use them when they explain "
    "their reasoning (MTR 4.1)."
)
_CUBS_DEFAULT = (
    "On today's Solo problem, use CUBS: Circle the numbers and say what each represents, "
    "Underline the question and name the unknown, Box the relationship words (joining, "
    "separating, comparing, grouping, sharing), then Solve & Check that the answer is "
    "reasonable — understand the story before choosing an operation."
)


def _ensure_lesson_extras(lesson: dict, topic_vocab: list) -> dict:
    """Guarantee vocabulary, its integration, and the CUBS strategy on a lesson —
    used to backfill AI-generated lessons when the model omits them, so every
    lesson always shows vocabulary + CUBS."""
    if not lesson.get("vocabulary"):
        lesson["vocabulary"] = (topic_vocab or [])[:6]
    if not lesson.get("vocabulary_integration"):
        lesson["vocabulary_integration"] = _VOCAB_INTEGRATION_DEFAULT
    # CUBS now lives inside the Solo (You Do) phase; keep a top-level copy for
    # older saved-guide renderers and backfill the phase if the model omitted it.
    yd = lesson.get("you_do")
    if isinstance(yd, dict) and not yd.get("cubs"):
        yd["cubs"] = lesson.get("cubs") or _CUBS_DEFAULT
    if not lesson.get("cubs"):
        lesson["cubs"] = (yd.get("cubs") if isinstance(yd, dict) else None) or _CUBS_DEFAULT
    # Guarantee a specific "what Level 3 looks like" block on every lesson.
    l3 = lesson.get("level3_look_like")
    if not (isinstance(l3, dict) and l3.get("problem")):
        lesson["level3_look_like"] = {
            "problem": "an on-grade problem for this benchmark",
            "solution": "the fully worked solution with the answer",
            "student_explanation": lesson.get("level3_example")
            or "A Level 3 student solves it independently and explains the reasoning "
               "using the lesson vocabulary.",
        }
    return lesson


def _as_phase(val, *, problem, say, do, concrete, pictorial, abstract, **extra):
    """Coerce an authored ACES-phase value into the scripted phase object shape.
    Accepts a ready-made dict, a legacy string (kept as the teacher script), or
    nothing (falls back to the provided scaffold)."""
    base = {"problem": problem, "say": say if isinstance(say, list) else [say],
            "do": do, "concrete": concrete, "pictorial": pictorial,
            "abstract": abstract, **extra}
    if isinstance(val, dict):
        for k, v in val.items():
            if v not in (None, "", [], {}):
                base[k] = v
        return base
    if isinstance(val, str) and val.strip():
        base["say"] = [val.strip()]
        return base
    return base


def _template_lessons(topic: dict, std_by_code: dict) -> list[dict]:
    """Build the per-lesson breakdown. Prefer lesson-specific content authored in
    the pacing guide (activate_prior_knowledge, i_do, we_do, cfu, you_do,
    exit_ticket, cpa, level3_example, misconceptions...); only synthesize a
    generic scaffold for whatever a lesson leaves blank. This keeps every lesson
    distinct even when the LLM is unavailable, instead of repeating one template."""
    vocab = topic.get("vocabulary", [])
    materials = topic.get("materials", [])
    conc = ", ".join(materials[:3]) if materials else "base-ten blocks / manipulatives"
    out = []
    for L in topic.get("lessons", []):
        title = L.get("title", "")
        focus = L.get("focus", "")
        codes = L.get("benchmarks") or []
        s = std_by_code.get(codes[0], {}) if codes else {}
        clar = s.get("clarifications") or []
        pre = s.get("prerequisites") or []

        def pick(key, default):
            v = L.get(key)
            return v if v not in (None, "", [], {}) else default

        skill = title.lower() or "the skill"
        c_conc = f"Use {conc} to build/represent {skill}."
        c_pict = "Draw a place-value chart, number line, array, or bar model to represent it."
        c_abst = "Record the matching equation with numbers and symbols."
        activate = pick("activate_prior_knowledge",
            f"Review prerequisite skills ({', '.join(pre) if pre else 'earlier-grade foundations'}) "
            "and introduce vocabulary: " + (", ".join(vocab[:4]) if vocab else "key terms") + ".")
        # ACES phases as scripted objects (Assemble → Connect → Explore → Solo).
        i_do = _as_phase(L.get("i_do"),
            problem=f"a worked example of {skill}",
            say=[f"Watch how I {skill}. First I…", "I'll think out loud so you hear my reasoning."],
            do=f"Model {skill} step by step with {conc}; write each step where students can see it.",
            concrete=c_conc, pictorial=c_pict, abstract=c_abst,
            look_for="Students track the steps and can name what I did first.")
        we_do = _as_phase(L.get("we_do"),
            problem=f"a second example of {skill} (different numbers)",
            say=["Let's do this one together — what should we do first?",
                 "Tell your partner the next step, then we'll check."],
            do="Guided practice on mini-whiteboards with immediate feedback; students explain their reasoning (MTR 4.1).",
            concrete=c_conc, pictorial=c_pict, abstract=c_abst,
            look_for="Most students hold up a correct step and can justify it.")
        # Explore = Y'all Do — collaborative team practice (teacher observes/supports).
        explore = _as_phase(L.get("explore_yall_do"),
            structure="Rally Coach (pairs) or Numbered Heads Together (groups of 4)",
            roles="Partner A solves and explains aloud while Partner B coaches and checks; then swap. "
                  "In groups of 4, each member solves one, then the team compares and agrees on the answer.",
            problem=f"a shared {skill} task (different numbers again)",
            say=[f"With your team, apply {skill} to this task.",
                 "Use the sentence frame when you explain your thinking."],
            do="Circulate, listen for reasoning, and support teams that are stuck.",
            concrete=c_conc, pictorial=c_pict, abstract=c_abst,
            look_for="Every student takes a turn and explains using the vocabulary.")
        you_do = _as_phase(L.get("you_do"),
            problem=f"an independent {skill} word problem (different numbers again)",
            say=["Now you'll try one on your own.", "Use CUBS to understand the story before you solve."],
            cubs=pick("cubs", _CUBS_DEFAULT),
            do="Students work independently (3–5 problems); pull a small group for reteach.",
            concrete=c_conc, pictorial=c_pict, abstract=c_abst,
            look_for="Correct answer, labeled, with a Level-3 explanation.")
        cfu = pick("cfu", [
            "Quick check on mini-whiteboards.",
            "Ask a 'why' question to surface reasoning, not just the answer.",
        ])
        exit_ticket = pick("exit_ticket",
            "One problem targeting today's benchmark — score ≥69% = green.")
        cpa = pick("cpa", {"concrete": c_conc, "pictorial": c_pict, "abstract": c_abst})
        # "What a Level 3 looks like" for THIS lesson — a specific worked problem.
        _l3 = L.get("level3_look_like")
        if isinstance(_l3, dict) and _l3.get("problem"):
            level3_look = _l3
        else:
            level3_look = {
                "problem": f"an on-grade {skill} problem",
                "solution": "the fully worked solution with the answer",
                "student_explanation":
                    "A Level 3 student solves it independently and explains the reasoning "
                    "using the lesson vocabulary.",
            }
        level3 = pick("level3_example", level3_look.get("student_explanation", ""))
        # Vocabulary FROM the pacing guide (lesson-specific if authored, else the
        # topic's terms), plus how to teach it and how CUBS applies this lesson.
        lesson_vocab = pick("vocabulary", vocab[:6])
        vocab_integration = pick("vocabulary_integration",
            "Add these terms to the math word wall with a student-friendly definition "
            "and a picture/model. Introduce them during Assemble (I Do), use them in the "
            "sentence frame during Connect/Explore, and require students to use them when "
            "they explain their reasoning (MTR 4.1).")
        cubs = pick("cubs", _CUBS_DEFAULT)
        misc = pick("misconceptions", _parse_misconceptions(s.get("misconceptions", "")))
        crit = pick("success_criteria", ([focus] if focus else []) + clar[:2])
        # Back-compat numbered strategy, assembled from the ACES phases.
        def _phase_line(p):
            if isinstance(p, dict):
                say = " ".join(p.get("say", [])) if isinstance(p.get("say"), list) else str(p.get("say", ""))
                return (p.get("problem", "") + " — " + say).strip(" —") or p.get("do", "")
            return str(p)
        strategy = pick("teaching_strategy", [
            f"Activate Prior Knowledge — {activate}",
            f"Assemble (I Do) — {_phase_line(i_do)}",
            f"Connect (We Do) — {_phase_line(we_do)}",
            f"Explore (Y'all Do) — {_phase_line(explore)}",
            f"Solo (You Do) — {_phase_line(you_do)}",
        ])

        out.append({
            "code": L.get("code", ""), "title": title,
            "benchmarks": codes, "focus": focus,
            "learning_goal": pick("learning_goal",
                f"I can {title[:1].lower() + title[1:]}." if title else ""),
            "success_criteria": crit,
            "success_example": L.get("success_example", ""),
            "benchmark_clarification": pick("benchmark_clarification",
                " ".join(clar) or s.get("description", "")),
            "benchmark_example": L.get("benchmark_example", ""),
            "sentence_frame": L.get("sentence_frame", ""),
            # Official FLDOE Achievement Level Descriptors for this benchmark —
            # "what a Level 3 (on-grade) looks like", plus 2/4/5 for the progression.
            "ald": s.get("alds", {}),
            "misconceptions": misc,
            "vocabulary": lesson_vocab,
            "vocabulary_integration": vocab_integration,
            "cubs": cubs,
            "activate_prior_knowledge": activate,
            "i_do": i_do,
            "we_do": we_do,
            "explore_yall_do": explore,
            "teaching_strategy": strategy,
            "cpa": cpa,
            "level3_example": level3,
            "level3_look_like": level3_look,
            "cfu": cfu,
            "you_do": you_do,
            "exit_ticket": exit_ticket,
        })
    return out


def _std_context(standards: list[dict]) -> str:
    def _ald_line(s):
        a = s.get("alds") or {}
        if not a:
            return ""
        parts = []
        for lvl, lbl in (("level2", "L2 below"), ("level3", "L3 ON-GRADE"),
                         ("level4", "L4 above"), ("level5", "L5 mastery")):
            if a.get(lvl):
                parts.append(f"{lbl}: {a[lvl]}")
        return "\n    Achievement Level Descriptors — " + " | ".join(parts) if parts else ""
    return "\n".join(
        f"- {s['code']}: {s.get('description','')}"
        + (f"\n    Clarifications: {' | '.join(s.get('clarifications', []))}" if s.get('clarifications') else "")
        + (f"\n    Common misconceptions: {s['misconceptions']}" if s.get('misconceptions') else "")
        + (f"\n    Instructional strategies (B1G-M): {s['strategies']}" if s.get('strategies') else "")
        + _ald_line(s)
        for s in standards
    )


# Each ACES phase is a fully-scripted object: the exact problem worked, the words
# the teacher SAYS (verbatim think-aloud / questions), what the teacher DOES, and
# the Concrete→Pictorial→Abstract for THAT phase's problem. A brand-new teacher
# can read it and deliver it. All fields must be grade-appropriate for the header.
_PHASE_SHAPE = (
    '{"problem":"the exact problem worked in THIS phase (real numbers) — a DIFFERENT '
    'problem from every other phase",'
    '"say":["the actual words the teacher speaks, line 1 (a real think-aloud or real '
    'question at an elementary reading level)","line 2","line 3"],'
    '"do":"what the teacher physically does while saying it (where to write, what to '
    'point to, how students respond — whiteboards, turn-and-talk, choral)",'
    '"concrete":"the NAMED manipulative and the exact hands-on steps for THIS problem '
    '(base-ten blocks 🟦🟩🟨⬜ / two-color counters / connecting cubes / fraction tiles / '
    'array tiles / number line — pick what fits the grade & benchmark)",'
    '"pictorial":"the exact labeled drawing to make (place-value chart / number line / '
    'array / bar model with the numbers filled in)",'
    '"abstract":"the exact equation or notation, e.g. 3,476 = 3,000 + 400 + 70 + 6",'
    '"look_for":"what a correct student response sounds/looks like in this phase"}'
)

_LESSON_SCHEMA = (
    '[{"code":"7.1","title":"...","benchmarks":["MA.3..."],"focus":"...",'
    '"learning_goal":"I can ... (student-friendly)",'
    '"success_criteria":["observable behavior 1","observable behavior 2"],'
    '"success_example":"a worked example that shows mastery (e.g. In 4,582: 4=4,000 ...)",'
    '"benchmark_clarification":"what students must understand",'
    '"benchmark_example":"a specific worked numeric example",'
    '"sentence_frame":"The __ is in the __ place, so it means __.",'
    '"misconceptions":[{"misconception":"...","example":"specific wrong answer a student gives","fix":"correction strategy"}],'
    '"vocabulary":["the pacing-guide vocabulary terms used in THIS lesson"],'
    '"vocabulary_integration":"specifically how to teach these exact terms in THIS lesson (kid-friendly definition, where in the lesson they are introduced/used, the sentence frame)",'
    '"activate_prior_knowledge":"a specific warm-up (with its actual review problem) that connects to THIS lesson",'
    f'"i_do":{_PHASE_SHAPE},'
    f'"we_do":{_PHASE_SHAPE},'
    '"explore_yall_do":{"structure":"the NAMED collaborative structure (e.g. Rally Coach in pairs, Numbered Heads Together in groups of 4)",'
    '"roles":"exactly what each partner/member does, step by step",'
    '"problem":"the shared task with real numbers (DIFFERENT from every other phase)",'
    '"say":["the exact launch directions the teacher gives","the sentence frame students must use"],'
    '"do":"what the teacher watches for and how to support while circulating",'
    '"concrete":"named manipulative + steps","pictorial":"the labeled drawing","abstract":"the equation","look_for":"what mastery looks like here"},'
    '"you_do":{"problem":"the independent word problem with real numbers (DIFFERENT from every other phase)",'
    '"say":["how the teacher sets up independent work","the CUBS reminder in kid words"],'
    '"cubs":"walk THIS problem through CUBS with the ACTUAL numbers: what to Circle, Underline, Box, and how to Solve & Check",'
    '"do":"what the teacher does (e.g. pull a small group to reteach ...)",'
    '"concrete":"named manipulative + steps","pictorial":"the labeled drawing","abstract":"the equation","look_for":"the correct answer + what a Level-3 explanation sounds like"},'
    '"level3_look_like":{"problem":"the SPECIFIC on-grade problem a Level 3 (proficient) student solves for THIS lesson — real numbers, not vague","solution":"the fully worked solution with the answer","student_explanation":"the first-person reasoning a Level-3 student gives, using the lesson vocabulary"},'
    '"cfu":["specific check problem 1","specific check problem 2"],'
    '"exit_ticket":{"problem":"one problem","answer":"the answer"}}]'
)

_LESSON_RULES = (
    "You are SCRIPTING a lesson that a BRAND-NEW elementary teacher will read and "
    "deliver word-for-word. NO SHORTCUTS, no vague or generic filler.\n"
    "Every ACES phase — i_do (ASSEMBLE/model), we_do (CONNECT/guided), explore_yall_do "
    "(EXPLORE/collaborative), you_do (SOLO/independent) — MUST contain:\n"
    "  1) 'problem' — the exact problem worked in that phase, and a DIFFERENT problem "
    "in every phase (never reuse a number or problem within the lesson);\n"
    "  2) 'say' — the ACTUAL words the teacher speaks (a real think-aloud and real "
    "questions), 2–4 short lines at an elementary reading level;\n"
    "  3) 'do' — what the teacher physically does;\n"
    "  4) 'concrete' / 'pictorial' / 'abstract' for THAT phase's problem: Concrete = "
    "the NAMED manipulative (base-ten blocks 🟦🟩🟨⬜, two-color counters, connecting "
    "cubes, fraction tiles, arrays, number line — choose what fits the grade & "
    "benchmark) with exact steps; Pictorial = the exact labeled drawing; Abstract = "
    "the exact equation.\n"
    "Use REAL, grade-appropriate examples like a math textbook would: small whole "
    "numbers for K–1, larger/multi-step for 2–3, fractions where the benchmark calls "
    "for it. Keep every number and word appropriate for the grade in the header.\n"
    "- explore_yall_do: NAME the collaborative structure (Rally Coach / Pairs Check in "
    "pairs; Numbered Heads Together / Round Robin / Team Huddle in groups of 4) and give "
    "each partner/member's exact role.\n"
    "- you_do: include CUBS walked through THIS problem's actual numbers.\n"
    "- level3_look_like: a SPECIFIC worked problem (real numbers) showing exactly what "
    "a Level 3 (proficient) student does for THIS lesson — never vague.\n"
    "- vocabulary from the pacing guide + how to teach those exact terms here; a "
    "3-column misconceptions table (misconception, a real example error, the fix).\n"
    "Do not invent standards or student data. Output ONLY the JSON array."
)


def _llm_json(client, prompt: str, system: str, max_tokens: int):
    """One streamed call returning (parsed_json_array | None, reason)."""
    with client.messages.stream(
        model=settings.ai_model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        msg = stream.get_final_message()
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    stop = getattr(msg, "stop_reason", "")
    arr = _parse_json_array(text)
    if arr is not None:
        return arr, None
    tail = text[-140:].replace("\n", " ") if text else "(empty response)"
    note = " (hit token limit)" if stop == "max_tokens" else ""
    return None, f"unparseable JSON{note}. Ends with: …{tail}"


def _lesson_skeleton(client, topic, std_ctx, pacing_text):
    """Small call: the lesson list only (code/title/benchmarks/focus)."""
    if pacing_text and pacing_text.strip():
        source = ("From the UPLOADED PACING GUIDE below, list EVERY lesson/day in "
                  "order — however many there are.\n\nPACING GUIDE:\n"
                  + pacing_text.strip()[:30000])
    else:
        source = "Design a logical sequence of 5-7 lessons covering the benchmarks below."
    prompt = (
        f"Grade {topic.get('grade_level')} {topic.get('subject')} — "
        f"{topic.get('topic_code','')}: {topic.get('name','')}\n"
        f"Benchmarks:\n{std_ctx}\n\n{source}\n\n"
        "Return ONLY a JSON array of lesson stubs: "
        '[{"code":"1.1","title":"...","benchmarks":["MA.3..."],"focus":"one line"}]'
    )
    arr, _ = _llm_json(client, prompt,
                       "You output ONLY a JSON array, no prose or fences.", 3000)
    if not arr:
        return []
    out = []
    for L in arr:
        if isinstance(L, dict) and (L.get("title") or L.get("code")):
            out.append({"code": str(L.get("code", "")), "title": str(L.get("title", "")),
                        "benchmarks": L.get("benchmarks", []), "focus": str(L.get("focus", ""))})
    return out


def _lesson_detail(client, topic, std_ctx, batch, pacing_text):
    """Expand a small batch of lesson stubs into full ACES detail (bounded call)."""
    stub_txt = "\n".join(
        f"- Lesson {L.get('code')}: {L.get('title')} "
        f"(benchmarks {', '.join(L.get('benchmarks', []))}; focus: {L.get('focus','')})"
        for L in batch
    )
    pacing_block = ("\n\nUse this pacing-guide content for these lessons:\n"
                    + pacing_text.strip()[:20000]) if pacing_text else ""
    prompt = (
        "You are an elementary math instructional coach writing a Collaborative "
        "Planning Guide. Expand EXACTLY these lessons (in order) into full detail.\n\n"
        f"Grade {topic.get('grade_level')} {topic.get('subject')} — "
        f"{topic.get('topic_code','')}: {topic.get('name','')}\n"
        f"Pacing-guide vocabulary: {topic.get('vocabulary', [])}\n"
        f"Materials: {topic.get('materials', [])}\n\n"
        f"{CUBS_ROUTINE}\n\n"
        f"Benchmarks (B1G-M detail + ALDs — use these):\n{std_ctx}\n\n"
        f"Lessons to expand:\n{stub_txt}{pacing_block}\n\n"
        f"{_LESSON_RULES}\n\n"
        f"Return ONLY a JSON array (one object per lesson above) matching:\n{_LESSON_SCHEMA}"
    )
    return _llm_json(
        client, prompt,
        "You output ONLY a valid JSON array, no prose or fences. Finish every "
        "object completely — never stop mid-object.", 16000)


def _llm_lessons(topic: dict, standards: list[dict], pacing_text: str | None = None):
    """Generate the per-lesson breakdown in two stages — a small skeleton call to
    get the lesson list, then bounded batches for full detail — so a long guide is
    never truncated. Any batch that fails is template-filled so no lesson is lost.
    Returns (lessons | None, error_reason | None)."""
    try:
        import anthropic
    except ImportError:
        return None, "anthropic SDK not installed"
    try:
        client = anthropic.Anthropic(api_key=settings.ai_api_key)
        std_ctx = _std_context(standards)
        std_by_code = {s["code"]: s for s in standards}

        skeleton = _lesson_skeleton(client, topic, std_ctx, pacing_text)
        if not skeleton:
            skeleton = [
                {"code": L.get("code", ""), "title": L.get("title", ""),
                 "benchmarks": L.get("benchmarks", []), "focus": L.get("focus", "")}
                for L in (topic.get("lessons") or [])
            ]
        if not skeleton:
            return None, "could not determine the lesson list from the pacing guide"

        # Two fully-scripted lessons per call: small enough that a richly-scripted
        # batch never truncates, few enough calls to keep generation responsive.
        out, errs = [], []
        for i in range(0, len(skeleton), 2):
            batch = skeleton[i:i + 2]
            detail, err = _lesson_detail(client, topic, std_ctx, batch, pacing_text)
            if detail:
                out.extend(detail)
            else:
                errs.append(err or "batch failed")
                mini = dict(topic)
                mini["lessons"] = batch
                out.extend(_template_lessons(mini, std_by_code))
        return (out, None) if out else (None, "; ".join(errs) or "no lessons generated")
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:200]}"


def _parse_json_array(text: str):
    """Extract a JSON array from a model reply, tolerant of prose, markdown
    fences, and truncation (salvages the complete objects before a cut-off)."""
    import json as _json
    import re as _re
    if not text:
        return None
    t = text.strip()
    fence = _re.search(r"```(?:json)?\s*(.*?)```", t, _re.S)
    if fence:
        t = fence.group(1).strip()
    start = t.find("[")
    if start == -1:
        return None
    t = t[start:]
    try:
        return _json.loads(t)
    except Exception:
        pass
    end = t.rfind("]")
    if end != -1:
        try:
            return _json.loads(t[:end + 1])
        except Exception:
            pass
    # Salvage a truncated array: close it after the last complete top-level object.
    depth = 0
    in_str = False
    esc = False
    last_obj_end = -1
    for i, ch in enumerate(t):
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                last_obj_end = i
    if last_obj_end != -1:
        try:
            return _json.loads(t[:last_obj_end + 1] + "]")
        except Exception:
            return None
    return None


def generate_plc_agenda(topic: dict, standards: list[dict]) -> dict:
    """Generate a collaborative-planning (PLC) agenda for a pacing week, grounded
    in the topic's real benchmarks, learning target, misconceptions and vocab.
    LLM when configured, else a structured template."""
    if settings.ai_provider == "anthropic" and settings.ai_api_key:
        got = _llm_agenda(topic, standards)
        if got:
            return got
    return _template_agenda(topic, standards)


def _template_agenda(topic: dict, standards: list[dict]) -> dict:
    misconceptions = []
    for s in standards:
        if s.get("misconceptions"):
            misconceptions.append({"standard": s["code"],
                                   "note": s["misconceptions"][:240]})
    return {
        "generated_by": "template",
        "ai_generated": False,
        "title": f"PLC Planning — {topic['name']} ({topic.get('chapter','')})",
        "week": topic.get("quarter", ""),
        "focus_standards": [s["code"] for s in standards],
        "learning_target": topic.get("learning_target", ""),
        "sections": [
            {"heading": "1. Norms & Objective (5 min)",
             "items": ["Review norms",
                       f"This week's focus: {topic['name']} — {topic.get('learning_target','')}"]},
            {"heading": "2. Standards Deep-Dive (10 min)",
             "items": [f"{s['code']}: {s['description'][:140]}" for s in standards]},
            {"heading": "3. Success Criteria — what mastery looks like (10 min)",
             "items": topic.get("success_criteria", []) or ["Define 'I can' statements"]},
            {"heading": "4. Anticipated Misconceptions (10 min)",
             "items": [f"{m['standard']}: {m['note']}" for m in misconceptions]
                      or ["Discuss likely student errors"]},
            {"heading": "5. Vocabulary Focus (5 min)",
             "items": topic.get("vocabulary", [])},
            {"heading": "6. Instructional Plan & Common Task (10 min)",
             "items": ["Agree on the week's mini-lessons and a common formative task",
                       "Plan small-group / DI supports for students below target"]},
            {"heading": "7. OPM / Assessment Plan (5 min)",
             "items": ["Agree on the Ongoing Progress Monitoring check for these benchmarks",
                       "Set the reassessment date"]},
            {"heading": "8. Teacher Commitments & Action Items (5 min)",
             "items": ["Each teacher commits to one instructional move",
                       "Assign action items and owners for next PLC"]},
        ],
        "note": "Editable draft — review before your planning meeting.",
    }


def _llm_agenda(topic: dict, standards: list[dict]) -> dict | None:
    try:
        import anthropic
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic(api_key=settings.ai_api_key)
        std_ctx = "\n".join(
            f"- {s['code']}: {s['description']}"
            + (f" | Misconceptions: {s['misconceptions'][:300]}" if s.get('misconceptions') else "")
            for s in standards
        )
        prompt = (
            "You are an elementary instructional coach preparing a weekly "
            "collaborative planning (PLC) meeting with teachers, grounded ONLY in "
            "the district pacing week below.\n\n"
            f"Grade {topic.get('grade_level')} {topic.get('subject')} — "
            f"{topic['topic_code']} {topic.get('chapter','')}: {topic['name']}\n"
            f"Pacing window: {topic.get('quarter','')}\n"
            f"Chapter learning target: {topic.get('learning_target','')}\n"
            f"Success criteria (I can): {topic.get('success_criteria', [])}\n"
            f"Vocabulary: {topic.get('vocabulary', [])}\n"
            f"Focus benchmarks:\n{std_ctx}\n\n"
            "Produce a concise, ready-to-run PLC agenda with timed sections: "
            "objective, standards deep-dive, success criteria, anticipated "
            "misconceptions, vocabulary, instructional plan + common formative "
            "task, OPM/assessment plan, and teacher commitments/action items. "
            "Ground everything in the benchmarks above. Do not invent standards."
        )
        msg = client.messages.create(
            model=settings.ai_model, max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        return {
            "generated_by": settings.ai_model,
            "ai_generated": True,
            "title": f"PLC Planning — {topic['name']} ({topic.get('chapter','')})",
            "week": topic.get("quarter", ""),
            "focus_standards": [s["code"] for s in standards],
            "learning_target": topic.get("learning_target", ""),
            "content": text,
            "note": "AI-generated draft — review before your planning meeting.",
        }
    except Exception:
        return None


def _llm_plan(standard: dict, group_size: int,
              student_profiles: list[dict]) -> dict | None:
    """Grounded LLM generation. Returns None on any failure so the caller falls
    back to the template (fail-safe, never fail-blank)."""
    try:
        import anthropic  # optional dependency
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic(api_key=settings.ai_api_key)
        flags = [p.get("flags", {}) for p in student_profiles]
        prompt = (
            "You are an expert elementary instructional coach. Create a 7-day "
            "differentiated reteach plan grounded ONLY in this Florida B.E.S.T. "
            f"standard.\n\nStandard {standard['code']} ({standard['subject']}, "
            f"grade {standard['grade_level']}): {standard['description']}\n"
            f"Group of {group_size} students needing reteach. "
            f"De-identified profiles (flags only): {flags}\n\n"
            "Follow this 7-day cycle: "
            + "; ".join(f"Day {d}: {t}" for d, (t, _) in CYCLE.items())
            + ". For each day give focus, concrete activities, and which "
            "printable artifacts to produce. Return concise structured text. "
            "Do not invent student data or scores."
        )
        msg = client.messages.create(
            model=settings.ai_model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        return {
            "generated_by": settings.ai_model,
            "ai_generated": True,
            "standard": standard["code"],
            "group_size": group_size,
            "grounding": {"standard": standard["code"],
                          "description": standard["description"]},
            "content": text,
            "note": "AI-generated draft — review and edit before teaching.",
        }
    except Exception:
        return None
