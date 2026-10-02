# 02 — Product Requirements Document (PRD)

## 1. Overview

Avocado is a multi-tenant, role-based web application (with mobile-responsive and offline-tolerant behavior) that ingests elementary assessment and student data, analyzes it against Florida B.E.S.T. standards, and produces differentiated instruction, progress monitoring, reports, and AI coaching. This PRD defines scope, requirements, and acceptance criteria for v1 and beyond.

## 2. Goals & non-goals

### Goals
- Reduce time-to-instruction from days to minutes.
- Give every role a single, action-oriented view of the data relevant to them.
- Automate DI grouping, packet generation, PLC prep, and reporting.
- Keep every recommendation standards-aligned, editable, and compliant.

### Non-goals (v1)
- Not a Student Information System (SIS) of record — Avocado reads from the SIS, it is not the source of truth for enrollment.
- Not a testing platform — it ingests assessment results, it does not administer FAST/i-Ready.
- Not a gradebook of record.
- No direct student accounts in v1 (teacher-mediated; revisit under COPPA in later phases).
- Not automating any high-stakes eligibility, placement, or retention decision.

## 3. Personas (summary — full in [04](04-personas.md))

District Admin, Principal, Assistant Principal, Reading Coach, Math Coach, Instructional Coach, Teacher, Interventionist, ESE Teacher, ELL Teacher, Support Staff.

## 4. Functional requirements by module

Requirements use MoSCoW priority: **M** = Must (v1), **S** = Should (v1.x), **C** = Could (later), **W** = Won't (this cycle).

### 4.1 Data Ingestion & Integration
| ID | Requirement | Priority |
|----|-------------|----------|
| ING-1 | Import assessment results via CSV/Excel upload (FAST PM1/2/3, i-Ready, district topic/interim exports). | M |
| ING-2 | Map imported columns to Avocado's schema via a guided, savable mapping template. | M |
| ING-3 | De-duplicate and reconcile students against a district ID. | M |
| ING-4 | OCR-assisted import of scanned exit tickets / paper assessments. | S |
| ING-5 | Direct API/SFTP integration with district data feeds (SIS, i-Ready). | C |
| ING-6 | Import attendance, behavior, demographics, ESE/ELL/504, MTSS tier. | M |

### 4.2 Assessment Analysis
| ID | Requirement | Priority |
|----|-------------|----------|
| ASS-1 | For any assessment, compute per-standard % correct, mastery, and gaps. | M |
| ASS-2 | Rank lowest and highest standards by class, grade, and school. | M |
| ASS-3 | Compute growth and regression across administrations (PM1→PM2→PM3). | M |
| ASS-4 | Comparison views: student vs. class vs. grade vs. school vs. district. | M |
| ASS-5 | Trend lines and heat maps over time. | M |
| ASS-6 | Flag the "bubble" and lowest-25% cohorts relevant to school grade. | S |

### 4.3 Differentiated Instruction (the core)
| ID | Requirement | Priority |
|----|-------------|----------|
| DI-1 | Auto-identify deficient standards from an assessment. | M |
| DI-2 | Auto-identify and group students by shared deficiency. | M |
| DI-3 | Generate a 7-day DI plan per group (model in [03](03-feature-list.md)). | M |
| DI-4 | Generate teacher guide, student packet, manipulative list, independent practice, centers, homework, quick checks, exit tickets, progress monitoring, reassessment. | M |
| DI-5 | Every artifact is printable (PDF) and editable before printing. | M |
| DI-6 | Teacher can adjust group membership and regenerate. | M |
| DI-7 | Reassessment (Day 7) feeds back into growth and next recommendation. | M |

### 4.4 Standards
| ID | Requirement | Priority |
|----|-------------|----------|
| STD-1 | Full Florida B.E.S.T. ELA & Math standards library (K–5). | M |
| STD-2 | Each standard: description, learning targets, prerequisites, future standards, misconceptions, vocabulary, strategies, resources, mastery threshold. | M |
| STD-3 | Prerequisite/future graph navigable in UI. | S |

### 4.5 Dashboards & Reporting
| ID | Requirement | Priority |
|----|-------------|----------|
| DsH-1 | Role-specific dashboards (principal, AP, coaches, teacher, student-profile, district). | M |
| REP-1 | Generate reports for student/teacher/grade/school/district/coach/parent/MTSS/leadership. | M |
| REP-2 | Export to PDF, Excel, and PowerPoint. | S (PDF=M) |
| REP-3 | Charts, growth, trend lines, heat maps, color coding, risk levels, next steps in every report. | M |

### 4.6 Collaborative Planning (PLC)
| ID | Requirement | Priority |
|----|-------------|----------|
| PLC-1 | Auto-generate PLC agenda, data discussion, root-cause analysis, strategy, misconceptions, lesson suggestions, commitments, action items. | S |
| PLC-2 | Track commitments/action items across meetings. | S |

### 4.7 Curriculum
| ID | Requirement | Priority |
|----|-------------|----------|
| CUR-1 | Store district pacing guides & instructional focus calendars. | M |
| CUR-2 | Align recommendations to the current pacing window & priority/power standards. | S |

### 4.8 AI Coach
| ID | Requirement | Priority |
|----|-------------|----------|
| AI-1 | Conversational assistant scoped to the user's role, roster, and data. | M |
| AI-2 | Generate reteach plans, small groups, centers, interventions, vocabulary, anchor charts, exit tickets, assessments, parent letters on request. | M |
| AI-3 | Ground responses in the user's actual data, pacing, and standards. | M |
| AI-4 | All output labeled AI-generated, editable, and never auto-sent externally. | M |

## 5. Non-functional requirements

- **Security/Privacy:** per [00](00-compliance-and-guardrails.md). RBAC, audit log, encryption at rest & in transit, US hosting, no PII in model training.
- **Performance:** dashboards render < 2s on typical school Wi-Fi; assessment import of a full grade (~150 students) processes < 60s; DI generation returns a first draft < 30s.
- **Availability:** 99.5%+ target; graceful offline read for teachers (cached roster + last DI plan).
- **Accessibility:** WCAG 2.1 AA.
- **Scalability:** designed for 1 school → 1 district (300+ schools) without re-architecture; multi-tenant isolation.
- **Usability:** a teacher can go from login to a generated DI plan in under 5 minutes with no training.
- **Auditability:** every student-record access logged.

## 6. Assumptions & dependencies

- District data-sharing agreement and approved-vendor status are pursued in parallel (gates live-data pilot).
- Standards content (B.E.S.T.) and pacing guides are available for licensing/loading.
- LLM provider available under zero-retention/no-training terms.

## 7. Acceptance criteria (v1 exit)

1. A teacher uploads a FAST PM or exit-ticket file, and within minutes sees ranked deficient standards, auto-formed groups, and a downloadable 7-day DI packet.
2. A principal sees a live school-health dashboard with risk indicators and standards needing remediation.
3. A coach generates a complete PLC agenda from a grade's data.
4. All of the above run on synthetic/de-identified data with full RBAC and audit logging in place.
5. AI Coach answers "What should I teach next?" grounded in that teacher's uploaded data.

## 8. Release strategy

- **v0 (Design):** this repository.
- **v1 (Pilot MVP):** Assessment import + analysis + DI generation + teacher & principal dashboards + AI Coach, on synthetic data, single school.
- **v1.x:** PLC module, full reporting exports, OCR import, live-data pilot (post-agreement).
- **v2:** District rollout, API integrations, mobile app, offline sync.
- **v3+:** Multi-state configurability (see [12](12-future-expansion.md)).
