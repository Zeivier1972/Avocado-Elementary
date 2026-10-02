# 07 — Database Schema

A logical relational schema (PostgreSQL). Presented as entities, key columns, and relationships. This is a design artifact, not migration DDL — but it is deliberately concrete so that migrations follow directly. Every student-scoped table carries `tenant_id` (district) for multi-tenant Row-Level Security.

## Conventions
- Primary keys are UUIDs (`id`).
- `tenant_id` on every school/student-scoped row → RLS isolation.
- `created_at`, `updated_at` audit timestamps on all tables.
- Soft-delete via `deleted_at` where retention rules require recoverability; hard-delete supported for district requests.

---

## Organization & Identity

### `districts`
`id, name, state, standards_framework_id, accountability_model_id, created_at`

### `schools`
`id, tenant_id(district), name, grade_range, sip_meta(jsonb), created_at`

### `users`
`id, tenant_id, name, email, sso_subject, status, created_at`
- Authenticated via external SSO (`sso_subject`); no password store.

### `roles`
`id, key(enum: district_admin|principal|ap|reading_coach|math_coach|instructional_coach|teacher|interventionist|ese_teacher|ell_teacher|support_staff), name`

### `user_roles` (assignment + scope)
`id, user_id, role_id, school_id, scope(jsonb: {grades:[], subjects:[], class_ids:[], caseload_student_ids:[]})`
- Encodes the persona→access matrix from [04](04-personas.md). RBAC is computed from these rows.

### `audit_log` (append-only)
`id, tenant_id, actor_user_id, action, entity_type, entity_id, purpose, ip, occurred_at`
- Immutable; every student-record access recorded.

---

## Students & Enrollment

### `students`
`id, tenant_id, district_student_id(unique), first_name, last_name, dob, grade_level, demographics(jsonb), created_at`
- `district_student_id` is the reconciliation key on import.

### `student_flags` (program status, time-boxed)
`id, student_id, type(enum: ESE|ELL|504|MTSS_TIER), value(jsonb: {tier, level, plan_ref}), effective_from, effective_to`
- ESE/504 reference *status*, not full legal IEP docs (compliance).

### `enrollments`
`id, student_id, school_id, class_id, school_year, status, start_date, end_date`

### `classes`
`id, tenant_id, school_id, teacher_user_id, name, subject(enum: ELA|MATH|OTHER), grade_level, period, school_year`

### `attendance` / `behavior` (imported context)
`attendance: id, student_id, date, status, minutes` · `behavior: id, student_id, date, type, severity, notes_ref`

---

## Standards & Curriculum

### `standards_frameworks`
`id, name(e.g., "FL B.E.S.T."), state, version`
- Framework is data → enables multi-state ([12](12-future-expansion.md)).

### `standards`
`id, framework_id, subject, grade_level, code(e.g., "ELA.3.R.2.2"), description, mastery_threshold`

### `standard_details`
`id, standard_id, learning_targets(jsonb[]), misconceptions(jsonb[]), vocabulary(jsonb[]), strategies(jsonb[]), mastery_threshold`

### `standard_prerequisites` (graph edges)
`id, standard_id, prerequisite_standard_id` · plus derived "future standards" via reverse edges.

### `standard_resources`
`id, standard_id, type(enum: anchor_chart|video|di_lesson|exit_ticket|practice|pm_item), title, uri/content_ref, source`

### `pacing_guides`
`id, tenant_id, subject, grade_level, school_year, windows(jsonb: [{week, standards[], objectives, priority}])`

### `priority_standards`
`id, tenant_id, standard_id, is_power_standard(bool), rationale`

---

## Assessments

### `assessment_definitions`
`id, tenant_id, name, source(enum: FAST_PM1|FAST_PM2|FAST_PM3|IREADY_READING|IREADY_MATH|DISTRICT_TOPIC|DISTRICT_INTERIM|TEACHER_MADE|EXIT_TICKET|FLUENCY|DIAGNOSTIC), subject, grade_level, administered_on, meta(jsonb)`

### `assessment_items`
`id, assessment_definition_id, item_number, standard_id, max_points`
- Links each item to the standard it measures — the backbone of standard-level analysis.

### `assessment_results` (per student, per assessment)
`id, tenant_id, student_id, assessment_definition_id, scale_score, percent_correct, administered_on, imported_at, source_file_ref`

### `item_responses` (per student, per item)
`id, assessment_result_id, assessment_item_id, standard_id, points_earned, max_points, correct(bool)`
- Enables per-standard mastery even from a single test.

### `import_batches` (provenance & idempotency)
`id, tenant_id, uploaded_by, source, mapping_template_id, row_count, error_report(jsonb), status, created_at`

### `mapping_templates` (savable column maps)
`id, tenant_id, source, column_map(jsonb), created_by`

---

## Analytics (materialized / derived)

### `standard_mastery` (per student × standard, current)
`id, tenant_id, student_id, standard_id, status(enum: mastered|in_progress|not_started|deficient), mastery_pct, last_assessed_on, trend(enum: up|flat|down)`

### `standard_rollups` (aggregates by scope)
`id, tenant_id, scope_type(class|grade|school|district), scope_id, standard_id, subject, avg_pct, mastery_rate, rank, window`

### `growth_snapshots`
`id, tenant_id, student_id, subject, from_admin, to_admin, delta, cohort(enum: all|lowest_25|bubble), computed_at`

### `risk_indicators`
`id, tenant_id, scope_type, scope_id, indicator, level(enum: on_track|watch|at_risk), drivers(jsonb), computed_at`

---

## Differentiated Instruction

### `di_groups`
`id, tenant_id, class_id, subject, standard_id(focus), created_by, generated_from_assessment_id, status, created_at`

### `di_group_members`
`id, di_group_id, student_id, added_by(system|teacher)`
- Teacher can override system grouping.

### `di_plans` (the 7-day cycle)
`id, di_group_id, standard_id, current_day(1..7), status(draft|active|completed), created_at`

### `di_plan_artifacts`
`id, di_plan_id, day(1..7), type(enum: teacher_guide|student_packet|manipulative_list|independent_practice|center_activity|homework|quick_check|exit_ticket|progress_monitoring|reassessment|mini_lesson), content(jsonb), pdf_ref, ai_generated(bool), edited_by`
- `ai_generated` + `edited_by` preserve the human-in-the-loop record.

### `interventions`
`id, tenant_id, student_id, standard_id, tier, provider_user_id, di_plan_id?, start_date, end_date, outcome, progress(jsonb)`

---

## Collaborative Planning (PLC)

### `plc_meetings`
`id, tenant_id, school_id, grade_level, subject, scheduled_for, facilitator_user_id, generated_agenda(jsonb), status`

### `plc_action_items`
`id, plc_meeting_id, owner_user_id, description, due_date, status, carried_from_meeting_id?`
- Carry-forward supports cross-meeting tracking.

---

## Reporting & Communication

### `reports`
`id, tenant_id, type(student|teacher|grade|school|district|coach|parent_conf|mtss|leadership|data_chat|sip), scope_id, generated_by, format(pdf|xlsx|pptx), file_ref, created_at`

### `parent_communications`
`id, tenant_id, student_id, drafted_by(system|user), draft_content, reviewed_by, sent_by, sent_at, channel`
- **Never** `sent_at` without `reviewed_by` + `sent_by` (human-in-the-loop, compliance).

### `teacher_notes`
`id, tenant_id, student_id, author_user_id, note, visibility, created_at`

---

## AI

### `ai_conversations`
`id, tenant_id, user_id, context(jsonb: scope, roster refs), created_at`

### `ai_messages`
`id, conversation_id, role(user|assistant|system), content, grounding_refs(jsonb: standards/assessments cited), model, created_at`
- `grounding_refs` enforces "cite what drove this."

### `ai_generation_jobs`
`id, tenant_id, requested_by, type, input_refs(jsonb, de-identified), status, output_ref, created_at`

---

## Entity relationship summary (textual ERD)

```
districts 1─* schools 1─* classes 1─* enrollments *─1 students
students 1─* assessment_results *─1 assessment_definitions 1─* assessment_items *─1 standards
assessment_results 1─* item_responses *─1 assessment_items
students 1─* standard_mastery *─1 standards
standards 1─* standard_prerequisites *─1 standards        (self-referential graph)
classes 1─* di_groups 1─* di_group_members *─1 students
di_groups 1─1 di_plans 1─* di_plan_artifacts
schools 1─* plc_meetings 1─* plc_action_items
users *─* roles (via user_roles, with scope)
* (student access) ─> audit_log
```

## Design notes
- **Item-level responses are the unit that makes standard-level analysis possible** even from a single teacher-made exit ticket — this is what powers automatic deficiency detection.
- **`jsonb` for pedagogical content** (learning targets, misconceptions, artifacts) keeps the schema stable while content evolves; structured columns are reserved for anything queried/aggregated.
- **Framework & accountability model as tables** is the single most important choice for future multi-state expansion.
