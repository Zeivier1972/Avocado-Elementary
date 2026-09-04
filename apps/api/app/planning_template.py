"""Build the teacher WALKOUT for a collaborative-planning session: a fillable
lesson-planning template organized by the gradual-release (ACES) model, with
Tier 2 / Tier 3 vocabulary. It shows what the guide models in each phase and
leaves clear prompts for the teacher to write their own plan — so they
internalize the planning guide instead of just receiving it.

Deterministic: reads the guide JSON app.ai already produced. The vocabulary
tiering is passed in (app.ai.classify_vocabulary), so this stays instant.
"""
from __future__ import annotations

# Gradual-release phases mapped to the school's ACES model, in order.
_PHASES = [
    ("i_do", "I Do", "Assemble",
     "Teacher models the thinking out loud; students watch and listen."),
    ("we_do", "We Do", "Connect",
     "Teacher and students work it together; students try with support."),
    ("explore_yall_do", "Y'all Do", "Explore",
     "Students work in pairs / small groups; teacher circulates and coaches."),
    ("you_do", "You Do", "Solo",
     "Students work independently; teacher checks who has it and who needs DI."),
]


def _as_list(v) -> list[str]:
    if isinstance(v, list):
        return [str(x) for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    return []


def _split_questions(say) -> tuple[list[str], list[str]]:
    """From a phase's 'say' lines, separate questions (end with ?) from moves."""
    questions, moves = [], []
    for line in _as_list(say):
        (questions if line.strip().endswith("?") else moves).append(line)
    return questions, moves


def _phase_model(guide_lessons: list[dict], key: str) -> dict:
    """A representative example for this phase, drawn from the first lesson that
    scripts it — what the guide models, so the teacher has a worked reference."""
    for L in guide_lessons:
        ph = L.get(key)
        if not isinstance(ph, dict):
            continue
        questions, moves = _split_questions(ph.get("say"))
        teacher = _as_list(ph.get("do")) + moves
        students = []
        if key == "explore_yall_do":
            if ph.get("structure"):
                students.append(f"Structure: {ph['structure']}")
            if ph.get("roles"):
                students.append(f"Roles: {ph['roles']}")
        if key == "you_do" and ph.get("cubs"):
            students.append(f"CUBS: {ph['cubs']}")
        if ph.get("look_for"):
            students.append(f"Look for: {ph['look_for']}")
        cpa = {k: ph.get(k, "") for k in ("concrete", "pictorial", "abstract")}
        return {
            "from_lesson": L.get("code", ""),
            "problem": ph.get("problem", ""),
            "teacher_moves": teacher,
            "questions": questions,
            "students": students,
            "cpa": {k: v for k, v in cpa.items() if v},
        }
    return {"from_lesson": "", "problem": "", "teacher_moves": [],
            "questions": [], "students": [], "cpa": {}}


def _phase_strategies(key: str, has_cpa: bool, has_cubs: bool) -> list[str]:
    out = []
    if key == "i_do" and has_cpa:
        out.append("CPA — model Concrete → Pictorial → Abstract in that order.")
    if key == "we_do":
        out.append("Think-aloud + guided questioning; students narrate the step.")
    if key == "explore_yall_do":
        out.append("Structured collaboration (Rally Coach / Numbered Heads) with "
                   "assigned roles and a required sentence frame.")
    if key == "you_do" and has_cubs:
        out.append("CUBS word-problem routine; pull a small reteach group.")
    return out


def _exit_text(et) -> str:
    if isinstance(et, dict):
        p, a = et.get("problem", ""), et.get("answer", "")
        return f"{p} → {a}" if a else p
    return str(et or "")


def _phase_cell(L: dict, key: str) -> str:
    """A compact, filled example for one lesson's phase — what the teacher does,
    a question to ask, and what students do — used for the 'filled example'
    version. Kept short so it reads inside a grid cell."""
    ph = L.get(key)
    if not isinstance(ph, dict):
        return ""
    # You Do: don't write out every problem — reference the book's independent set
    # (page numbers) and name the strategy, then walk CUBS on ONE specific
    # 'Modeling Real Life' problem. Much less writing, same rigor.
    if key == "you_do":
        br = L.get("book_reference") or {}
        ip = (br.get("independent_practice") or "").strip()
        ipg = (br.get("independent_pages") or "").strip()
        ref = ip or "the In-Class Practice / Apply and Grow set"
        ref_line = ("Students work independently on " + ref
                    + (f" (p. {ipg})" if ipg else "") + " — utilizing CUBS.")
        parts = [ref_line]
        if ph.get("problem"):
            parts.append(f"Model Real Life (CUBS on this one): {ph['problem']}")
        if ph.get("cubs"):
            parts.append(f"CUBS: {ph['cubs']}")
        elif ph.get("look_for"):
            parts.append(f"Look for: {ph['look_for']}")
        return "\n".join(parts)
    # Prefer the phase's explicit guiding questions (We Do), else parse them from
    # the 'say' lines.
    questions = _as_list(ph.get("questions"))
    say_q, moves = _split_questions(ph.get("say"))
    if not questions:
        questions = say_q
    move = (moves[0] if moves else "") or (" ".join(_as_list(ph.get("do"))[:1]))
    q = questions[0] if questions else ""
    if key == "explore_yall_do":
        students = ph.get("structure", "") or "Work in pairs/groups"
        if ph.get("roles"):
            students += f" — {ph['roles']}"
    elif key == "you_do":
        students = ("CUBS: " + ph["cubs"]) if ph.get("cubs") else "Work independently"
    else:
        students = ph.get("look_for", "") or "Try it with support"
    parts = []
    # I Do names the STRATEGY it models; We Do CONNECTS back to it — so the grid
    # shows the strategy and think-aloud, not just the problem.
    if key == "i_do" and ph.get("strategy"):
        parts.append(f"Strategy: {ph['strategy']}")
    if key == "we_do" and ph.get("connect"):
        parts.append(f"Connect: {ph['connect']}")
    # Show the actual problem, so the lesson plan uses the SAME book problem the
    # planning guide models for this phase.
    if ph.get("problem"):
        parts.append(f"Problem: {ph['problem']}")
    if move:
        parts.append(f"You: {move}")
    if q:
        parts.append(f"Ask: {q}")
    if key == "we_do" and ph.get("check"):
        parts.append(f"Check: {ph['check']}")
    if students:
        parts.append(f"Students: {students}")
    return "\n".join(parts)


def _activities_text(L: dict) -> str:
    """A short list of this lesson's in-lesson activities for the template cell."""
    out = []
    for a in (L.get("activities") or [])[:3]:
        if isinstance(a, dict):
            name = a.get("name", "")
            phase = a.get("phase", "")
            out.append(f"• {name}" + (f" ({phase})" if phase else ""))
        elif a:
            out.append(f"• {a}")
    return "\n".join(out)


def _day_slots(lessons: list[dict]) -> list[dict]:
    """Five lesson slots for the week — a DATE blank, not a weekday, since the
    coach doesn't know which lesson lands on which day. Each slot is pre-labeled
    with its lesson (code / title / goal) and carries a filled example for each
    gradual-release phase (used by the example version). Extra lessons roll to a
    next-week print."""
    slots = []
    for i in range(5):
        L = lessons[i] if i < len(lessons) else None
        slots.append({
            "slot": i + 1,
            "lesson_code": (L or {}).get("code", "") if L else "",
            "title": (L or {}).get("title", "") if L else "",
            "learning_goal": (L or {}).get("learning_goal", "") if L else "",
            "exit": _exit_text((L or {}).get("exit_ticket")) if L else "",
            "activities": _activities_text(L) if L else "",
            "phase_example": {k: _phase_cell(L, k) for (k, *_ ) in _PHASES}
                             if L else {},
        })
    return slots


def build_planning_template(guide: dict, summary: dict, vocab_tiers: dict) -> dict:
    """Assemble the weekly (5-day) fillable planning one-pager from the guide +
    coach summary + Tier 2/3 vocabulary."""
    lessons = guide.get("lessons", []) or []
    strat_names = [s.get("name", "") for s in summary.get("strategies", [])]
    has_cpa = any("CPA" in n for n in strat_names)
    has_cubs = any("CUBS" in n for n in strat_names)

    # Phase definitions drive the grid's row labels + a one-line "what to plan".
    phases = []
    for key, gr, aces, essence in _PHASES:
        strategies = _phase_strategies(key, has_cpa, has_cubs)
        phases.append({
            "key": key, "gradual_release": gr, "aces": aces, "essence": essence,
            "plan_prompt": "What you'll do · questions you'll ask · what students do",
            "strategies_suggested": strategies,
            # A tiny worked reference from the guide (kept short for the grid).
            "model": _phase_model(lessons, key),
        })

    misc = summary.get("misconceptions", []) or []
    # A real week-level goal: the guide's focus, unless it's just the topic name
    # (e.g. "Topic 2") — then fall back to the first lesson's learning goal.
    focus = (summary.get("focus", "") or "").strip()
    first_goal = next((L.get("learning_goal", "") for L in lessons
                       if L.get("learning_goal")), "")
    trivial = (not focus) or focus.lower().startswith(("topic", "chapter")) \
        or len(focus) < 12
    learning_goal = first_goal if (trivial and first_goal) else focus
    return {
        "title": guide.get("title", "Collaborative Planning"),
        "grade_level": guide.get("grade_level", ""),
        "subject": guide.get("subject", ""),
        "topic_focus": focus,
        "benchmarks": summary.get("benchmarks", []),
        "learning_goal": learning_goal,
        "success_criteria": guide.get("success_criteria", []) or [],
        "vocabulary": {
            "tier2": vocab_tiers.get("tier2", []),
            "tier3": vocab_tiers.get("tier3", []),
        },
        "sentence_frames": summary.get("sentence_frames", []),
        "phases": phases,
        "days": _day_slots(lessons),
        "lesson_count": len(lessons),
        "misconception": misc[0] if misc else None,
        "level3": summary.get("level3"),
        "ai_vocab": vocab_tiers.get("ai_generated", False),
    }
