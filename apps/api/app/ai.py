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


# Plain-language rule appended to every writing prompt so output is simple enough
# for the coach to read aloud and explain to teachers.
_PLAIN = (
    "WRITE IN PLAIN, SIMPLE LANGUAGE — short sentences, everyday words a 10-year-old "
    "could understand — so the coach can explain it to teachers easily. Avoid jargon; "
    "if a technical term is truly needed, add a quick plain-words meaning right after it."
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
            "You are reading a school PACING GUIDE (it may be laid out as a TABLE "
            "with a Dates column next to a Lesson/Standard column). Extract the "
            "teaching schedule EXACTLY as written. Output one row per dated entry.\n\n"
            f"School year starts in August {year_start}. Resolve dates written like "
            f"'August 13', '8/13', or 'Aug 13' to ISO YYYY-MM-DD using this rule: "
            f"months August-December use {year_start}; January-July use "
            f"{year_start + 1}. If the document already gives full dates, use them.\n"
            "DATE RANGES: if an entry spans a range (e.g. '8/13-8/15' or "
            "'August 13 – 15'), output a SEPARATE row for EACH weekday in the range "
            "(skip weekends) with the SAME lesson, so every school day is on the "
            "calendar. A single-date entry is just one row.\n\n"
            "For each row return an object: {\"date\":\"YYYY-MM-DD\", "
            "\"lesson_code\":\"e.g. 1.1 or blank\", \"title\":\"the lesson/activity "
            "as written\", \"kind\":\"lesson|review|assessment|note\"}. Use "
            "\"assessment\" for a topic/chapter assessment or test day, \"review\" "
            "for a review day, \"lesson\" otherwise. Only include rows that have a "
            "real date in the document. Do not invent dates or lessons.\n\n"
            "PACING GUIDE:\n" + pacing_text.strip()[:30000]
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
    # Tier 2 academic vocabulary mined from THIS topic's standards (the school's
    # focus this year — cross-curricular words like determine/explain/justify
    # that appear in the question stems).
    from app.tier2_vocab import tier2_for_standards
    tier2_vocab = tier2_for_standards(standards)

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
        "tier2_vocabulary": tier2_vocab,
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
        f"Top misconceptions: {[m['misconception'] for m in summary.get('misconceptions', [])]}\n\n"
        + _PLAIN
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


# Tier 2 = high-utility ACADEMIC words that recur across grades and show up in
# the QUESTION STEMS of many standards (the words that trip kids up on the test).
# Tier 3 = subject-specific math terms. Used to split lesson vocabulary for the
# planning template's Tier 2 / Tier 3 focus, with an AI pass when available.
_TIER2_WORDS = {
    "represent", "model", "describe", "explain", "determine", "identify",
    "compare", "estimate", "solve", "select", "complete", "justify", "evaluate",
    "combine", "share", "distribute", "arrange", "total", "in all", "altogether",
    "each", "per", "equal", "equal groups", "group", "groups", "value", "amount",
    "relationship", "pattern", "unknown", "missing", "strategy", "expression",
    "part", "whole", "how many", "how much", "fewer", "more", "most", "least",
    "twice", "double", "sum", "difference", "increase", "decrease", "represents",
    "true", "matches", "shows", "reasonable", "explain your reasoning",
}


def _classify_vocabulary_fallback(words: list[str]) -> dict:
    tier2, tier3 = [], []
    for w in words:
        key = str(w).strip().lower()
        if not key:
            continue
        (tier2 if key in _TIER2_WORDS else tier3).append(
            {"word": w, "meaning": "", "why": ""})
    return {"tier2": tier2, "tier3": tier3, "ai_generated": False}


def classify_vocabulary(words: list[str], standards: list[dict],
                        grade: str = "", use_ai: bool = True) -> dict:
    """Split lesson vocabulary into Tier 2 (academic, cross-grade words that
    appear in the standard's question stems) and Tier 3 (subject-specific math
    terms), each with a kid-friendly meaning. AI when configured and use_ai is
    set, else an instant word-list fallback the teacher can complete. Set
    use_ai=False on a request that must return immediately (e.g. a file download
    behind an edge proxy) so a slow AI call can't drop the connection."""
    words = [w for w in (words or []) if str(w).strip()]
    if not words:
        return {"tier2": [], "tier3": [], "ai_generated": False}
    if not use_ai or not (settings.ai_provider == "anthropic" and settings.ai_api_key):
        return _classify_vocabulary_fallback(words)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ai_api_key)
    except Exception:
        return _classify_vocabulary_fallback(words)
    codes = [f"{s.get('code','')}: {s.get('description','')}" for s in standards][:6]
    prompt = (
        "Split these math vocabulary words into TIER 2 and TIER 3 for a "
        f"Grade {grade} lesson.\n"
        "TIER 2 = high-utility ACADEMIC words that appear across grade levels and "
        "in the QUESTION STEMS students read on this standard (e.g. represent, "
        "compare, determine, equal groups, in all). These are the words that make "
        "a test question hard even when a student knows the math.\n"
        "TIER 3 = SUBJECT-SPECIFIC math terms (e.g. array, factor, product, "
        "quotient, commutative property).\n"
        "Give each word a short kid-friendly meaning; for Tier 2 also give a "
        "one-line 'why it matters on the test'. Return ONLY JSON:\n"
        '{"tier2":[{"word":"","meaning":"","why":""}],'
        '"tier3":[{"word":"","meaning":""}]}\n\n'
        f"STANDARDS: {codes}\n"
        f"WORDS: {words}\n\n" + _PLAIN
    )
    try:
        with client.messages.stream(
            model=settings.ai_model, max_tokens=1500,
            system="You output ONLY one valid JSON object, no prose or fences.",
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            msg = stream.get_final_message()
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        import json as _json
        import re as _re
        m = _re.search(r"\{.*\}", text, _re.S)
        data = _json.loads(m.group(0)) if m else None
        if isinstance(data, dict) and ("tier2" in data or "tier3" in data):
            data.setdefault("tier2", [])
            data.setdefault("tier3", [])
            data["ai_generated"] = True
            return data
    except Exception:
        pass
    return _classify_vocabulary_fallback(words)


def _framework_app_fallback(component: dict, grade: str, topic_name: str,
                            week_focus: str) -> dict:
    name = component.get("name", "")
    return {
        "how_it_shows_up": component.get("in_math", "")
        or f"How {name} looks in {topic_name} for Grade {grade}.",
        "look_fors": component.get("coach_lookfors", [])[:5],
        "coaching_questions": component.get("coaching_questions", [])[:4],
        "growth_moves": component.get("growth_moves", [])[:3],
        "teacher_talking_points": [
            f"This week's lens is {name}: {week_focus}.",
            "Anchor it in the topic — model, question, and check through this lens.",
        ],
        "watch_fors": component.get("pitfalls", [])[:3],
        "ai_generated": False,
    }


def generate_framework_application(component: dict, grade: str, topic_name: str,
                                   standards: list[dict], week_focus: str) -> dict:
    """Script how one Framework of Effective Instruction component applies to a
    SPECIFIC grade + topic — content-specific look-fors, coaching questions,
    growth moves, teacher talking points, and watch-fors. One short AI call with
    a deterministic fallback."""
    if not (settings.ai_provider == "anthropic" and settings.ai_api_key):
        return _framework_app_fallback(component, grade, topic_name, week_focus)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ai_api_key)
    except Exception:
        return _framework_app_fallback(component, grade, topic_name, week_focus)
    codes = [f"{s.get('code','')}: {s.get('description','')}" for s in standards][:8]
    prompt = (
        "You are an expert K-3 math instructional coach. Script how ONE component "
        "of the Framework of Effective Instruction applies to a SPECIFIC grade and "
        "math topic, so the coach can lead a focused, content-specific planning "
        "conversation. Be concrete to the math in this topic — reference the actual "
        "content, models (CPA), and misconceptions. Return ONLY a JSON object:\n"
        '{"how_it_shows_up":"2-3 sentences: what this component looks like in THIS '
        'topic for THIS grade, referencing the actual math",'
        '"look_fors":["4-6 content-specific things to observe in a lesson"],'
        '"coaching_questions":["4-5 questions tied to this topic\'s math"],'
        '"growth_moves":["3-4 concrete coaching moves for this topic"],'
        '"teacher_talking_points":["3-5 things to say in the planning meeting"],'
        '"watch_fors":["3-4 topic-specific misconceptions or pitfalls to flag"]}\n\n'
        f"FRAMEWORK COMPONENT: {component.get('name','')} — {component.get('essence','')}\n"
        f"Component look-fors: {component.get('coach_lookfors', [])}\n"
        f"WEEK FOCUS: {week_focus}\n"
        f"GRADE: {grade}   TOPIC: {topic_name}\n"
        f"BENCHMARKS: {codes}\n\n"
        + _PLAIN
    )
    try:
        with client.messages.stream(
            model=settings.ai_model, max_tokens=1500,
            system="You output ONLY one valid JSON object, no prose or fences.",
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            msg = stream.get_final_message()
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        import json as _json
        import re as _re
        m = _re.search(r"\{.*\}", text, _re.S)
        data = _json.loads(m.group(0)) if m else None
        if isinstance(data, dict) and data.get("how_it_shows_up"):
            data["ai_generated"] = True
            return data
    except Exception:
        pass
    return _framework_app_fallback(component, grade, topic_name, week_focus)


def ask_assistant(message: str, history: list[dict], context: dict) -> dict:
    """The in-system Expert AI Coach. Grounded in the school's aggregate data;
    helps manage teachers/students/standards/pacing and drafts communications.
    Student data is aggregate-only (compliance, docs/00)."""
    system = (
        "You are the Avocado AI Coach — an expert instructional coach, data "
        "analyst, and assistant for a K-3 elementary school (Miami-Dade / Florida "
        "B.E.S.T.). You have a LIVE SNAPSHOT of this coach's whole system below. "
        "Answer the coach's questions directly FROM this snapshot — name specific "
        "teachers, grades, percentages, section codes, and dates when they are in "
        "the data.\n\n"
        "WHAT THIS PLATFORM DOES (know this so you answer about the tools too):\n"
        "• Collaborative Planning Guides — generated per grade/topic, grounded in "
        "the B1G-M (B.E.S.T.) benchmark content (clarifications, common "
        "misconceptions, instructional strategies, and the FLDOE Achievement Level "
        "Descriptors for what Level 3 looks like) PLUS the district pacing guide "
        "(lesson sequence, vocabulary, materials). Lessons are scripted in the "
        "ACES gradual-release model (I Do/Assemble → We Do/Connect → Y'all "
        "Do/Explore → You Do/Solo) with CPA (Concrete-Pictorial-Abstract) and "
        "CUBS. Review/test days are skipped.\n"
        "• Coach One-Pager — a short 'how to present it' distillation of a guide.\n"
        "• Weekly Planning Template (teacher walkout) — a one-page, 5-lesson "
        "gradual-release grid with Tier 2 / Tier 3 vocabulary that teachers fill "
        "in; a filled Example version is available.\n"
        "• TIER 2 ACADEMIC VOCABULARY is the school's FOCUS THIS YEAR: "
        "cross-curricular academic words (determine, explain, justify, represent, "
        "compare, model …) mined from each grade's standards and woven into the "
        "guides and templates. Tier 3 = subject-specific math terms. The Tier 2 "
        "words per grade are in the snapshot below.\n"
        "• Framework of Effective Instruction — 6 components with a weekly coaching "
        "lens; the coach plans a WEEK AHEAD.\n"
        "• Master schedule — each teacher's Math time and Math-DI window (DI runs "
        "during Science/Social Studies), plus a conflict-free visit planner.\n"
        "• Staff/Section directory — maps every class code (K01, 101, A13 …) to its "
        "teacher, room, program (Gen Ed/ASD), and birthday; ASD schedule rows are "
        "resolved to the real teacher.\n"
        "• Collaborative Planning A/B rotation with a host per meeting.\n"
        "• Math Goal Setting Rubric — crosswalks FAST → level → topic goal %, and "
        "color-codes results L1 Red, L2 Yellow, L3 Green, L4 Blue, L5 Orange.\n"
        "• Assessments — topic-test blueprints (which standard each item assesses), "
        "and uploaded class results scored per standard and per student, with the "
        "most-missed questions per class for DI packets. Tracked all year vs "
        "i-Ready and FAST.\n\n"
        "If something isn't in the snapshot, say so plainly and point to where in "
        "the app it lives (Reports, Assessments, Schedule, Staff, Planning, Key "
        "Dates, a teacher's page) rather than guessing. Be concise, practical, and "
        "action-oriented. Never invent individual student names or scores — student "
        "data here is aggregate/teacher-level by design; for a single student, "
        "direct the coach to that teacher's tracker. When asked, draft teacher "
        "emails with a clear subject line and a body ready to send.\n"
        + _PLAIN + "\n\n"
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
    sd = ctx.get("staff_directory") or []
    if sd:
        lines.append("\nSTAFF / SECTION DIRECTORY (which teacher owns each class "
                     "code; ★ = teaches math):")
        for s in sd:
            star = "★" if s.get("teaches_math") else " "
            bday = f" · bday {s['birthday']}" if s.get("birthday") else ""
            mt = ", ".join(s.get("math_times") or [])
            di = ", ".join(s.get("di_windows") or [])
            when = f" · Math {mt}" if mt else ""
            when += f" · DI {di}" if di else ""
            lines.append(
                f"  {star} {s['section'] or '—'} · G{s['grade']} {s['program']} · "
                f"{s['teacher']} (Rm {s['room']}){when}{bday}")
    az = ctx.get("assessments") or []
    if az:
        lines.append("\nTOPIC TESTS & STANDARDS ASSESSED (tracked all year vs "
                     "i-Ready & FAST):")
        for a in az:
            lines.append(
                f"  - G{a['grade']} {a['topic']}: {a['items']} items / "
                f"{a['points']} pts — standards {', '.join(a['standards']) or '—'}")
            r = a.get("results")
            if r:
                cls = "; ".join(f"{c['teacher']} {c['avg']}% ({c['color']})"
                                for c in r.get("classes", []))
                ws = r.get("weakest_standard")
                lines.append(
                    f"      RESULTS: {r['students']} students, grade avg "
                    f"{r.get('grade_avg')}% ({r.get('color')}). Classes: {cls or '—'}.")
                if ws:
                    lines.append(
                        f"      Weakest standard: {ws['standard']} at {ws['percent']}% "
                        f"({ws['color']}) — target for DI.")
                if r.get("most_missed"):
                    mm = ", ".join(f"Q{m['q']} ({m['standard']}, {m['miss_pct']}% missed)"
                                   for m in r["most_missed"])
                    lines.append(f"      Most-missed: {mm}")
    t2 = ctx.get("tier2_by_grade") or {}
    if any(t2.values()):
        lines.append("\nTIER 2 ACADEMIC VOCABULARY per grade (THIS YEAR'S FOCUS — "
                     "cross-curricular words from the standards' question stems; "
                     "built into guides & lesson templates):")
        for g in ("K", "1", "2", "3"):
            if t2.get(g):
                lines.append(f"  - Grade {g}: {', '.join(t2[g])}")
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
    fapps = ctx.get("framework_applications") or []
    if fapps:
        lines.append("Framework already scripted to specific topics: "
                     + "; ".join(f"G{a['grade']} {a['topic']} ({a['component']})"
                                 for a in fapps[:12]))
    gr = ctx.get("goal_rubric") or {}
    if gr.get("level3"):
        lines.append(
            "\nMATH GOAL SETTING RUBRIC (FAST scale -> topic-assessment goal). "
            "On-grade (Level 3, the school goal) begins at: "
            + "; ".join(f"G{g}: FAST {v['scale_at_or_above']}+ -> topic goal {v['topic_goal']}"
                        for g, v in sorted(gr["level3"].items()))
            + ". Use this to compare a student's topic-test average to where their "
            "FAST score says they should be, and to project end-of-year.")
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
    # Guarantee at least a couple of in-lesson activities to choose from.
    if not lesson.get("activities"):
        skill = (lesson.get("title") or "the skill").lower()
        lesson["activities"] = [
            {"name": "Show Me boards", "type": "hands-on",
             "phase": "We Do / You Do",
             "how": f"Pose a quick problem on {skill}; students build/solve on "
                    "whiteboards and hold them up so you see every answer at once.",
             "why": "Fast check for understanding for every student."},
            {"name": "Rally Coach (partners)", "type": "partner",
             "phase": "Y'all Do",
             "how": "Partner A solves one problem aloud while B coaches and checks, "
                    "then they switch — each uses the sentence frame.",
             "why": "Every student explains their thinking using the vocabulary."},
        ]
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


# Pacing-guide day rows that are NOT teaching lessons — review days and
# test/assessment days. The coach only wants a guide for the actual lessons.
import re as _re_lessons
_SKIP_ROW = _re_lessons.compile(
    r"(?:\breview\b|\bre-?teach\w*|\bassess\w*|\btest\w*|\btesting\b|\bquiz\w*"
    r"|\bexam\b|\bmid-?topic\b|\bunit\s+test\b|\bchapter\s+test\b"
    r"|\bperformance\s+task\b|\bculminating\b)",
    _re_lessons.I)


def _is_teaching_lesson(row: dict) -> bool:
    """True unless the row is a standalone review or test/assessment day. A row
    that carries a real LESSON CODE (e.g. 2.4) is always kept, even if its title
    contains a word like 'review' — only code-less review/test days are dropped,
    so we never lose a numbered lesson."""
    code = str(row.get("code", "")).strip()
    if _re_lessons.search(r"\d", code):   # has a lesson number -> a real lesson
        return True
    text = f"{code} {row.get('title','')} {row.get('kind','')}".lower()
    return not _SKIP_ROW.search(text)


def _lessons_only(rows: list[dict]) -> list[dict]:
    """Drop review and test/assessment days, keeping the actual lessons in order.
    If a list is ALL non-lesson rows (e.g. a topic that is only an assessment),
    keep it as-is so we never produce an empty guide."""
    kept = [r for r in (rows or []) if _is_teaching_lesson(r)]
    return kept if kept else (rows or [])


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
    for L in _lessons_only(topic.get("lessons", [])):
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
    '"activities":[{"name":"the activity name","type":"game|hands-on|partner|station|movement|math-talk",'
    '"phase":"which ACES phase / when in the lesson it fits","how":"exactly how to run it in 1-3 steps with the actual numbers/materials","why":"the skill it builds"}],'
    '"book_reference":{"lesson":"the matching textbook lesson name/number","pages":"the page range in the book",'
    '"model_example":"the actual book Build Understanding / Think & Grow model example (with its real numbers) to MODEL in the I Do — same as i_do.problem","model_pages":"its page(s)",'
    '"guided_practice":"the actual book Try It / Show and Grow problem (real numbers) for the We Do","guided_pages":"its page(s)",'
    '"independent_practice":"the actual book In-Class Practice / Apply and Grow problems (real numbers) for the Solo (You Do)","independent_pages":"its page(s)",'
    '"exit_problem":"one In-Class Practice problem (real numbers) that matches TODAY\'S objective — the exit slip — or the book Closure","exit_pages":"its page(s)",'
    '"dig_deeper":"the actual book Dig Deeper higher-order question (real numbers) to infuse as a stretch/enrichment","dig_deeper_pages":"its page(s)",'
    '"level3_problem":"the actual book problem (real numbers) that hits the Level-3 proficiency target for this lesson","level3_pages":"its page(s)",'
    '"examples":"which book Example(s) to model","practice":"which book practice/problem set to assign","from_book":true},'
    '"exit_ticket":{"problem":"one problem","answer":"the answer"}}]'
)

_LESSON_RULES = (
    "You are SCRIPTING a lesson that a BRAND-NEW elementary teacher will read and "
    "deliver word-for-word. NO SHORTCUTS, no vague or generic filler.\n"
    "Every ACES phase — i_do (ASSEMBLE/model), we_do (CONNECT/guided), explore_yall_do "
    "(EXPLORE/collaborative), you_do (SOLO/independent) — MUST contain:\n"
    "  1) 'problem' — the exact problem worked in that phase. Normally use a "
    "DIFFERENT problem in every phase (never reuse a number within the lesson). "
    "EXCEPTION: when the source includes the actual TEXTBOOK (from_book true), the "
    "i_do / we_do / you_do 'problem' fields MUST be the real book problems named in "
    "the book map below (same numbers/wording) — do NOT swap in invented problems "
    "just to make them different. The guide and the lesson plan both read these "
    "'problem' fields, so using the book's problems here makes them match the book;\n"
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
    "- book_reference + USE THE BOOK'S REAL PROBLEMS: IF the source includes the "
    "actual TEXTBOOK / student book (Big Ideas Math / enVision — it shows lesson "
    "numbers, page numbers, worked Examples and practice sets), MATCH each lesson to "
    "the real book lesson and PULL THE ACTUAL BOOK PROBLEMS into the gradual-release "
    "phases, using this exact map (Big Ideas Math section names shown):\n"
    "    * I DO (i_do, Assemble/model) — the book's 'Build Understanding' / 'Think & "
    "Grow' worked example IS a model problem: the teacher models it. Put that real "
    "example (its numbers) in i_do.problem AND in book_reference.model_example.\n"
    "    * WE DO (we_do, Connect/guided) — the book's 'Try It' is only one or two "
    "problems done together: use it as the We Do. Put a Try It problem (real numbers) "
    "in we_do.problem AND in book_reference.guided_practice.\n"
    "    * CHECK FOR UNDERSTANDING (cfu) — pull the 1-2 CFU checks from the book's "
    "'Try It' or 'In-Class Practice' (real problems), not invented ones.\n"
    "    * YOU DO (you_do, Solo/independent) — the problem RIGHT AFTER 'Modeling Real "
    "Life' (the Show-and-Grow the students do right after the teacher models) is a You "
    "Do: students solve it independently. Put that book problem (real numbers) in "
    "you_do.problem. The broader 'In-Class Practice / Apply and Grow' set is the "
    "assigned independent practice — put it in book_reference.independent_practice.\n"
    "    * Y'ALL DO (explore_yall_do, collaborative) — build this from the PACING "
    "GUIDE as usual (not the book), so it stays a collaborative task.\n"
    "    * EXIT SLIP (exit_ticket) — choose one 'In-Class Practice' problem that "
    "directly addresses TODAY'S objective, or the book's Closure. Put it in "
    "exit_ticket.problem and in book_reference.exit_problem.\n"
    "    * LEVEL 3 (level3_look_like) — pick the real book problem that hits the "
    "Level-3 proficiency target for this lesson and work it in level3_look_like; put "
    "it in book_reference.level3_problem.\n"
    "    * DIG DEEPER — put the book's 'Dig Deeper' higher-order question in "
    "book_reference.dig_deeper AND infuse it as a stretch: add it as a challenge for "
    "early finishers / Level-4 students inside the you_do 'do' and as one 'activities' "
    "or 'cfu' entry, so the rigor question is actually planned into the lesson.\n"
    "  The i_do / we_do / you_do 'problem' fields and the matching book_reference "
    "slots MUST be the SAME problem (same numbers) so the planning guide and the "
    "teacher lesson plan show the identical book problem for each phase.\n"
    "  Give the book lesson name/number, page ranges (model_pages/guided_pages/"
    "independent_pages/exit_pages/dig_deeper_pages/level3_pages), and set from_book "
    "true. Use the ACTUAL numbers/wording from the book — never paraphrase away the "
    "problem. If the source is ONLY a pacing guide with no book pages, set from_book "
    "false, leave the book fields blank, and script the phases from the pacing guide "
    "as usual — do NOT invent page numbers or book problems.\n"
    "- activities: 2-3 REAL, engaging activities that can be done WITHIN this "
    "lesson (a game, hands-on/manipulative task, partner or station activity, a "
    "movement or a math-talk). For each, name it, say which phase it fits, and "
    "give the exact steps with the actual numbers/materials for THIS lesson — not "
    "generic ideas. Keep them do-able in a normal class period.\n"
    "- TIER 2 ACADEMIC VOCABULARY (this year's focus): the benchmark text lists "
    "cross-curricular academic words (e.g. determine, explain, justify, represent, "
    "compare, model). Weave these SAME words into the teacher's questions ('say') "
    "and into the sentence frames students must use, so students hear and use the "
    "exact academic words they will meet in the test questions. Prefer the academic "
    "verb the standard uses.\n"
    "Do not invent standards or student data. Output ONLY the JSON array.\n"
    + _PLAIN
)


# Visual models the packet renderer can draw. The AI picks ONE that fits the
# benchmark and gives an integer "value" (or a/b, rows/cols) per modeled problem.
_DI_MODELS = ("ten_frame", "pairing", "base_ten", "array", "number_line",
              "equal_teams", "bar_model", "none")


def suggest_di_model(code: str, description: str, grade: str = "") -> str:
    """A sensible default visual model for a benchmark, from its strand + words.
    Grade-aware: Kindergarten counts by ONES to 5, so it uses five-frames /
    countable objects — never ten-frames or base-ten (no grouping by ten yet)."""
    c = (code or "").upper()
    d = (description or "").lower()
    if (grade or "").upper() == "K":
        # K Topic assessments are count-to-5: a set of counters in a FIVE-frame,
        # or countable objects. Match the test — never tens/base-ten.
        return "five_frame"
    if "NSO.1" in c or "place value" in d or "hundreds" in d or "tens and ones" in d:
        return "base_ten"
    if "even" in d or "odd" in d:
        return "pairing"
    if "array" in d or "rows" in d:
        return "array"
    if "equal group" in d or "repeated addition" in d or "multiplication" in d:
        return "equal_groups"
    if "number line" in d or "skip count" in d:
        return "number_line"
    if "sum" in d and ("equal" in d or "two equal" in d):
        return "equal_teams"
    if "within 20" in d or "sums to 20" in d or "addition facts" in d or "make a ten" in d:
        return "ten_frame"
    if "real-world" in d or "word problem" in d or "problems" in d:
        return "bar_model"
    return "ten_frame"


_DI_PACKET_SCHEMA = (
    '[{"tier":"Intensive|Cusp|Strategic",'
    '"days":[{"day":1,"title":"kid-friendly focus for the day","model":"array",'
    '"pacing":"Model 5 min · Try it 10 min · On your own 15 min",'
    '"watch_it":{"rows":2,"cols":3,"statement":"the big idea in one kid sentence, WITH the answer",'
    '"steps":["Step 1 — name/draw the model","Step 2 — the action (skip count / add groups)","Step 3 — write the equation and answer"]},'
    '"try_it":{"problem":"one guided problem in student words — SAME method as Watch it, new numbers",'
    '"steps":["Step 1 — same first move, no answer","Step 2","Step 3 — set up the equation but do NOT state the final answer"]},'
    '"on_your_own":[{"text":"an independent problem that mirrors a missed test item","choices":["option A","option B","option C","option D"],"answer_frame":"____ groups of ____ = ____ (ASD packets only; a fill-in frame, no answer)","answer":"correct option — TEACHER KEY ONLY, not shown to students"}]}],'
    '"opm":[{"problem":"a short progress-monitoring question on THIS standard","answer":"the answer — teacher key only"}]}]'
)


def generate_di_packets(standard: dict, most_missed: list, grade: str,
                        tiers: list, tier2: list | None = None,
                        asd: bool = False) -> dict:
    """Generate the three rotation-tier DI packets (Intensive / Cusp / Strategic)
    as STUDENT-FACING packets, grounded in the B1G-M benchmark AND the most-missed
    test questions. Each tier is split into DAYS (its TLC count: Intensive/Cusp = 2,
    Strategic = 1); each day runs Watch it -> Try it -> On your own with a visual
    MODEL chosen for the standard, plenty of independent practice (~30-min center),
    and an OPM progress check per tier. When asd=True the packet is adapted for
    students with autism (predictable structure, literal language, task-analysis
    checklists, fewer items, answer frames, a clear finish line)."""
    code = standard.get("code", "")
    model = suggest_di_model(code, standard.get("description", ""), grade)
    base = {"standard": code, "description": standard.get("description", ""),
            "grade_level": grade, "model": model, "asd": asd,
            "tiers": [], "ai_generated": False}
    if not (settings.ai_provider == "anthropic" and settings.ai_api_key):
        base["ai_status"] = ("AI is off — turn on AI_PROVIDER=anthropic, AI_API_KEY, "
                             "AI_MODEL to write the DI packets.")
        return base
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ai_api_key)
        std_ctx = _std_context([standard])
        missed_txt = "\n".join(
            f"- Q{m.get('position')}: {(m.get('stem') or '').strip()[:220]} "
            f"(answer {m.get('correct_response','')}, missed by {m.get('miss_pct','')}%)"
            for m in (most_missed or [])[:8]) or "(no item stems captured)"
        day_map = "\n".join(
            f"- {t['name']} ({t['band']}): {t['tlc_sessions']} day(s)" for t in tiers)
        prompt = (
            f"You are an elementary math coach writing STUDENT DI PACKETS for Grade "
            f"{grade} on ONE benchmark. Kids work these at a 30-minute teacher-led "
            f"center. NO teacher script — write everything TO THE STUDENT.\n\n"
            f"TARGET BENCHMARK — {code}: {standard.get('description','')}\n"
            f"CRITICAL: EVERY problem, in EVERY tier and EVERY section (watch_it, "
            f"try_it, on_your_own, OPM), MUST assess THIS EXACT benchmark ({code}). "
            f"Differentiate ONLY by number size and scaffolding (Intensive = smaller "
            f"numbers + more support; Strategic = harder) — it is ALWAYS the same "
            f"skill. NEVER substitute an easier or different standard: e.g. if the "
            f"benchmark is repeated addition / arrays, do NOT drift to even/odd, "
            f"counting, or plain addition. For a very low student, scaffold the SAME "
            f"skill with tiny numbers — do not change the skill.\n\n"
            f"BENCHMARK (B1G-M — ground every problem here so it hits the target):\n{std_ctx}\n\n"
            f"MOST-MISSED TEST QUESTIONS (mirror THESE — same idea, format and number "
            f"range):\n{missed_txt}\n\n"
            f"TIER 2 academic words to weave in: {', '.join(tier2 or [])}\n\n"
            f"VISUAL MODEL — pick ONE model per DAY and put it on the day object as "
            f"\"model\". That SAME model is used for Watch it, Try it and On your own "
            f"that day, so I do -> We do -> You do all practice the SAME "
            f"representation. Use a DIFFERENT model on a different DAY or TIER to "
            f"match a different missed item — but NEVER mix models within one day. "
            f"Allowed models (use only ones that TRULY represent {code}; the default "
            f"that fits it is '{model}'):\n"
            f"  - array: rows×cols dot grid (equal rows shown as a grid) — \"rows\",\"cols\"\n"
            f"  - equal_groups: N GROUPS OF M for repeated addition / multiplication — "
            f"draws 'a' separate group-circles each holding 'b' counters — give \"a\" "
            f"(number of groups) and \"b\" (amount in EACH group). Use THIS, not "
            f"equal_teams, for '3 groups of 2'.\n"
            f"  - equal_teams: TWO equal addends a + b (even/odd only) — \"a\",\"b\"\n"
            f"  - number_line: skip-counting / jumps to a total — \"value\",\"max\"\n"
            f"  - five_frame: a row of 5 cells with counters — COUNT TO 5 (Kinder) — \"value\" (0-5)\n"
            f"  - counters: just N countable objects, no frame — count by ones — \"value\"\n"
            f"  - ten_frame: counts/sums within 20 — \"value\" (0-20)\n"
            f"  - base_ten: place value, tens & ones — \"value\"\n"
            f"  - pairing: even/odd as pairs — \"value\" (0-30)\n"
            + ("KINDERGARTEN RULE (these kids are NOT counting by tens yet): use "
               "ONLY 'five_frame' or 'counters', numbers 0-5, and count-the-objects "
               "problems (starfish, cars, frogs…) that ask 'how many?'. NEVER a "
               "ten_frame, base_ten, or any grouping into tens. The test shows a set "
               "of red counters in a FIVE-frame — mirror that exactly.\n"
               if (grade or "").upper() == "K" else "")
            + f"MATCH THE TEST: the day's model MUST be the SAME representation the "
            f"MOST-MISSED items above use — arrays for array/row items, a number line "
            f"for skip-counting, equal groups for repeated addition, a ten-frame for "
            f"within-20 sums, base-ten for place value. Look at how those missed items "
            f"are drawn and mirror it.\n"
            f"Only WATCH IT is drawn for the student — it is the worked example, so put "
            f"the day-model's numeric fields ON watch_it. Try it and On your own are "
            f"the STUDENT's to draw and solve, so they carry NO numeric fields and no "
            f"picture.\n\n"
            f"SCAFFOLDED MODELING (this is what makes it teachable): watch_it is not "
            f"just a picture — give it a \"steps\" list that WALKS THE METHOD one move "
            f"at a time (e.g. 'Step 1: draw 3 rows', 'Step 2: put 4 dots in each row', "
            f"'Step 3: skip count 4, 8, 12', 'Step 4: write 3 × 4 = 12'). Try it "
            f"repeats the SAME numbered steps with a new problem (student does each "
            f"step, no answer given), and On your own gives problems the student "
            f"solves with those SAME steps from memory. Steps must be concrete, "
            f"do-able actions a K-3 / ESE / ASD student can follow, not explanations.\n\n"
            f"NEVER GIVE THE ANSWER AWAY in Try it or On your own. Watch it shows the "
            f"worked answer; but try_it steps guide the METHOD only and must NOT state "
            f"the final result, and on_your_own problems must not reveal their answer "
            f"(put the correct choice in \"answer\" as a TEACHER KEY only — students "
            f"never see it). Do not tell students to 'draw' a model you have already "
            f"drawn for them.\n\n"
            f"Split EACH tier into this many DAYS:\n{day_map}\n"
            "Each day: watch_it (one worked example), try_it (one guided problem with "
            "2-3 student steps), and on_your_own with ENOUGH problems to fill ~15 "
            + ("minutes (ASD: keep it SHORT — 3 problems per day, one clear idea "
               "each). " if asd else
               "minutes of independent work (Intensive & Cusp: 5-6 per day; "
               "Strategic: 4-5 plus a 'Dig Deeper' enrichment). ")
            + "If the test is multiple choice, "
            "give each on_your_own problem a 'choices' array of 3-4 SHORT options "
            "(exactly one correct) so it looks like the test; otherwise omit "
            "'choices'. Tier intent: Intensive = "
            "foundational, smallest numbers, the Watch-it model is fully worked; Cusp "
            "= targeted practice to reach proficiency; Strategic = practice + "
            "higher-order enrichment. Day 2 (Intensive/Cusp) uses larger numbers. "
            "Include 3 OPM questions per tier.\n\n"
            + (
                "AUTISM (ASD) SUPPORTS — this class is students with autism, so adapt "
                "for them:\n"
                "- Use LITERAL, concrete, short sentences. No idioms, sarcasm, or "
                "open-ended wording. One instruction per sentence.\n"
                "- Keep the SAME predictable structure and the SAME model every day; "
                "familiarity lowers anxiety.\n"
                "- Make each step a DISCRETE, observable action the student can check "
                "off ('Draw 3 circles.' not 'Think about the groups.').\n"
                "- FEWER items, lots of white space, one clear idea at a time.\n"
                "- Give each on_your_own problem an \"answer_frame\" — a fill-in "
                "sentence frame like '____ groups of ____ = ____' or '____ x ____ = "
                "____' so the response is structured (still no answer given).\n"
                "- Use calm, familiar, concrete contexts (blocks, snacks, pencils); "
                "avoid busy story problems.\n\n"
                if asd else ""
            )
            + "Every number is grade-appropriate and grounded in the benchmark. Write "
            "at an elementary reading level.\n\n"
            f"Return ONLY a JSON array (one object per tier, in the order given) "
            f"matching:\n{_DI_PACKET_SCHEMA}\n{_PLAIN}"
        )
        arr, reason = _llm_json(
            client, prompt,
            "You output ONLY a valid JSON array, no prose or fences. Finish every "
            "object completely.", 14000)
        if not arr:
            base["ai_status"] = reason or "the model did not return usable packets"
            return base
        by_name = {str(t.get("tier", "")).lower(): t for t in arr}
        out_tiers = []
        for t in tiers:
            gen = by_name.get(t["name"].lower(), {})
            out_tiers.append({"tier": t["name"], "stars": t["stars"],
                              "band": t["band"], "tlc_sessions": t["tlc_sessions"],
                              "days": gen.get("days", []), "opm": gen.get("opm", [])})
        base.update({"tiers": out_tiers, "ai_generated": True,
                     "generated_by": settings.ai_model})
        return base
    except Exception as e:
        base["ai_status"] = f"{type(e).__name__}: {str(e)[:200]}"
        return base


_ENRICH_SCHEMA = (
    '[{"tier":"Enrichment",'
    '"days":[{"day":1,"title":"kid-friendly challenge focus",'
    '"pacing":"Study it 5 min · Try it 10 min · On your own 15 min",'
    '"watch_it":{"statement":"a worked ABOVE-GRADE example that shows the reasoning in kid words","model":"array","value":12},'
    '"try_it":{"problem":"one guided multi-step challenge in student words","model":"array","value":16,'
    '"steps":["step 1","step 2","step 3"]},'
    '"on_your_own":[{"text":"a challenge problem — multi-step, or explain/prove your thinking, or create your own","standard":"MA...","show_model":false,"answer":"the answer or a sample response"}]}],'
    '"opm":[{"problem":"a stretch check-question","answer":"the answer"}]}]'
)


def generate_enrichment_packet(standards: list, grade: str,
                               tier2: list | None = None) -> dict:
    """Generate ONE student-facing ENRICHMENT / 'Dig Deeper' packet for the high
    (all-Green) kids, covering ALL the given benchmarks together at ABOVE-GRADE
    rigor — multi-step problems, explain/prove your thinking, open-ended and
    'create your own' challenges — no reteach scaffolds. Renders through the same
    tier/day machinery as the reteach packets (a single 'Enrichment' tier)."""
    codes = [s.get("code", "") for s in standards if s.get("code")]
    label = " + ".join(codes) if codes else "Enrichment"
    model = suggest_di_model(codes[0] if codes else "",
                             standards[0].get("description", "") if standards else "",
                             grade)
    base = {"standard": label, "description": "Dig Deeper — enrichment challenge",
            "grade_level": grade, "model": model, "enrichment": True,
            "tiers": [], "ai_generated": False}
    if not (settings.ai_provider == "anthropic" and settings.ai_api_key):
        base["ai_status"] = ("AI is off — turn on AI_PROVIDER=anthropic, AI_API_KEY, "
                             "AI_MODEL to write the enrichment packet.")
        return base
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ai_api_key)
        std_ctx = _std_context(standards)
        model_hint = "; ".join(
            f"{s.get('code','')} -> {suggest_di_model(s.get('code',''), s.get('description',''), grade)}"
            for s in standards) or model
        young = (grade or "").upper() in ("PK", "K", "1")
        band = ("Extend & explore — within grade" if young
                else "Above grade — Dig Deeper")
        if young:
            rigor = (
                f"RIGOR: STAY WITHIN the standard and WITHIN grade-level numbers — do "
                f"NOT go above grade. These are Grade {grade} kids who JUST took the "
                f"first topic test, so keep numbers in the SAME small range the test "
                f"used (for Kinder Topic 1 that is 0-5 — never higher). Enrichment "
                f"here means DEEPER, MORE VARIED practice at the SAME level, not "
                f"harder: count different sets of objects, show the same number a "
                f"different way (a five-frame, then fingers, then objects), match a "
                f"number to a set, one more / one less within the range, and subitize "
                f"(say how many without counting). Keep it playful, concrete, and "
                f"hands-on. NEVER multi-step reasoning, big numbers, 'prove it another "
                f"way', or anything above grade.\n\n")
            build = (
                f"Build ONE short day: watch_it (a worked count example in the tested "
                f"range), try_it (one guided count problem with 1-2 tiny steps), and "
                f"on_your_own with just 3-4 simple, varied count problems. Use the "
                f"five_frame or counters model; numbers 0-5 for Kinder Topic 1. Give "
                f"an 'answer' for each. Include 1-2 gentle OPM checks.\n\n")
        else:
            rigor = (
                f"RIGOR: ABOVE grade level. These kids have the basics, so PUSH them: "
                f"multi-step problems, problems that combine BOTH benchmarks at once, "
                f"'explain your thinking', 'prove it another way', 'find the mistake', "
                f"open-ended tasks with more than one answer, and 'create your own "
                f"problem for a friend'. Bigger numbers than the tested grade, and "
                f"reasoning over recall. NEVER a plain recall drill.\n\n")
            build = (
                f"Build ONE day with gradual release: watch_it (a worked above-grade "
                f"example showing the reasoning), try_it (one guided multi-step "
                f"challenge with 2-3 student steps), and on_your_own with 6-8 rich "
                f"challenge problems spanning the benchmarks (tag each with its "
                f"'standard' code). Include 2-3 stretch OPM checks.\n\n")
        prompt = (
            f"You are an elementary math coach writing ONE student ENRICHMENT packet "
            f"for Grade {grade} for the students who are ALREADY PROFICIENT (all "
            f"Green). They work it at a 30-minute teacher-led center. NO teacher "
            f"script — write everything TO THE STUDENT.\n\n"
            f"Extend these benchmarks — do NOT reteach, but stay ON these standards:\n"
            f"{std_ctx}\n\n"
            + rigor
            + f"TIER 2 academic words to weave in: {', '.join(tier2 or [])}\n\n"
            + build
            + f"Most enrichment problems are constructed-response, so set "
            f"\"show_model\": false and give an 'answer' (or a sample response for "
            f"open-ended ones) — add a visual only where it truly helps by setting "
            f"\"model\" and \"value\" on that problem (models: {model_hint}). For "
            f"'array' use \"rows\"/\"cols\"; 'equal_teams'/'equal_groups' use "
            f"\"a\"/\"b\"; 'number_line' use \"value\"/\"max\"; 'five_frame'/"
            f"'counters' use \"value\".\n\n"
            + ("KINDERGARTEN RULE: numbers 0-5 only, use five_frame or counters, "
               "count by ones, never tens/base-ten or above-grade content.\n\n"
               if (grade or "").upper() == "K" else "")
            + f"Return ONLY a JSON array with ONE object matching:\n{_ENRICH_SCHEMA}\n{_PLAIN}"
        )
        arr, reason = _llm_json(
            client, prompt,
            "You output ONLY a valid JSON array, no prose or fences. Finish every "
            "object completely.", 12000)
        if not arr:
            base["ai_status"] = reason or "the model did not return a usable packet"
            return base
        gen = arr[0] if arr else {}
        base.update({
            "tiers": [{"tier": "Enrichment", "stars": 3, "band": band,
                       "tlc_sessions": 1, "days": gen.get("days", []),
                       "opm": gen.get("opm", [])}],
            "ai_generated": True, "generated_by": settings.ai_model})
        return base
    except Exception as e:
        base["ai_status"] = f"{type(e).__name__}: {str(e)[:200]}"
        return base


def generate_target_the_misses(standard: dict, most_missed: list, grade: str,
                               model: str) -> list:
    """Layer 2 of DI: cluster the class's most-missed questions ON THIS BENCHMARK
    by the MISCONCEPTION they reveal (not just the standard), and write matched
    'fix-it' samples that mirror the real items (their wording/format/numbers) so
    students rectify that exact mistake. Uses the captured question text (stems)
    when the test PDF was uploaded. Returns [] if AI is off or nothing to target."""
    if not most_missed:
        return []
    if not (settings.ai_provider == "anthropic" and settings.ai_api_key):
        return []
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ai_api_key)
        std_ctx = _std_context([standard])
        have_text = any((m.get("stem") or "").strip() for m in most_missed)
        items_txt = "\n".join(
            f"- Q{m.get('position')} [{m.get('standard') or '?'}] "
            f"({m.get('miss_pct','')}% missed, correct "
            f"answer {m.get('correct_response','')}): "
            f"{(m.get('stem') or '(question text not captured)').strip()[:300]}"
            for m in most_missed[:10])
        prompt = (
            f"You are a Grade {grade} math coach planning the TARGETED part of a DI "
            f"reteach for ONE benchmark. Below are the ACTUAL test questions the "
            f"class missed most on this benchmark"
            + (" (with their real wording)" if have_text else
               " (only item numbers + correct answers were captured — the test PDF "
               "wasn't uploaded, so mirror the SKILL and format from the benchmark)")
            + f":\n{items_txt}\n\n"
            f"BENCHMARK + common misconceptions (B1G-M):\n{std_ctx}\n\n"
            "Each question's standard code is given in [brackets]. These questions "
            "MAY SPAN A FEW STANDARDS — that is fine; target every one the class "
            "missed, even if it is not the packet's main standard.\n"
            "CLUSTER these missed questions by the MISCONCEPTION or error they "
            "reveal (questions missed for the SAME reason go together; questions on "
            "the same standard but a DIFFERENT demand — e.g. a word problem vs an "
            "equation vs a picture — go in separate clusters). NEVER put questions "
            "from DIFFERENT standards in the same cluster. Tag each cluster with the "
            "standard given in [brackets] for its questions EXACTLY — never guess or "
            "relabel it. For EACH cluster give 2-3 matched 'fix-it' problems "
            "that MIRROR the real questions (same format and number range) so "
            "students rectify that exact mistake, each with its answer. Write the "
            "problems TO THE STUDENT, elementary reading level.\n\n"
            "If the real questions are multiple choice, give each fix sample a "
            "'choices' array of 3-4 SHORT options (one correct) that mirror the "
            "test's answer choices — including a plausible wrong option matching the "
            "misconception; otherwise omit 'choices'.\n"
            'Return ONLY a JSON array: [{"questions":["Q17","Q19"],"standard":"MA...",'
            '"why_missed":"the misconception in plain words",'
            '"fix_samples":[{"problem":"a matched problem","choices":["A opt","B opt","C opt","D opt"],"answer":"the correct option"}]}]'
            f"\n{_PLAIN}")
        arr, _ = _llm_json(
            client, prompt,
            "You output ONLY a valid JSON array, no prose or fences.", 6000)
        return arr or []
    except Exception:
        return []


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
        source = ("From the UPLOADED DOCUMENT below (a pacing guide or the actual "
                  "TEXTBOOK/book chapter), list the actual TEACHING lessons in "
                  "order — use the book's real lesson names/numbers when present. "
                  "SKIP review days and test/assessment days (review, re-teach, "
                  "topic/chapter/unit assessment or test, quiz).\n\nDOCUMENT:\n"
                  + pacing_text.strip()[:45000])
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
    return _lessons_only(out)


def _lesson_detail(client, topic, std_ctx, batch, pacing_text, max_tokens=20000):
    """Expand a small batch of lesson stubs into full ACES detail (bounded call)."""
    stub_txt = "\n".join(
        f"- Lesson {L.get('code')}: {L.get('title')} "
        f"(benchmarks {', '.join(L.get('benchmarks', []))}; focus: {L.get('focus','')})"
        for L in batch
    )
    pacing_block = ("\n\nUse this uploaded document (pacing guide and/or the actual "
                    "TEXTBOOK chapter) for these lessons — match to the book's real "
                    "lesson, pages, Examples and practice sets where they appear:\n"
                    + pacing_text.strip()[:40000]) if pacing_text else ""
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
        "object completely — never stop mid-object.", max_tokens)


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
                for L in _lessons_only(topic.get("lessons") or [])
            ]
        if not skeleton:
            return None, "could not determine the lesson list from the pacing guide"

        # Two fully-scripted lessons per call: small enough that a richly-scripted
        # batch rarely truncates, few enough calls to keep generation responsive.
        # If a batch comes back short (truncated / unparseable), we do NOT drop
        # straight to a generic template — we RETRY each missing lesson on its own
        # (a single lesson has plenty of token headroom), and only template-fill a
        # lesson that still fails. This stops the "some lessons are richly scripted
        # with book problems, others are generic filler" split.
        def _code(x):
            return str((x or {}).get("code", "")).strip()

        out, errs = [], []
        for i in range(0, len(skeleton), 2):
            batch = skeleton[i:i + 2]
            detail, err = _lesson_detail(client, topic, std_ctx, batch, pacing_text)
            got = [d for d in (detail or []) if isinstance(d, dict)]
            covered = {_code(d) for d in got if _code(d)}
            for L in batch:
                if _code(L) and _code(L) in covered:
                    continue
                one, err1 = _lesson_detail(
                    client, topic, std_ctx, [L], pacing_text, max_tokens=12000)
                if one and isinstance(one[0], dict):
                    got.append(one[0])
                else:
                    errs.append(err1 or err or "batch failed")
                    mini = dict(topic)
                    mini["lessons"] = [L]
                    got.extend(_template_lessons(mini, std_by_code))
            # Keep the skeleton's order.
            order = {_code(L): n for n, L in enumerate(batch)}
            got.sort(key=lambda d: order.get(_code(d), 99))
            out.extend(got)
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


# Keys whose string values are prose the coach reads to teachers. We simplify
# ONLY these. Number-bearing keys (problem, abstract, solution, code, benchmarks,
# cfu, *_example) are deliberately NOT here, so every problem, equation and
# number in an existing guide is left exactly as written.
_SIMPLIFY_KEYS = {
    "focus", "learning_goal", "benchmark_clarification", "clarification",
    "vocabulary_integration", "activate_prior_knowledge", "say", "do",
    "concrete", "pictorial", "look_for", "cubs", "roles", "structure",
    "misconception", "fix", "student_explanation", "sentence_frame",
    "how_it_shows_up", "big_idea", "why_it_matters", "talking_points",
    "watch_fors", "note", "overview", "teacher_talking_points",
    "coaching_questions", "growth_moves", "success_criteria", "explanation",
}


def _collect_prose_slots(node, slots):
    """Walk a guide dict, appending (container, key_or_index, original) for every
    prose string under a key we simplify. Because we keep the container + key we
    can write the rewrite straight back in place — structure and number-bearing
    fields are untouched."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _SIMPLIFY_KEYS:
                if isinstance(v, str) and v.strip():
                    slots.append((node, k, v))
                elif isinstance(v, list):
                    for i, item in enumerate(v):
                        if isinstance(item, str) and item.strip():
                            slots.append((v, i, item))
                        else:
                            _collect_prose_slots(item, slots)
                elif isinstance(v, dict):
                    _collect_prose_slots(v, slots)
            else:
                _collect_prose_slots(v, slots)
    elif isinstance(node, list):
        for item in node:
            _collect_prose_slots(item, slots)


def simplify_guide_text(guide: dict):
    """Rewrite the prose inside an EXISTING guide into plain, teacher-friendly
    language without rebuilding it — same structure, same keys, same problems,
    numbers and equations. Returns (new_guide, changed_count, error)."""
    import copy
    new_guide = copy.deepcopy(guide)
    slots: list = []
    _collect_prose_slots(new_guide, slots)
    if not slots:
        return new_guide, 0, None
    if not (settings.ai_provider == "anthropic" and settings.ai_api_key):
        return new_guide, 0, "AI is off — set the AI key in Railway to simplify language."
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ai_api_key)
    except Exception as e:  # pragma: no cover
        return new_guide, 0, f"AI unavailable: {e}"

    import json as _json
    changed = 0
    BATCH = 25
    for start in range(0, len(slots), BATCH):
        chunk = slots[start:start + BATCH]
        originals = [s[2] for s in chunk]
        prompt = (
            "Rewrite each string below into plain, simple language a 10-year-old "
            "could understand, so a coach can read it to teachers. KEEP THE "
            "MEANING. Keep every number, equation, fraction, blank (like __), "
            "student name, manipulative name, and vocabulary term EXACTLY as "
            "written — only make the words simpler and the sentences shorter. "
            "Return ONLY a JSON array of the rewritten strings, the SAME length "
            "and SAME order as the input (one rewrite per input, nothing extra).\n\n"
            "INPUT:\n" + _json.dumps(originals, ensure_ascii=False)
        )
        arr, _reason = _llm_json(
            client, prompt,
            "You output ONLY a JSON array of strings, same length as the input.",
            8000,
        )
        if isinstance(arr, list) and len(arr) == len(chunk):
            for (container, key, _orig), new_val in zip(chunk, arr):
                if isinstance(new_val, str) and new_val.strip():
                    container[key] = new_val.strip()
                    changed += 1
        # A mismatched or failed batch keeps its originals — never corrupts.
    new_guide["language_simplified"] = True
    return new_guide, changed, None


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
            "Ground everything in the benchmarks above. Do not invent standards.\n\n"
            + _PLAIN
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
            "Do not invent student data or scores.\n\n"
            + _PLAIN
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
