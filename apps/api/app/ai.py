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
