# 03 — Feature List

Organized by module. Each module is independent but communicates with the others through the shared data model ([07](07-database-schema.md)) and event bus ([06](06-system-architecture.md)).

---

## Module: Dashboard
- School health overview (single glance: on-track / watch / at-risk).
- Achievement trends over time (by subject, grade, standard).
- Growth view (cohort and lowest-25%).
- Risk indicators (students, standards, classes trending down).
- Standards needing remediation, ranked by impact.
- Upcoming assessments calendar.
- AI recommendations feed ("This week, focus 3rd grade on B.E.S.T. ELA.3.R.2.2…").

## Module: Student
- Profile: demographics, ESE / ELL / 504 / MTSS tier flags.
- Testing history across all sources.
- Growth charts.
- Strengths & weaknesses (by standard).
- Learning path (mastered → in progress → next).
- Intervention history.
- Current DI group assignment(s).
- Standards: mastered / in progress / current.
- Teacher notes.
- Parent communication log.
- AI-suggested next steps.

## Module: Teacher
- Current class performance snapshot.
- Current-standard performance.
- Student growth (individual and class).
- Lowest and highest standards.
- Upcoming pacing (what's next this week/window).
- Recommended DI groups.
- Suggested mini-lessons and small groups.
- Students needing intervention vs. enrichment, separated.

## Module: Standards
- Every Florida B.E.S.T. Reading & Math standard (K–5).
- Per standard: description, learning targets, prerequisite standards, future standards, common misconceptions, vocabulary, suggested strategies, anchor charts, videos, DI lessons, exit tickets, practice activities, progress-monitoring items, mastery threshold.
- Navigable prerequisite/future knowledge graph.

## Module: Assessment
- Import assessment data (CSV/Excel; OCR for paper).
- Auto-identify lowest / highest standards.
- Growth, mastery, regression, trend analysis.
- Percent correct.
- Comparisons: district / teacher / grade-level / school.

## Module: Differentiated Instruction (the heart)
For every assessment, automatically:
- Identify deficient standards.
- Identify affected students.
- Group students by shared deficiency.
- Generate a **7-Day DI Plan** (cycle below).
- Generate: teacher guide, student packet, manipulative list, independent practice, center activities, homework, quick checks, exit tickets, progress monitoring, reassessment.
- Everything printable (PDF) and editable.

### The 7-Day DI Cycle
| Day | Focus |
|-----|-------|
| 1 | Error analysis · mini-lesson · guided practice |
| 2 | Teacher small group · independent rotation |
| 3 | Hands-on activity · vocabulary · manipulatives |
| 4 | Application · word problems · reading task |
| 5 | Collaborative learning · centers · partner work |
| 6 | Independent practice · progress monitoring |
| 7 | Reassessment · growth report · new recommendation |

## Module: Collaborative Planning (PLC)
Auto-generate: agenda, teacher discussion questions, data discussion, root-cause analysis, instructional strategy, vocabulary focus, student misconceptions, lesson-plan suggestions, exit-ticket analysis, teacher commitments, action items, next-meeting setup.

## Module: Curriculum
- District pacing guides.
- Florida standards alignment.
- District assessment alignment.
- Instructional focus calendars.
- Suggested weekly objectives.
- Priority standards / power standards tagging.

## Module: Reporting
Reports for: student, teacher, grade level, school, principal, district, coach, parent conference, MTSS meeting, leadership meeting, data chat, SIP monitoring.
Every report includes: charts, growth, trend lines, heat maps, color coding, recommendations, risk levels, suggested next steps.
Exports: PDF, Excel, PowerPoint.

## Module: AI Coach
ChatGPT-style assistant inside the platform, grounded in the user's data. Handles requests such as: "What should I teach next?", "How should I reteach this standard?", "Create a small-group lesson", "Generate a center activity", "Generate intervention", "Create a vocabulary lesson", "Generate an anchor chart", "Generate an exit ticket", "Generate an assessment", "Generate a parent letter." Understands district pacing, assessment data, student & teacher history, current standards, and previous interventions.

---

## Cross-cutting features
- **Role-based dashboards & permissions** (principal, AP, coaches, teacher, student-profile, district).
- **Automation engine:** identify standards, create groups, generate packets & reports, suggest interventions, track growth, prep PLCs, create parent reports, generate AI lesson plans, update dashboards, track mastery.
- **Notifications & alerts:** risk thresholds crossed, reassessment due, new data imported.
- **Audit log & compliance controls** (see [00](00-compliance-and-guardrails.md)).
- **Offline-tolerant teacher mode:** cached roster + last DI plan available without connectivity.
