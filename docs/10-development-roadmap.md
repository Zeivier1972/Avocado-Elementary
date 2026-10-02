# 10 — Development Roadmap

A phased roadmap that de-risks the two hardest problems early (data compliance and the DI generation loop) and defers scale until value is proven. Two tracks run in parallel: a **Product/Engineering track** and a **Compliance/District track** — because live-data access gates on the latter, not the former.

## Guiding sequencing principle
Prove the core value — *data in → differentiated instruction out* — on **synthetic data** before spending on integrations, exports, and scale. The pilot with live district data is unlocked by the compliance track, which starts on day one.

---

## Phase 0 — Design (this repository) ✅
Deliverables 1–12 (vision, PRD, features, personas, stories, architecture, schema, dashboards, navigation, roadmap, AI strategy, expansion). **Exit:** design reviewed and approved.

## Phase 1 — Foundation & Compliance Spine (Weeks 1–6)
**Engineering**
- Repo, CI/CD, IaC (Terraform), environments (dev/staging).
- Auth: SSO/OIDC scaffold; user/role/scope model; **RBAC + Postgres RLS from the start**.
- Audit-log pipeline.
- Core schema ([07](07-database-schema.md)) migrations; multi-tenant `tenant_id` everywhere.
- Synthetic/de-identified data generator (fake district, schools, students, assessments).

**Compliance/District (parallel)**
- Begin M-DCPS vendor + data-sharing agreement process.
- Draft data-protection agreement; select LLM provider with zero-retention/no-training terms.

**Exit:** a logged-in user, correctly scoped, can browse synthetic students with full audit logging.

## Phase 2 — Data In & Understand (Weeks 5–10)
- Assessment import (CSV/Excel) with guided, savable column mapping; batch import; student reconciliation.
- Standards library loaded (Florida B.E.S.T. K–5, ELA & Math) with item→standard linkage.
- Assessment analytics: per-standard mastery, rankings, growth (PM1→PM2→PM3), regression, comparisons, heat maps.
- Risk indicators + lowest-25%/bubble cohorts.
- **Teacher dashboard** and **Principal dashboard** (v1).

**Exit:** upload a class file → see ranked deficient standards + growth in minutes.

## Phase 3 — The DI Engine (Weeks 9–16) — *the core, highest value*
- Auto-identify deficient standards → auto-form groups (teacher-overridable).
- 7-day DI plan generation with all artifacts (teacher guide, packet, manipulatives, practice, centers, homework, quick checks, exit tickets, progress monitoring, reassessment).
- AI generation grounded via RAG on standards + de-identified class data ([11](11-ai-integration-strategy.md)).
- PDF export of every artifact; edit-before-print.
- Day-7 reassessment → growth loop closes → next recommendation.

**Exit:** Friday's exit ticket becomes Monday's printed, differentiated packets. (This is the demo that sells the platform.)

## Phase 4 — AI Coach & Reporting (Weeks 15–22)
- AI Coach conversational UI, grounded and role-scoped, with all generator intents (reteach, small group, center, intervention, vocabulary, anchor chart, exit ticket, assessment, parent letter — draft only, never auto-sent).
- Reporting module: student/teacher/grade/school/parent/MTSS/leadership reports.
- Exports: PDF (must), Excel & PowerPoint (should).
- Coach dashboards.

**Exit:** teachers ask and receive grounded help; leaders generate real reports.

## Phase 5 — Collaboration & Curriculum (Weeks 21–28)
- PLC module: auto-drafted agendas, data discussion, root-cause, strategy, misconceptions, commitments, cross-meeting action tracking.
- Curriculum module: pacing guides, instructional focus calendars, priority/power standards; recommendations aligned to the current pacing window.
- AP/MTSS and interventionist/ESE/ELL views.

**Exit:** a coach runs a fully-prepped, data-driven PLC from the platform.

## Phase 6 — Live-Data Pilot (gated on compliance track)
- **Gate:** signed data-sharing agreement + security review passed.
- OCR import for paper exit tickets.
- First integrations (SIS/i-Ready via SFTP/API where available).
- Single-school live pilot (the "Avocado Elementary" pilot); measure north-star (time-to-instruction) and planning-hours saved.
- Hardening from real-world usage & accessibility audit (WCAG 2.1 AA).

**Exit:** one school runs on live data with measured impact.

## Phase 7 — District Rollout & Scale
- Multi-school onboarding; district dashboard hardened.
- Analytics moved to columnar store for district-scale aggregates.
- Extract heaviest modules (DI, Analytics, AI) from the modular monolith into services as load requires.
- Mobile app / robust offline sync.
- Deeper integrations (Clever/ClassLink rostering, automated feeds).

**Exit:** the district runs on Avocado with SLAs.

## Phase 8+ — Platform & Multi-State
See [12](12-future-expansion.md): configurable standards frameworks and accountability models, marketplace, predictive early-warning, secondary grades.

---

## Milestones & the one demo that matters
| Milestone | When | Proof point |
|-----------|------|-------------|
| Compliance spine live | End P1 | Scoped access + audit on synthetic data |
| Data→insight | End P2 | Ranked deficiencies + growth from an upload |
| **Data→instruction** | End P3 | **Exit ticket → printed 7-day DI packets** |
| Grounded AI + reports | End P4 | "What do I teach next?" answered + exportable reports |
| Live pilot with impact | P6 | Time-to-instruction measured in minutes |

## Team shape (indicative)
Product lead · 2–3 full-stack engineers · 1 data/ML engineer · 1 designer (UX) · a part-time **instructional/curriculum SME** (essential — validates pedagogy) · plus district liaison for the compliance track.

## Key risks & mitigations
- **Compliance/agreement delays** → build & demo entirely on synthetic data; don't block product on the agreement.
- **AI quality/hallucination** → RAG grounding, SME review of generated materials, citations, edit-before-use.
- **Teacher adoption** → obsessive focus on the <5-minute data→packet path; no training required.
- **Scope creep** (this is a big vision) → strict MoSCoW; the DI loop (P3) is non-negotiable, everything else sequences behind it.
- **Standards content licensing** → resolve B.E.S.T./pacing content sourcing during P1–P2.
