# 05 — User Stories

Format: *As a [persona], I want [capability], so that [outcome].* Grouped by epic. Each story has acceptance criteria (AC). Priority: **M**ust / **S**hould / **C**ould.

---

## Epic A — Data In

**A1 (M).** As a **Teacher**, I want to upload an exit-ticket or FAST file and have it mapped to standards, so that I don't hand-tally results.
- AC: Upload CSV/Excel → guided column mapping (savable) → per-student, per-standard results appear within 60s for a full class.

**A2 (M).** As **Support Staff**, I want to import a whole grade's assessment export at once, so that teachers don't each import separately.
- AC: Bulk import with student de-duplication against district ID; error report for unmatched rows.

**A3 (S).** As a **Teacher**, I want to scan a stack of paper exit tickets, so that paper assessments count too.
- AC: OCR extracts scores; low-confidence items flagged for human confirmation before commit.

**A4 (M).** As a **Principal**, I want demographics, ESE/ELL/504, MTSS tier, attendance, and behavior imported, so that risk analysis is complete.
- AC: These fields load and appear on student profiles and dashboards, gated by RBAC.

## Epic B — Understand the Data

**B1 (M).** As a **Teacher**, I want my class's lowest and highest standards ranked, so that I know where to focus.
- AC: Ranked list per subject with % correct and student counts; click a standard → the students.

**B2 (M).** As a **Coach**, I want growth from PM1→PM2→PM3 by standard and cohort, so that I can see if instruction is working.
- AC: Trend lines and heat maps; lowest-25% cohort isolated.

**B3 (M).** As a **Principal**, I want a school-health overview with risk indicators, so that I know today's priorities.
- AC: One screen: on-track/watch/at-risk, standards needing remediation, students at risk, intervention effectiveness.

**B4 (S).** As an **AP**, I want the "bubble" and lowest-25% students surfaced, so that school-grade-relevant cohorts are obvious.
- AC: Named cohort filters usable across dashboards and reports.

## Epic C — Act on the Data (Differentiated Instruction)

**C1 (M).** As a **Teacher**, I want students auto-grouped by shared deficiency, so that I don't build groups by hand.
- AC: Groups generated from an assessment; teacher can move students and regenerate.

**C2 (M).** As a **Teacher**, I want a complete 7-day DI plan and printable packets per group, so that I can teach tomorrow.
- AC: Teacher guide, student packet, manipulatives, independent practice, centers, homework, quick checks, exit tickets, progress monitoring, reassessment — all editable, all export to PDF.

**C3 (M).** As a **Teacher**, I want Day-7 reassessment to feed back into growth and next steps, so that the cycle closes.
- AC: Reassessment updates mastery, growth charts, and generates the next recommendation.

**C4 (S).** As an **ELL Teacher**, I want DI materials language-scaffolded to proficiency level, so that they fit my students.
- AC: Generated materials adapt when ELL level is present.

**C5 (S).** As an **Interventionist**, I want cross-class intervention rosters by standard, so that I can pull the right kids.
- AC: Roster spans teachers; progress monitoring tracked per student.

## Epic D — Collaborate (PLC)

**D1 (S).** As a **Coach**, I want a full PLC agenda auto-drafted from a grade's data, so that I spend PLC coaching, not compiling.
- AC: Agenda, data discussion, root-cause analysis, strategy, misconceptions, lesson suggestions, commitments, action items generated and editable.

**D2 (S).** As a **Coach**, I want commitments/action items tracked across meetings, so that follow-through is visible.
- AC: Open items carry forward; status visible next meeting.

## Epic E — Report

**E1 (M).** As a **Teacher**, I want a parent-conference report per student, so that conferences are data-rich.
- AC: One-click report with growth, standards, next steps; exports to PDF.

**E2 (S).** As a **Principal**, I want SIP-monitoring and leadership reports, so that accountability reporting is fast.
- AC: Reports export to PDF/Excel/PowerPoint with charts, heat maps, risk levels.

**E3 (M).** As a **District Admin**, I want comparable cross-school reports, so that I can allocate support.
- AC: Aggregated, RBAC-respecting; drill-down where permitted.

## Epic F — AI Coach

**F1 (M).** As a **Teacher**, I want to ask "What should I teach next?" and get an answer grounded in my data, so that I trust it.
- AC: Response cites the driving standards/assessment; is editable; labeled AI-generated.

**F2 (M).** As a **Teacher**, I want to say "Create a small-group lesson for these students on this standard," so that materials are instant.
- AC: Generates standards-aligned, grade-appropriate material referencing the real group.

**F3 (M).** As a **Teacher**, I want to generate a parent letter, so that communication is easy — but I want to send it myself.
- AC: Draft produced; **never auto-sent**; human reviews and sends.

## Epic G — Trust, Access & Compliance

**G1 (M).** As a **Principal**, I want teachers to see only their rosters, so that student privacy is protected.
- AC: RBAC enforced at the query layer; verified by test.

**G2 (M).** As a **District Admin/DPO**, I want every student-record access logged, so that we can audit.
- AC: Immutable audit log: actor, record, action, timestamp, purpose.

**G3 (M).** As a **Compliance Officer**, I want assurance that student PII is never used to train third-party models, so that we meet FERPA/state law.
- AC: LLM calls run under zero-retention/no-training config; de-identified prompts where possible; documented.

**G4 (S).** As a **Teacher** in a classroom with poor Wi-Fi, I want my roster and last DI plan available offline, so that connectivity doesn't block me.
- AC: Cached read-only access to roster + latest DI plan when offline.
