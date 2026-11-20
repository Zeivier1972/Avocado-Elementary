# 00 — Compliance & Data Governance Guardrails

*Read this before any other document. A world-class education platform that ignores student-data law is a liability, not a product. These constraints shape every architecture and AI decision that follows.*

## Why this comes first

Avocado ingests some of the most sensitive data a public institution holds: identifiable records of minors, including academic performance, ESE/504 status, ELL status, behavior, and attendance. The legal and district framework is non-negotiable and must be designed in, not bolted on.

## Governing frameworks

| Framework | What it requires of Avocado |
|-----------|-----------------------------|
| **FERPA (20 U.S.C. §1232g)** | Education records may only be disclosed to authorized parties with a legitimate educational interest. Avocado acts as a "school official" under district contract, meaning it must be under the school's direct control regarding use and maintenance of records. |
| **Florida §1002.22 / §1002.222 F.S.** | State-level student data privacy. Prohibits sale of student data; restricts collection to what is educationally necessary; parents have inspection rights. |
| **PPRA** | Restrictions on surveys and certain data collection from students. |
| **COPPA** | Relevant if any student-facing feature collects data from children under 13 (elementary = yes). Favor teacher-mediated data entry over direct child accounts in early phases. |
| **M-DCPS vendor & data-sharing requirements** | District data-sharing agreement, security review, and approved-vendor status are prerequisites to touching live district data (FAST, i-Ready exports, SIS/ISIS). |
| **State/district accessibility (Section 508 / WCAG 2.1 AA)** | Public-sector software must be accessible. |

## Design principles that follow

1. **Privacy by design & data minimization.** Ingest only fields with a stated instructional purpose. No SSNs. Student identifiers are district-issued, not invented.
2. **No training on student PII.** Student data is never sent to third-party model providers for training, and prompts to LLMs are de-identified or run under a zero-retention / no-training contractual configuration. See [11-ai-integration-strategy.md](11-ai-integration-strategy.md).
3. **Role-based access control (RBAC) everywhere.** A teacher sees their roster; a coach sees their assigned grade bands; a principal sees the school; the district sees aggregates. Enforced at the query layer, not just the UI.
4. **Full audit trail.** Every read/write of a student record is logged with actor, timestamp, and purpose. Non-repudiable.
5. **Encryption in transit and at rest.** TLS 1.2+ everywhere; database and backups encrypted (AES-256). Field-level encryption for the most sensitive attributes.
6. **Data residency & retention.** Follow district retention schedules; support hard-delete and export on district request. US-region hosting only.
7. **Parent-facing content is generated but never auto-sent.** AI drafts parent letters; a human always reviews and sends. No automated external communication about a child without staff approval.
8. **Human-in-the-loop for all high-stakes recommendations.** Avocado *recommends* interventions and groupings; educators decide. The system never makes a placement/retention/ESE-eligibility decision.

## Guardrails specifically for AI features

- LLM prompts operate on **de-identified** or **pseudonymized** student references (e.g., "Student A, 3rd grade, below-standard on B.E.S.T. ELA.3.R.2.2") wherever the output does not require a real name.
- Model provider must be under a **zero-retention, no-training** agreement (see [11](11-ai-integration-strategy.md)).
- All AI output is labeled as AI-generated and is **editable** before use.
- Guardrails against fabricated data: the AI Coach cites which assessment/standard drove a recommendation and never invents scores.

## What this means for the build

- The MVP can and should be built and demoed against **synthetic / de-identified sample data** — no district agreement required to prove value.
- The pilot against live data is gated on the district data-sharing agreement and security review. These run in parallel with development (see roadmap Phase gates).

> **Bottom line:** Avocado is designed so that the compliance answer is always "yes, by construction." Every table, endpoint, and prompt in the following documents assumes these guardrails.
