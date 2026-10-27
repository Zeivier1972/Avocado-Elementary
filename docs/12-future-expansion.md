# 12 — Future Expansion Opportunities

Avocado is designed for a single M-DCPS elementary school first, but architected so the path to "every district in the U.S." is configuration, not rewrite. This document maps that trajectory.

## The expansion thesis

The hard, valuable core — *turn assessment data into differentiated, standards-aligned instruction, grounded and compliant* — is universal. What varies by market is **which standards** and **which accountability model**. Because Avocado stores both as **data** (`standards_frameworks`, `accountability_models`) rather than hard-coded logic ([07](07-database-schema.md)), expansion is primarily a content-and-config effort.

## Horizon 1 — Deepen within M-DCPS (0–18 months)
- **Secondary grades (6–12):** extend standards library and DI patterns to middle/high; more subjects (Science/EOC, Civics, Algebra 1).
- **More data sources:** deeper i-Ready, FAST, and district-assessment integrations via API/SFTP; automated nightly feeds.
- **MTSS automation:** end-to-end tier documentation, meeting packs, and progress-monitoring compliance.
- **Family engagement:** parent-facing (staff-approved) progress summaries; multilingual (Spanish/Haitian-Creole — critical for M-DCPS).
- **Scheduling intelligence:** suggest intervention blocks and staffing based on need.

## Horizon 2 — Statewide (Florida) (12–30 months)
- License to other Florida districts — same B.E.S.T. standards and FAST/accountability model, so mostly onboarding + config.
- **District benchmarking** (opt-in, privacy-preserving aggregates) across districts.
- **Curriculum marketplace:** vetted DI lessons, centers, and anchor charts shared across schools/districts.
- **Coaching analytics:** measure and improve coaching impact.

## Horizon 3 — Multi-state platform (24–48 months)
- **Pluggable standards frameworks:** load any state's standards (or Common Core) as a framework; the prerequisite graph and item-mapping model already generalize.
- **Pluggable accountability models:** each state's school-grade/rating formula as a configurable model driving risk indicators and projections.
- **Assessment-vendor connectors:** NWEA MAP, STAR, state test exports, etc.
- **SIS/rostering standards:** Clever, ClassLink, OneRoster, Ed-Fi alignment for turnkey onboarding.
- **Interoperability:** Ed-Fi / IMS Global (1EdTech) compliance to slot into district data ecosystems.

## Horizon 4 — Intelligence & platform (36+ months)
- **Predictive early-warning:** advisory models forecasting which students/standards/schools trend toward risk, with transparent drivers (never opaque high-stakes automation — see [11](11-ai-integration-strategy.md)).
- **Adaptive learning paths:** per-student sequencing across the prerequisite graph.
- **Student-facing experiences (COPPA-compliant):** carefully designed, age-appropriate practice tied to their DI plan.
- **Open API & developer platform:** let districts and partners build on Avocado's data model.
- **Efficacy research partnerships:** publish evidence of impact (ESSA evidence tiers) — a major procurement differentiator.
- **What-if planning:** simulate "if we focus these standards, projected grade impact is X."

## Business & go-to-market expansion
- **Tiered offering:** school → district → state license; add-ons (secondary, family engagement, marketplace).
- **Procurement readiness:** ESSA evidence, accessibility (508/WCAG), security certifications (SOC 2, StateRAMP), data-privacy pledges (Student Privacy Pledge).
- **Professional services:** onboarding, data integration, coaching enablement.

## Technical enablers already in the design
| Future need | Enabled today by |
|-------------|------------------|
| Multi-state standards | Standards/framework as data ([07](07-database-schema.md)) |
| Multi-state accountability | Accountability model as config |
| District scale | Multi-tenant + modular monolith → extractable services ([06](06-system-architecture.md)) |
| New assessment vendors | Import mapping templates + item→standard model |
| New AI models | Provider-abstracted AI layer ([11](11-ai-integration-strategy.md)) |
| Interoperability | Clean domain model, event bus, US-hosted secure data layer |

## Guardrails on expansion
Every new market inherits the [compliance spine](00-compliance-and-guardrails.md): FERPA + that state's student-privacy law, RBAC, audit, no-training-on-PII, human-in-the-loop. Growth never comes at the cost of the trust posture — that posture *is* the moat in the education market.

---

*Avocado starts as the instructional operating system for one elementary school and is built, deliberately, to become the instructional intelligence layer for public education.*
