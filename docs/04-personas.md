# 04 — User Personas

Each persona lists their core job, what they need from Avocado, their primary dashboard, and their success metric. Personas drive the RBAC model in [06](06-system-architecture.md) and the dashboards in [08](08-dashboard-designs.md).

---

### 1. District Administrator — "Denise"
- **Role:** Regional/district academic leadership overseeing many schools.
- **Job:** Spot schools trending away from an A; allocate support; report up.
- **Needs:** Cross-school aggregates, comparable metrics, early-warning on risk, drill-down without seeing more PII than necessary.
- **Primary view:** District dashboard.
- **Access scope:** Aggregates across schools; drill-down to school level; student-level only where policy permits.
- **Success:** No school is surprised by a grade drop; support arrives before the slide.

### 2. Principal — "Paula"
- **Role:** Instructional leader of the school; owns the school grade.
- **Job:** Keep the whole school on track; know who and what is at risk today.
- **Needs:** One-glance school health, risk indicators, standards failing school-wide, intervention effectiveness, SIP monitoring.
- **Primary view:** Principal dashboard.
- **Access scope:** Entire school.
- **Success:** Maintains/achieves an A; can answer any board or district question with two clicks.

### 3. Assistant Principal — "Andre"
- **Role:** Operational instructional leadership, often by grade band or subject.
- **Job:** Execute the principal's plan; manage MTSS; monitor specific grades.
- **Needs:** Grade-band drill-down, MTSS tracking, teacher-level support signals.
- **Primary view:** AP dashboard (school with grade-band focus).
- **Access scope:** School (often filtered to assigned grades).
- **Success:** MTSS runs on time; struggling grades get targeted support.

### 4. Reading Coach — "Rosa"
- **Role:** ELA instructional coach.
- **Job:** Improve reading instruction; run ELA PLCs; coach teachers.
- **Needs:** ELA standard analysis across grades, auto PLC prep, DI plan review, teacher coaching signals.
- **Primary view:** Reading Coach dashboard.
- **Access scope:** ELA data across assigned grades/teachers.
- **Success:** ELA lowest-25% growth up; PLCs are data-driven and prepped in minutes.

### 5. Mathematics Coach — "Marcus"
- **Role:** Math instructional coach. (Same shape as Reading Coach, Math domain.)
- **Primary view:** Math Coach dashboard.
- **Access scope:** Math data across assigned grades/teachers.
- **Success:** Math proficiency & growth up.

### 6. Instructional Coach (general) — "Ingrid"
- **Role:** Cross-subject coach.
- **Needs:** Both subjects, teacher development focus, DI and PLC tools.
- **Access scope:** Assigned teachers, both subjects.

### 7. Teacher — "Tomás" (primary user)
- **Role:** Classroom teacher, K–5.
- **Job:** Teach the right thing to the right kids tomorrow.
- **Needs:** Class snapshot, lowest standards, auto-formed groups, ready-to-print DI packets, exit-ticket import, AI Coach, intervention vs. enrichment lists.
- **Primary view:** Teacher dashboard.
- **Access scope:** Own roster only.
- **Success:** Saves 3–5 hrs/week; students grow; walks in prepared.

### 8. Interventionist — "Iris"
- **Role:** Pull-out/push-in intervention specialist.
- **Job:** Deliver targeted intervention to Tier 2/3 students across classes.
- **Needs:** Cross-class intervention rosters, progress monitoring, standard-specific plans.
- **Access scope:** Assigned intervention students across teachers.
- **Success:** Tier movement (3→2→1); documented progress for MTSS.

### 9. ESE Teacher — "Elena"
- **Role:** Exceptional Student Education.
- **Job:** Serve students with IEPs; align instruction to goals.
- **Needs:** ESE flags, accommodations context, standard-aligned differentiated plans, progress monitoring aligned to IEP-relevant standards.
- **Access scope:** Assigned ESE caseload.
- **Compliance note:** IEP content is highly sensitive; Avocado references status and progress, not full IEP legal documents, unless explicitly authorized.

### 10. ELL Teacher — "Liang"
- **Role:** English Language Learner support.
- **Needs:** ELL flags & proficiency level, language-scaffolded DI materials, vocabulary focus.
- **Access scope:** Assigned ELL caseload.

### 11. Support Staff — "Sam"
- **Role:** Data clerk / office / paraprofessional.
- **Job:** Import data, print packets, maintain rosters.
- **Needs:** Import tools, print queue, roster maintenance — **without** broad analytical or PII access beyond task.
- **Access scope:** Task-scoped, least-privilege.

---

## Persona → access matrix (summary)

| Persona | Scope | Subjects | Sees student PII |
|---------|-------|----------|------------------|
| District Admin | Multi-school | Both | Aggregate; limited drill-down |
| Principal | School | Both | Yes (school) |
| AP | School (grade-filtered) | Both | Yes (assigned) |
| Reading Coach | Grades/teachers | ELA | Yes (assigned) |
| Math Coach | Grades/teachers | Math | Yes (assigned) |
| Instructional Coach | Assigned teachers | Both | Yes (assigned) |
| Teacher | Own roster | Own classes | Yes (own) |
| Interventionist | Caseload | As assigned | Yes (caseload) |
| ESE Teacher | Caseload | As assigned | Yes (caseload) |
| ELL Teacher | Caseload | As assigned | Yes (caseload) |
| Support Staff | Task-scoped | n/a | Minimal / least-privilege |

This matrix is enforced at the data-access layer, not just the UI. See [06](06-system-architecture.md) §RBAC.
