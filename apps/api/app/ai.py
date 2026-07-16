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


def generate_planning_guide(topic: dict, standards: list[dict]) -> dict:
    """Generate a full lesson-by-lesson Collaborative Planning Guide matching the
    M-DCPS format (Quick Facts, benchmark clarifications, misconceptions, and a
    per-lesson breakdown with Teaching Strategy, CPA model, ALD Level 3 example,
    CFU, You Do, Exit Ticket). Grounded in the pacing guide + B1G-M content."""
    std_by_code = {s["code"]: s for s in standards}
    quick_facts = {
        "time_frame": topic.get("time_frame", ""),
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
    misconceptions = [
        {"code": s["code"], "note": s["misconceptions"]}
        for s in standards if s.get("misconceptions")
    ]
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


def _parse_misconceptions(raw: str) -> list[dict]:
    """Turn a B1G-M misconception string ('... Fix: ... Next mistake. Fix: ...')
    into structured {misconception, fix} pairs for the guide."""
    import re as _re
    if not raw:
        return []
    # Split into "<misconception> Fix: <fix>" chunks. Each fix ends where the
    # next misconception sentence begins.
    pairs = []
    # Break on "Fix:" but keep the misconception that precedes it.
    parts = _re.split(r"\bFix:\s*", raw)
    # parts[0] = first misconception; parts[i] = fix_i + next misconception.
    lead = parts[0].strip()
    for i in range(1, len(parts)):
        chunk = parts[i].strip()
        if i < len(parts) - 1:
            # The fix is everything up to the last sentence boundary; the tail
            # sentence(s) become the next misconception.
            m = _re.match(r"(.*?[.!?])\s+(.*)$", chunk, _re.S)
            if m:
                fix, nxt = m.group(1).strip(), m.group(2).strip()
            else:
                fix, nxt = chunk, ""
        else:
            fix, nxt = chunk, ""
        if lead:
            pairs.append({"misconception": lead, "fix": fix})
        lead = nxt
    if not pairs and raw.strip():
        pairs.append({"misconception": raw.strip(), "fix": ""})
    return pairs


def _template_lessons(topic: dict, std_by_code: dict) -> list[dict]:
    """Grounded, genuinely useful lessons built from the pacing outline + B1G-M
    standard metadata (clarifications, misconceptions, prerequisites). Used both
    as the pre-AI skeleton and as the fallback when the LLM call fails, so the
    guide is never blank."""
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
        # Success criteria grounded in the lesson focus and standard clarifications.
        crit = []
        if focus:
            crit.append(focus)
        crit.extend(clar[:2])
        # Teaching strategy: an explicit I-Do / We-Do / You-Do arc anchored to CPA.
        strategy = [
            f"Activate prior knowledge ({', '.join(pre) if pre else 'prerequisite skills'}) "
            "and introduce vocabulary: " + (", ".join(vocab[:4]) if vocab else "key terms") + ".",
            f"I Do — model with {conc}; think aloud through {title.lower() or 'the skill'}.",
            "We Do — guided practice with immediate feedback; students explain their reasoning (MTR 4.1).",
            "You Do — students practice independently; teacher pulls a small group for reteach.",
        ]
        out.append({
            "code": L.get("code", ""), "title": title,
            "benchmarks": codes, "focus": focus,
            "learning_goal": f"I can {title[:1].lower() + title[1:]}." if title else "",
            "success_criteria": crit,
            "benchmark_clarification": " ".join(clar) or s.get("description", ""),
            "misconceptions": _parse_misconceptions(s.get("misconceptions", "")),
            "teaching_strategy": strategy,
            "cpa": {
                "concrete": f"Use {conc} to build/represent the concept.",
                "pictorial": "Draw place-value charts, number lines, or models to represent it.",
                "abstract": "Record with numbers and symbols; explain the reasoning in writing.",
            },
            "level3_example": (
                "An ALD Level 3 student can independently " + (focus[:1].lower() + focus[1:] if focus else title.lower())
                + " and explain their reasoning using correct vocabulary."
            ),
            "cfu": [
                "Quick check: have students show the skill on mini-whiteboards.",
                "Ask a 'why' question to surface reasoning, not just the answer.",
            ],
            "you_do": f"Independent practice on {title.lower() or 'the skill'} "
                      "(3–5 problems); reteach small group as needed.",
            "exit_ticket": "One problem targeting today's benchmark — score for green (≥69%) mastery.",
        })
    return out


def _llm_lessons(topic: dict, standards: list[dict]):
    """Ask the LLM for the per-lesson breakdown as strict JSON, grounded in the
    benchmarks. Returns (lessons | None, error_reason | None)."""
    try:
        import anthropic
    except ImportError:
        return None, "anthropic SDK not installed"
    try:
        import json as _json
        client = anthropic.Anthropic(api_key=settings.ai_api_key)
        std_ctx = "\n".join(
            f"- {s['code']}: {s.get('description','')}"
            + (f"\n    Clarifications: {' | '.join(s.get('clarifications', []))}" if s.get('clarifications') else "")
            + (f"\n    Common misconceptions: {s['misconceptions']}" if s.get('misconceptions') else "")
            + (f"\n    Instructional strategies (B1G-M): {s['strategies']}" if s.get('strategies') else "")
            for s in standards
        )
        outline = topic.get("lessons") or []
        outline_txt = "\n".join(
            f"- Lesson {L.get('code')}: {L.get('title')} "
            f"(benchmarks {', '.join(L.get('benchmarks', []))}; focus: {L.get('focus','')})"
            for L in outline
        ) or "Design a logical sequence of 5-7 lessons covering the benchmarks."
        schema = (
            '[{"code":"7.1","title":"...","benchmarks":["MA.3..."],"focus":"...",'
            '"learning_goal":"I can ...","success_criteria":["..."],'
            '"benchmark_clarification":"... with a worked example",'
            '"misconceptions":[{"misconception":"...","fix":"..."}],'
            '"teaching_strategy":["step 1","step 2"],'
            '"cpa":{"concrete":"...","pictorial":"...","abstract":"..."},'
            '"level3_example":"student explanation at ALD Level 3",'
            '"cfu":["..."],"you_do":"independent practice task",'
            '"exit_ticket":"one problem with the answer"}]'
        )
        prompt = (
            "You are an elementary math instructional coach writing a lesson-by-lesson "
            "Collaborative Planning Guide for teachers, grounded ONLY in the Florida "
            "B.E.S.T. benchmarks and pacing content below. Use the CPA (Concrete-"
            "Pictorial-Abstract) model and ALD Level 3 proficiency examples.\n\n"
            f"Grade {topic.get('grade_level')} {topic.get('subject')} — "
            f"{topic['topic_code']}: {topic['name']}\n"
            f"Topic learning goal: {topic.get('learning_target','')}\n"
            f"Success criteria: {topic.get('success_criteria', [])}\n"
            f"Vocabulary: {topic.get('vocabulary', [])}\n"
            f"MTR practices: {topic.get('mtr_practices', [])}\n"
            f"Materials: {topic.get('materials', [])}\n\n"
            f"Benchmarks (with B1G-M detail):\n{std_ctx}\n\n"
            f"Lesson outline to expand:\n{outline_txt}\n\n"
            "For EACH lesson produce: student-friendly learning goal, success "
            "criteria, a benchmark clarification with a worked example, likely "
            "misconceptions with fixes, a step-by-step teaching strategy, a CPA "
            "model (concrete/pictorial/abstract), an ALD Level 3 proficiency "
            "example, checks for understanding, a 'You Do' task, and a single "
            "exit-ticket problem with its answer. Ground everything in the "
            "benchmarks; do not invent standards or student data.\n\n"
            f"Return ONLY valid JSON, an array matching this schema:\n{schema}"
        )
        # Stream — an 8k-token, 7-lesson generation is long enough to hit a
        # request timeout on a plain create() call, which would drop us to the
        # empty template. Streaming keeps the connection alive.
        with client.messages.stream(
            model=settings.ai_model, max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            msg = stream.get_final_message()
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            text = text[4:] if text.startswith("json") else text
            text = text.rsplit("```", 1)[0] if "```" in text else text
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end == -1:
            return None, "model did not return JSON array"
        return _json.loads(text[start:end + 1]), None
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:200]}"


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
