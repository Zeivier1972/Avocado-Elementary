"""Distill a full Collaborative Planning Guide into a one-page Coach Summary —
the essentials a coach presents in planning: the big idea, benchmarks in plain
language, the strategies (with a one-line explanation each), vocabulary, sentence
frames, the top misconceptions to watch for, and a per-lesson "what to model."

Deterministic: it reads the guide JSON that app.ai already produced, so it is
instant and never invents content. app.ai.coach_one_pager_narrative adds an
optional short AI "how to present this" narrative on top."""
from __future__ import annotations


def _phase_problem(phase) -> str:
    if isinstance(phase, dict):
        return phase.get("problem", "") or (
            phase.get("say", [""])[0] if isinstance(phase.get("say"), list) else "")
    return str(phase or "")


def _exit_text(et) -> str:
    if isinstance(et, dict):
        p, a = et.get("problem", ""), et.get("answer", "")
        return f"{p} → {a}" if a else p
    return str(et or "")


def _dedupe(seq):
    seen, out = set(), []
    for x in seq:
        k = str(x).strip().lower()
        if x and k not in seen:
            seen.add(k)
            out.append(x)
    return out


def build_coach_summary(guide: dict) -> dict:
    """Extract the coach-facing essentials from a full planning guide."""
    lessons = guide.get("lessons", []) or []
    qf = guide.get("quick_facts", {}) or {}

    # Benchmarks in plain language (code + short description).
    benchmarks = []
    for c in guide.get("benchmark_clarifications", []) or []:
        benchmarks.append({"code": c.get("code", ""),
                           "description": c.get("description", "")})
    if not benchmarks:
        for code in qf.get("key_benchmarks", []) or []:
            benchmarks.append({"code": code, "description": ""})

    # Vocabulary and sentence frames pulled across every lesson, de-duplicated.
    vocab, frames = [], []
    for L in lessons:
        vocab.extend(L.get("vocabulary", []) or [])
        if L.get("sentence_frame"):
            frames.append(L["sentence_frame"])
    vocab = _dedupe(vocab)
    frames = _dedupe(frames)

    # Which named strategies actually appear, each with a plain explanation the
    # coach can say out loud.
    strategies = []
    has_aces = any(isinstance(L.get(k), (dict, str)) and L.get(k)
                   for L in lessons
                   for k in ("i_do", "we_do", "explore_yall_do", "you_do"))
    has_cubs = any(
        (isinstance(L.get("you_do"), dict) and L["you_do"].get("cubs")) or L.get("cubs")
        for L in lessons)
    has_cpa = any(
        (isinstance(L.get("cpa"), dict) and any(L["cpa"].values())) or
        (isinstance(L.get("i_do"), dict) and L["i_do"].get("concrete"))
        for L in lessons)
    if has_aces:
        strategies.append({
            "name": "ACES Gradual Release",
            "what": "Assemble (I Do) → Connect (We Do) → Explore (Y'all Do, "
                    "collaborative in pairs/groups of 4) → Solo (You Do). The "
                    "teacher models, guides together, lets teams practice, then "
                    "students work independently — responsibility shifts gradually."})
    if has_cpa:
        strategies.append({
            "name": "CPA (Concrete–Pictorial–Abstract)",
            "what": "Build the idea with manipulatives first, then draw it, then "
                    "write the equation — every new concept moves in that order so "
                    "it sticks."})
    if has_cubs:
        strategies.append({
            "name": "CUBS (word-problem routine)",
            "what": "Circle the numbers and what they mean · Underline the question "
                    "· Box the relationship words · Solve & check it's reasonable — "
                    "understand the story before choosing an operation."})

    # Top misconceptions to watch for (topic-level first, then from lessons).
    misc = []
    for m in guide.get("common_misconceptions", []) or []:
        misc.append({"misconception": m.get("misconception", ""),
                     "fix": m.get("fix", "")})
    if not misc:
        for L in lessons:
            for m in L.get("misconceptions", []) or []:
                misc.append({"misconception": m.get("misconception", ""),
                             "fix": m.get("fix", "")})
    misc = [m for m in misc if m["misconception"]][:5]

    # A representative "what Level 3 looks like".
    level3 = None
    for L in lessons:
        l3 = L.get("level3_look_like")
        if isinstance(l3, dict) and l3.get("problem"):
            level3 = l3
            break

    # Per-lesson quick rows: the one thing to model + the exit check.
    lesson_rows = []
    for L in lessons:
        lesson_rows.append({
            "code": L.get("code", ""),
            "title": L.get("title", ""),
            "learning_goal": L.get("learning_goal", ""),
            "model_focus": _phase_problem(L.get("i_do")) or L.get("focus", ""),
            "collab": (L.get("explore_yall_do", {}).get("structure", "")
                       if isinstance(L.get("explore_yall_do"), dict) else ""),
            "exit": _exit_text(L.get("exit_ticket")),
        })

    # Worked models — "what it looks like" so the coach can model it. Pull the
    # I Do example's Concrete → Pictorial → Abstract (falling back to a
    # lesson-level cpa block), plus the problem and the teacher's opening move.
    # Only lessons that actually carry a representation are included.
    models = []
    for L in lessons:
        ido = L.get("i_do") if isinstance(L.get("i_do"), dict) else {}
        cpa = L.get("cpa") if isinstance(L.get("cpa"), dict) else {}
        concrete = ido.get("concrete") or cpa.get("concrete") or ""
        pictorial = ido.get("pictorial") or cpa.get("pictorial") or ""
        abstract = ido.get("abstract") or cpa.get("abstract") or ""
        problem = ido.get("problem") or ""
        say = ido.get("say")
        teacher_move = (say[0] if isinstance(say, list) and say
                        else (say if isinstance(say, str) else ""))
        if concrete or pictorial or abstract or (problem and (say or cpa)):
            models.append({
                "code": L.get("code", ""), "title": L.get("title", ""),
                "problem": problem, "teacher_move": teacher_move,
                "concrete": concrete, "pictorial": pictorial, "abstract": abstract,
            })

    focus = (guide.get("learning_goal") or qf.get("topic_focus")
             or (lessons[0].get("learning_goal") if lessons else "") or "")

    return {
        "title": guide.get("title", "Collaborative Planning Guide"),
        "grade_level": guide.get("grade_level", ""),
        "subject": guide.get("subject", ""),
        "assessment_date": qf.get("assessment_date", ""),
        "focus": focus,
        "lesson_count": len(lessons),
        "benchmarks": benchmarks,
        "vocabulary": vocab,
        "sentence_frames": frames,
        "strategies": strategies,
        "misconceptions": misc,
        "level3": level3,
        "models": models,
        "lessons": lesson_rows,
        "mtr_practices": qf.get("mtr_practices", []) or [],
        "materials": qf.get("materials", []) or [],
    }
