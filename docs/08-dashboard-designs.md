# 08 — Dashboard Designs (Wireframes)

Low-fidelity, text-based wireframes for each role's dashboard. The visual language (per [01](01-executive-vision.md), Product Principle #1) is: **every panel ends in a recommended action, not just a chart.** Design references: Power BI (density), Notion (calm structure), Canva/Apple (polish), Google Classroom (teacher familiarity).

Shared conventions:
- **Color coding:** 🟢 on-track · 🟡 watch · 🔴 at-risk. Consistent everywhere.
- **Top bar:** role + scope selector, global search, AI Coach launcher, notifications.
- **Every risk item is clickable** and drills to the underlying students/standards.

---

## Principal Dashboard

```
┌───────────────────────────────────────────────────────────────────────────┐
│ Avocado · Avocado Elementary · Principal   [🔍]  [🤖 AI Coach]  [🔔 3]      │
├───────────────────────────────────────────────────────────────────────────┤
│  SCHOOL HEALTH                          │  RISK INDICATORS                  │
│  ┌─────────┐ ELA  Proficiency 58% 🟡    │  🔴 12 students below on 3+ std   │
│  │  GRADE  │ Math Proficiency 61% 🟢    │  🔴 Grade 4 Math trending down    │
│  │  PROJ:  │ Lowest-25% growth ▲ +4 🟢  │  🟡 8 reassessments overdue       │
│  │   B→A   │ Attendance 94% 🟢          │  → [View all risks]               │
│  └─────────┘                            │                                   │
├─────────────────────────────────────────┼───────────────────────────────────┤
│  STANDARDS NEEDING REMEDIATION (school)  │  INTERVENTION EFFECTIVENESS       │
│  1. ELA.3.R.2.2  41% 🔴  (3 classes)     │  Tier 3→2 movement: 18 students   │
│  2. MA.4.NSO.2.1 44% 🔴  (2 classes)     │  Active DI plans: 27  🟢          │
│  3. ELA.5.R.1.1  49% 🟡                  │  Stalled plans: 3 🔴  → [review]  │
│  → [Generate school remediation plan]    │                                   │
├─────────────────────────────────────────┴───────────────────────────────────┤
│  ACHIEVEMENT TREND (PM1→PM2→PM3)  [heat map by grade × standard]             │
│  AI RECOMMENDATION: "Focus this week on Grade 4 Math NSO; 2 classes drive    │
│  the school gap. Suggested PLC + DI plan ready. → [Open]"                    │
└───────────────────────────────────────────────────────────────────────────┘
```

## Assistant Principal Dashboard
Same shell as Principal, **filtered to assigned grade band**, plus an **MTSS panel**: students by tier, overdue tier reviews, tier-movement trend, and a "MTSS meeting pack" generator.

---

## Reading Coach / Math Coach Dashboard

```
┌───────────────────────────────────────────────────────────────────────────┐
│ Reading Coach · Grades 3–5 · ELA          [🔍] [🤖] [🔔]                     │
├───────────────────────────────────────────────────────────────────────────┤
│  STANDARDS ACROSS MY GRADES              │  TEACHERS NEEDING SUPPORT         │
│  Lowest: ELA.3.R.2.2 🔴, ELA.4.C.1 🟡    │  🔴 Rm 210 – 3 std below grade    │
│  Highest: ELA.5.V.1 🟢                    │  🟡 Rm 118 – DI plan stalled      │
│  → [Standard deep-dive]                   │  → [Schedule coaching]            │
├─────────────────────────────────────────┼───────────────────────────────────┤
│  PLC PREP (auto-drafted)                 │  DI PLANS TO REVIEW               │
│  Grade 3 ELA · Thu 8:00                  │  6 draft plans awaiting review    │
│  Agenda ✓  Data ✓  Root-cause ✓          │  → [Review & approve]             │
│  → [Open PLC pack]                        │                                   │
└───────────────────────────────────────────────────────────────────────────┘
```

The **Instructional Coach** view is the same with both subjects enabled.

---

## Teacher Dashboard (primary user — most-used screen)

```
┌───────────────────────────────────────────────────────────────────────────┐
│ Mr. Tomás · Grade 3 · Rm 210            [🔍] [🤖 Ask AI] [🔔] [🖨 Print]     │
├───────────────────────────────────────────────────────────────────────────┤
│  MY CLASS RIGHT NOW           │  WHAT TO TEACH NEXT (AI)                     │
│  Proficiency  ELA 54% 🟡       │  "Reteach ELA.3.R.2.2 — 7 students below.    │
│  Growth ▲ +3 since PM2 🟢      │   Groups formed, 7-day plan ready."          │
│                               │  → [Open DI plan]  → [Print packets]         │
├───────────────────────────────┼───────────────────────────────────────────────┤
│  LOWEST STANDARDS             │  RECOMMENDED DI GROUPS                        │
│  ELA.3.R.2.2  41% 🔴 (7 kids) │  🔴 Group A (7): ELA.3.R.2.2  → [plan]       │
│  ELA.3.C.1.4  52% 🟡 (5 kids) │  🟡 Group B (5): ELA.3.C.1.4  → [plan]       │
│  → [click standard → students]│  🟢 Enrichment (6): ready for ELA.4 preview  │
├───────────────────────────────┴───────────────────────────────────────────────┤
│  NEEDS INTERVENTION (6)   |   NEEDS ENRICHMENT (6)   |   UPCOMING PACING: Wk 5 │
│  Ana, Luis, ...           |   Sofia, Ben, ...        |   ELA.3.R.3.1 (Fri)     │
│  UPLOAD: [Import exit ticket ⬆]   —  turns Friday's quiz into Monday's groups │
└───────────────────────────────────────────────────────────────────────────┘
```

Design intent: a teacher lands here and the **very next action is always visible** — open the plan, print the packets, or import the latest data.

---

## Student Profile

```
┌───────────────────────────────────────────────────────────────────────────┐
│ ← Ana R. · Grade 3 · Rm 210    Flags: [ELL L3] [MTSS T2]      [🖨 Report]    │
├───────────────────────────────────────────────────────────────────────────┤
│  GROWTH (PM1→PM2→PM3)  [line chart 🟢 trending up]                          │
│  STRENGTHS: ELA.3.V.1 🟢, ELA.3.R.1.1 🟢                                     │
│  WEAKNESSES: ELA.3.R.2.2 🔴, ELA.3.C.1.4 🟡                                  │
├─────────────────────────────────────────┬───────────────────────────────────┤
│  LEARNING PATH                           │  INTERVENTION HISTORY             │
│  Mastered → In progress → Next           │  T2 · ELA.3.R.2.2 · 3 wks · ▲     │
│  ● ● ● ○ ○  (ELA.3.R sequence)           │  Current DI group: A              │
├─────────────────────────────────────────┼───────────────────────────────────┤
│  TEACHER NOTES / PARENT LOG              │  AI SUGGESTED NEXT STEPS          │
│  "Responds well to visual scaffolds."    │  "Continue T2; add vocab pre-teach;│
│                                          │   language-scaffold for ELL L3."   │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## District Dashboard

```
┌───────────────────────────────────────────────────────────────────────────┐
│ District · Region · Academic Admin        [🔍] [🤖] [🔔]                     │
├───────────────────────────────────────────────────────────────────────────┤
│  SCHOOLS AT A GLANCE (sortable)                                             │
│  School            Grade Proj  ELA   Math  Low-25% Growth  Risk            │
│  Avocado Elem      B → A ▲      58%🟡 61%🟢  +4 🟢          watch           │
│  ...               C → C ▬      49%🔴 51%🟡  +1 🟡          at-risk 🔴      │
│  → [drill to school]  (student PII gated by policy)                         │
├───────────────────────────────────────────────────────────────────────────┤
│  DISTRICT STANDARD HOTSPOTS  [heat map school × standard]                    │
│  EARLY WARNING (AI): "3 schools trending away from projected grade. → View" │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## Design system notes
- **Cards over tables** where possible; tables only for dense comparisons.
- **Progressive disclosure:** overview → drill-down → student, never everything at once.
- **Consistent risk color semantics** across every role.
- **Print affordance** on any student- or group-level view (elementary = paper).
- **AI Coach launcher** persistent in the top bar on every screen, pre-loaded with the current context (roster/standard in view).
- **Accessibility:** color never the sole signal (icons + labels accompany 🟢🟡🔴); WCAG 2.1 AA.

High-fidelity mockups (Figma) are a Phase 4/5 deliverable; these wireframes define layout and information priority for that work.
