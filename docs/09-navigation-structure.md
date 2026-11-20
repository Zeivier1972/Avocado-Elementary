# 09 — Navigation Structure

Navigation is **role-adaptive**: the same information architecture, filtered and reordered by persona. A teacher's most-used item is DI; a principal's is the school dashboard; a coach's is PLC + standards.

## Global shell (all roles)

```
┌──────────────────────────────────────────────────────────────┐
│ TOP BAR:  [Avocado logo]  Scope selector ▾   🔍 Search        │
│           🤖 AI Coach   🔔 Notifications   👤 Profile/Role     │
├──────────┬───────────────────────────────────────────────────┤
│ LEFT NAV │  MAIN CONTENT (role dashboard by default)          │
│ (role-   │                                                    │
│  aware)  │                                                    │
└──────────┴───────────────────────────────────────────────────┘
```

- **Scope selector** changes what "my data" means within the user's permitted scope (e.g., a coach switches grade; a principal stays school-wide; a teacher switches class/period).
- **AI Coach** is always one click away and inherits the current screen's context.

## Primary navigation (full map)

```
Home / Dashboard        → role-specific (see 08)
Students                → roster/search → Student Profile
   └ Student Profile        (growth, standards, interventions, notes, AI next steps)
Classes                 → class list → class analysis
Assessments
   ├ Import                (upload, mapping templates, OCR, batches)
   ├ Results & Analysis    (rankings, growth, comparisons, heat maps)
   └ Assessment library    (definitions, item→standard maps)
Differentiated Instruction
   ├ Recommended Groups
   ├ DI Plans              (7-day cycle, per group)
   └ Packets / Print queue
Standards
   ├ Browse (K–5, ELA/Math)
   ├ Standard detail       (targets, prereqs, misconceptions, resources)
   └ Prerequisite graph
Curriculum
   ├ Pacing guides
   ├ Instructional focus calendar
   └ Priority / power standards
Collaborative Planning (PLC)
   ├ Meetings & agendas
   └ Action items tracker
Reports
   ├ Generate (student/teacher/grade/school/district/parent/MTSS/SIP…)
   └ Export history (PDF/Excel/PPTX)
AI Coach                → full conversation view (also available as overlay)
Admin (role-gated)
   ├ Users & roles/scopes
   ├ Data sources & integrations
   ├ Audit log
   └ District/school settings (standards framework, accountability model)
```

## Role-adaptive left-nav ordering

| Role | Nav emphasis (top → down) |
|------|---------------------------|
| **Teacher** | Dashboard · **DI** · Assessments(Import) · Students · Standards · Reports · AI Coach |
| **Coach** | Dashboard · **PLC** · **Standards** · DI (review) · Assessments · Reports · AI Coach |
| **Principal / AP** | **Dashboard** · Reports · Assessments · DI (oversight) · PLC · Students · Admin |
| **Interventionist / ESE / ELL** | **Students (caseload)** · DI · Assessments · Standards · Reports |
| **District Admin** | **District Dashboard** · Reports · Schools · Admin |
| **Support Staff** | **Assessments (Import)** · Print queue · Roster maintenance (task-scoped) |

Items a role cannot access are **hidden, not just disabled**, and the underlying routes are enforced server-side by RBAC ([06](06-system-architecture.md)).

## Key user flows (click paths)

**Teacher — data to instruction (the money path):**
`Dashboard → "Import exit ticket" → map columns → Results → "Recommended Groups" → open DI Plan → edit → Print packets` — target: **under 5 minutes**.

**Coach — PLC prep:**
`PLC → New meeting (grade+subject) → auto-drafted agenda → edit → share pack → track action items`.

**Principal — school check:**
`Dashboard → click a 🔴 risk → drill to standard/students → "Generate remediation plan" → assign to teacher/coach`.

**Any role — ask AI:**
`🤖 (any screen) → "What should I teach next?" → grounded answer with cited standards → "generate packet" → lands in DI Plans`.

## Mobile / responsive
- PWA; dashboards reflow to single-column cards.
- Teacher offline mode exposes only **Students (roster)** and the **latest DI Plan/packets** (cached, read-only).
- Print actions defer/queue when offline and flush on reconnect.

## Search
Global search spans students (within scope), standards (by code or description), classes, and reports. Results respect RBAC scope. Standard codes (e.g., `ELA.3.R.2.2`) are first-class search tokens.
