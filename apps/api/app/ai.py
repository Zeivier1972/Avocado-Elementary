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
