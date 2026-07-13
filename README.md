# Avocado — Instructional Intelligence Platform for Miami-Dade County Public Schools

> The instructional operating system for the elementary school. Avocado continuously answers one question: **"What should every teacher teach tomorrow to maximize student growth?"**

This repository holds the **design and architecture** of Avocado. Per the project mandate, we design the system like a software company would **before** writing production code. Coding is Phase 10; everything preceding it lives here as reviewable documentation.

---

## What Avocado is

Avocado unifies academic data, instruction, differentiated instruction, collaborative planning, progress monitoring, reporting, coaching, and AI into a single ecosystem for an A-rated (or A-seeking) elementary school. It is built specifically around Miami-Dade County Public Schools (M-DCPS) realities: FAST progress monitoring, i-Ready, district topic/interim assessments, Florida B.E.S.T. standards, MTSS/RTI, and Florida's school-grade accountability model.

## Who it serves

District administrators, principals, assistant principals, reading/math/instructional coaches, teachers, interventionists, ESE teachers, ELL teachers, and support staff.

---

## Design documents

Read in order. Each phase feeds the next.

| # | Document | Phase |
|---|----------|-------|
| 00 | [Compliance & Data Governance Guardrails](docs/00-compliance-and-guardrails.md) | Constraints (read first) |
| 01 | [Executive Vision](docs/01-executive-vision.md) | Phase 1 — Requirements |
| 02 | [Product Requirements Document (PRD)](docs/02-prd.md) | Phase 1 — Requirements |
| 03 | [Feature List](docs/03-feature-list.md) | Phase 1 — Requirements |
| 04 | [User Personas](docs/04-personas.md) | Phase 5 — UX |
| 05 | [User Stories](docs/05-user-stories.md) | Phase 5 — UX |
| 06 | [System Architecture](docs/06-system-architecture.md) | Phase 2 — Architecture |
| 07 | [Database Schema](docs/07-database-schema.md) | Phase 3 — Data |
| 08 | [Dashboard Designs](docs/08-dashboard-designs.md) | Phase 4 — Wireframes |
| 09 | [Navigation Structure](docs/09-navigation-structure.md) | Phase 4 — Wireframes |
| 10 | [Development Roadmap](docs/10-development-roadmap.md) | Phase 9 — Roadmap |
| 11 | [AI Integration Strategy](docs/11-ai-integration-strategy.md) | Phase 7 — AI Design |
| 12 | [Future Expansion Opportunities](docs/12-future-expansion.md) | Strategy |

## Core modules

Dashboard · Student · Teacher · Standards · Assessment · Differentiated Instruction (DI) · Collaborative Planning · Curriculum · Reporting · AI Coach.

## A note on scope and compliance (read before building)

Avocado handles student PII covered by **FERPA**, Florida student-privacy statutes (**§1002.22 / §1002.222 F.S.**), and district data-governance rules. Any real deployment against live M-DCPS data requires a district data-sharing agreement and vendor approval. This design assumes those are pursued in parallel and bakes privacy-by-design in from day one. See [00-compliance-and-guardrails.md](docs/00-compliance-and-guardrails.md).

---

*Status: Design phase. No production code committed yet — by design.*
