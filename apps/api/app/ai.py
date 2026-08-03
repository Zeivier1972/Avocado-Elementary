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


def ask_assistant(message: str, history: list[dict], context: dict) -> dict:
    """The in-system Expert AI Coach. Grounded in the school's aggregate data;
    helps manage teachers/students/standards/pacing and drafts communications.
    Student data is aggregate-only (compliance, docs/00)."""
    system = (
        "You are the Avocado AI Coach — an expert instructional coach, data "
        "analyst, and assistant for a K-3 elementary school (Miami-Dade / Florida "
        "B.E.S.T.). You help the coach and school leaders manage teachers, "
        "students, standards, pacing, collaborative planning, differentiated "
        "instruction, and progress toward the school grade. You can draft emails "
        "and messages to teachers when asked. Be concise, practical, and "
        "action-oriented. Ground answers in the SCHOOL CONTEXT provided. Never "
        "fabricate individual student data or scores; speak about students in "
        "aggregate. When drafting a teacher email, return a clear subject line "
        "and body the coach can review and send.\n\n"
        f"SCHOOL CONTEXT (live aggregates):\n{_context_text(context)}"
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
        f"Students: {ctx.get('students',0)} | Teachers: {ctx.get('teachers',0)} "
        f"| Classes: {ctx.get('classes',0)}",
        f"Students by grade: {ctx.get('by_grade', {})}",
    ]
    if ctx.get("fast_math_proficiency_by_grade"):
        lines.append("FAST Math % proficient (Level 3+) by grade & period: "
                     f"{ctx['fast_math_proficiency_by_grade']}")
    if ctx.get("fast_levels"):
        lines.append(f"FAST Math achievement-level counts: {ctx['fast_levels']}")
    if ctx.get("teachers_sample"):
        lines.append(f"Teachers (sample): {', '.join(ctx['teachers_sample'])}")
    if ctx.get("pacing_topics"):
        lines.append("Pacing topics: " + "; ".join(ctx["pacing_topics"]))
    if ctx.get("standards_count"):
        lines.append(f"Standards loaded: {ctx['standards_count']}")
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

        activate = pick("activate_prior_knowledge",
            f"Review prerequisite skills ({', '.join(pre) if pre else 'earlier-grade foundations'}) "
            "and introduce vocabulary: " + (", ".join(vocab[:4]) if vocab else "key terms") + ".")
        i_do = pick("i_do",
            f"Model {title.lower() or 'the skill'} with {conc}; think aloud step by step.")
        we_do = pick("we_do",
            "Guided practice with immediate feedback; students explain their reasoning (MTR 4.1).")
        # ACES: Explore = Y'all Do — collaborative team practice between We Do and
        # You Do (teacher observes and supports).
        explore = pick("explore_yall_do",
            f"In teams, students apply {title.lower() or 'the skill'} on a shared task; "
            "they problem-solve together and justify their thinking while the teacher observes and supports.")
        you_do = pick("you_do",
            f"Students practice {title.lower() or 'the skill'} independently "
            "(3–5 problems); pull a small group for reteach.")
        cfu = pick("cfu", [
            "Quick check on mini-whiteboards.",
            "Ask a 'why' question to surface reasoning, not just the answer.",
        ])
        exit_ticket = pick("exit_ticket",
            "One problem targeting today's benchmark — score ≥69% = green.")
        cpa = pick("cpa", {
            "concrete": f"Use {conc} to build/represent the concept.",
            "pictorial": "Draw place-value charts, number lines, or models to represent it.",
            "abstract": "Record with numbers and symbols; explain the reasoning in writing.",
        })
        level3 = pick("level3_example",
            "A Level 3 student can independently "
            + (focus[:1].lower() + focus[1:] if focus else title.lower())
            + " and explain their reasoning using correct vocabulary.")
        misc = pick("misconceptions", _parse_misconceptions(s.get("misconceptions", "")))
        crit = pick("success_criteria", ([focus] if focus else []) + clar[:2])
        # Back-compat numbered strategy, assembled from the ACES phases.
        strategy = pick("teaching_strategy", [
            f"Activate Prior Knowledge — {activate}",
            f"Assemble (I Do) — {i_do}",
            f"Connect (We Do) — {we_do}",
            f"Explore (Y'all Do) — {explore}",
            f"Share (You Do) — {you_do}",
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
            "activate_prior_knowledge": activate,
            "i_do": i_do,
            "we_do": we_do,
            "explore_yall_do": explore,
            "teaching_strategy": strategy,
            "cpa": cpa,
            "level3_example": level3,
            "cfu": cfu,
            "you_do": you_do,
            "exit_ticket": exit_ticket,
        })
    return out


def _llm_lessons(topic: dict, standards: list[dict], pacing_text: str | None = None):
    """Ask the LLM for the per-lesson breakdown as strict JSON, grounded in the
    benchmarks (and the coach's uploaded pacing-guide text when provided).
    Returns (lessons | None, error_reason | None)."""
    try:
        import anthropic
    except ImportError:
        return None, "anthropic SDK not installed"
    try:
        import json as _json
        client = anthropic.Anthropic(api_key=settings.ai_api_key)
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
        std_ctx = "\n".join(
            f"- {s['code']}: {s.get('description','')}"
            + (f"\n    Clarifications: {' | '.join(s.get('clarifications', []))}" if s.get('clarifications') else "")
            + (f"\n    Common misconceptions: {s['misconceptions']}" if s.get('misconceptions') else "")
            + (f"\n    Instructional strategies (B1G-M): {s['strategies']}" if s.get('strategies') else "")
            + _ald_line(s)
            for s in standards
        )
        outline = topic.get("lessons") or []
        outline_txt = "\n".join(
            f"- Lesson {L.get('code')}: {L.get('title')} "
            f"(benchmarks {', '.join(L.get('benchmarks', []))}; focus: {L.get('focus','')})"
            for L in outline
        ) or "Design a logical sequence of 5-7 lessons covering the benchmarks."
        # When the coach uploaded a pacing guide, use its text as the PRIMARY
        # source for the lesson sequence and content (truncated to stay in budget).
        pacing_block = ""
        if pacing_text and pacing_text.strip():
            pacing_block = (
                "\n\nUPLOADED PACING GUIDE (primary source — extract the topic's "
                "lesson sequence, learning goals, and content from this; align each "
                "lesson to the benchmarks above):\n"
                + pacing_text.strip()[:12000]
            )
        schema = (
            '[{"code":"7.1","title":"...","benchmarks":["MA.3..."],"focus":"...",'
            '"learning_goal":"I can ... (student-friendly)",'
            '"success_criteria":["observable behavior 1","observable behavior 2"],'
            '"success_example":"a worked example that shows mastery (e.g. In 4,582: 4=4,000 ...)",'
            '"benchmark_clarification":"what students must understand",'
            '"benchmark_example":"a specific worked numeric example",'
            '"sentence_frame":"The __ is in the __ place, so it means __.",'
            '"misconceptions":[{"misconception":"...","example":"specific wrong answer a student gives","fix":"correction strategy"}],'
            '"activate_prior_knowledge":"how to activate prior knowledge for THIS lesson, with a specific warm-up",'
            '"i_do":"ASSEMBLE (I Do): teacher models with a specific worked example and think-aloud",'
            '"we_do":"CONNECT (We Do): guided practice with a specific example and how to engage students together",'
            '"explore_yall_do":"EXPLORE (Y\'all Do): collaborative TEAM practice on a specific task; students work in teams, apply the skill, and problem-solve while the teacher observes",'
            '"cpa":{"concrete":"hands-on with materials; INCLUDE base-ten emoji visuals like 🟦 thousands 🟩 hundreds 🟨 tens ⬜ ones","pictorial":"place-value chart / number line drawing","abstract":"the numbers and symbols, e.g. 3,476 = 3,000 + 400 + 70 + 6"},'
            '"level3_example":"a first-person student quote explaining the reasoning at ALD Level 3",'
            '"cfu":["specific problem 1","specific problem 2"],'
            '"you_do":"independent practice task with specific numbers",'
            '"exit_ticket":{"problem":"one problem","answer":"the answer"}}]'
        )
        prompt = (
            "You are an elementary math instructional coach writing a lesson-by-lesson "
            "Collaborative Planning Guide for teachers. Match the M-DCPS format EXACTLY "
            "and at high specificity. Ground everything ONLY in the Florida B.E.S.T. "
            "(B1G-M) benchmark detail and pacing content below — use their real "
            "clarifications and misconceptions, and write concrete WORKED numeric "
            "examples (actual numbers, not placeholders).\n\n"
            f"Grade {topic.get('grade_level')} {topic.get('subject')} — "
            f"{topic['topic_code']}: {topic['name']}\n"
            f"Topic learning goal: {topic.get('learning_target','')}\n"
            f"Success criteria: {topic.get('success_criteria', [])}\n"
            f"Vocabulary: {topic.get('vocabulary', [])}\n"
            f"MTR practices: {topic.get('mtr_practices', [])}\n"
            f"Materials: {topic.get('materials', [])}\n\n"
            f"Benchmarks (with B1G-M detail — use these clarifications & misconceptions):\n{std_ctx}\n\n"
            f"Lesson outline to expand:\n{outline_txt}\n"
            f"{pacing_block}\n\n"
            "CRITICAL: every lesson must be DIFFERENT and specific to its own "
            "benchmark and skill — never reuse the same activate/I Do/We Do/CFU/"
            "You Do/exit wording across lessons. Each field must use worked "
            "numbers appropriate to THAT lesson (e.g. a 'round to nearest ten' "
            "lesson uses ones-digit examples like 47→50; a 'compare' lesson uses "
            "two 4-digit numbers).\n\n"
            "For EACH lesson produce, at the depth of a real teacher-ready plan:\n"
            "- a student-friendly 'I can' learning goal\n"
            "- observable success criteria PLUS a worked success_example with real numbers\n"
            "- a benchmark clarification and a specific benchmark_example (real numbers)\n"
            "- a sentence_frame students use to explain their reasoning\n"
            "- a 3-column misconceptions table: each row has the misconception, a "
            "specific EXAMPLE ERROR a student makes (real numbers), and the correction strategy\n"
            "Structure the lesson using the school's ACES gradual-release model: "
            "Assemble (I Do) -> Connect (We Do) -> Explore (Y'all Do, collaborative "
            "teams) -> Share (You Do, independent). Provide all four phases:\n"
            "- activate_prior_knowledge: a specific warm-up that connects to THIS lesson\n"
            "- i_do (Assemble): the teacher models ONE specific worked example with a think-aloud\n"
            "- we_do (Connect): guided practice on a DIFFERENT specific example, plus how "
            "students engage together (turn-and-talk, whiteboards, the sentence frame)\n"
            "- explore_yall_do (Explore): a collaborative TEAM task where students apply the "
            "skill together and problem-solve while the teacher observes and supports\n"
            "- a CPA model where Concrete INCLUDES base-ten emoji block visuals "
            "(🟦 thousands, 🟩 hundreds, 🟨 tens, ⬜ ones), Pictorial is a place-value "
            "chart or number line, and Abstract shows the expanded-form/equation\n"
            "- a Level 3 proficiency example written as a first-person student quote\n"
            "- cfu: specific problems (real numbers), a 'You Do' task with specific "
            "numbers, and a single exit ticket with BOTH the problem and its answer, "
            "written so a correct answer demonstrates Level 3 mastery\n"
            "Do not invent standards or student data.\n\n"
            f"Return ONLY valid JSON, an array matching this schema:\n{schema}"
        )
        # Stream a generous budget — a full 7-lesson ACES guide is large, and a
        # truncated response is the usual cause of "did not return JSON array".
        with client.messages.stream(
            model=settings.ai_model, max_tokens=16000,
            system=("You output ONLY a single valid JSON array. No prose, no "
                    "markdown fences, no explanation before or after."),
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            msg = stream.get_final_message()
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        stop = getattr(msg, "stop_reason", "")
        lessons = _parse_json_array(text)
        if lessons:
            return lessons, None
        tail = text[-160:].replace("\n", " ") if text else "(empty response)"
        note = " (response was truncated — hit the token limit)" if stop == "max_tokens" else ""
        return None, f"model reply was not parseable JSON{note}. Ends with: …{tail}"
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
