# 06 — System Architecture

## 1. Architectural goals

- **Modular:** the 10 modules are independently developable and deployable, communicating through shared data + events.
- **Multi-tenant:** one school → one district (300+ schools) without re-architecture; strict tenant isolation.
- **Secure & compliant by construction** (see [00](00-compliance-and-guardrails.md)).
- **AI-native but grounded:** LLM features backed by the platform's real data via retrieval, never free-floating.
- **Configurable standards/accountability:** Florida B.E.S.T. today, other states later, as data not code.

## 2. High-level architecture

```
                         ┌───────────────────────────────────────────┐
                         │            Client (Web / PWA)             │
                         │  React + TypeScript · role-based UI · PWA  │
                         │  offline cache (roster + last DI plan)     │
                         └───────────────┬───────────────────────────┘
                                         │ HTTPS (TLS 1.2+)
                         ┌───────────────▼───────────────────────────┐
                         │            API Gateway / BFF               │
                         │  AuthN (OIDC/SSO) · AuthZ (RBAC) · rate    │
                         │  limiting · audit logging middleware       │
                         └───────────────┬───────────────────────────┘
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        │            Application / Domain Services (modular)               │
        ├──────────────┬──────────────┬──────────────┬───────────────────┤
        │ Ingestion &  │ Assessment   │ Differentiated│ Standards &       │
        │ Integration  │ Analytics    │ Instruction   │ Curriculum        │
        ├──────────────┼──────────────┼──────────────┼───────────────────┤
        │ Reporting    │ Collab       │ Dashboards    │ AI Coach /        │
        │ & Export     │ Planning     │ & Aggregation │ Orchestration     │
        └──────┬───────┴──────┬───────┴──────┬───────┴─────────┬─────────┘
               │              │              │                 │
        ┌──────▼──────────────▼──────────────▼─────────┐  ┌────▼───────────┐
        │        Data Layer (multi-tenant)             │  │ AI Layer       │
        │  PostgreSQL (OLTP, RLS per tenant)           │  │ LLM provider   │
        │  Analytics store / columnar (aggregates)     │  │ (0-retention,  │
        │  Object storage (packets, uploads, exports)  │  │  no-training)  │
        │  Cache (Redis)  ·  Search (standards)         │  │ Vector store   │
        │  Event bus / queue (async jobs)              │  │ (RAG index)    │
        └──────────────────────────────────────────────┘  └────────────────┘
```

## 3. Recommended technology stack

Chosen for team velocity, hiring pool, ecosystem maturity, and compliance fit. Alternatives noted.

| Layer | Recommendation | Why / alternatives |
|-------|----------------|--------------------|
| **Frontend** | React + TypeScript, Next.js, Tailwind + a component library (shadcn/ui), Recharts/visx for charts, PWA for offline. | Huge talent pool; SSR for fast dashboards; PWA covers offline & mobile-responsive. Alt: Remote. |
| **Backend** | TypeScript (NestJS) *or* Python (FastAPI). Recommend **Python/FastAPI** for the analytics + AI-heavy nature; NestJS acceptable if team is JS-first. | Python aligns with data science / ML tooling. Modular monolith first, extract services later. |
| **Database (OLTP)** | PostgreSQL with **Row-Level Security** for tenant + RBAC isolation. | Mature, RLS gives defense-in-depth for multi-tenancy; JSON columns for flexible per-standard content. |
| **Analytics** | Start in Postgres (materialized views); grow into a columnar store (DuckDB/ClickHouse/BigQuery) for district-scale aggregates. | Don't over-build early. |
| **Object storage** | S3-compatible (AWS S3 / GCS). | Packets, uploads, PDF/PPTX exports. Encrypted, US region. |
| **Cache / queue** | Redis (cache + rate limiting); a job queue (Celery/RQ or BullMQ) for async import, generation, exports. | DI generation, OCR, and exports are async jobs. |
| **Search** | Postgres full-text first; OpenSearch/Meilisearch for standards library at scale. | Standards browsing & AI retrieval. |
| **AI / LLM** | A frontier LLM under **zero-retention, no-training** enterprise terms; RAG over a vector index of standards, pacing, and (de-identified) student context. | See [11](11-ai-integration-strategy.md). Model choice is a config, not a lock-in. |
| **Vector store** | pgvector (start) → dedicated vector DB at scale. | Keep it in Postgres early to reduce moving parts. |
| **OCR** | Cloud OCR service or self-hosted (Tesseract + layout model) for scanned exit tickets. | Human-confirm low-confidence extractions. |
| **Auth** | OIDC / SAML SSO to integrate with district identity (Google Workspace / ClassLink / Clever). MFA for staff. | Districts expect SSO; avoid managing passwords. |
| **Hosting** | Cloud (AWS/GCP/Azure), US region, infrastructure-as-code (Terraform), containers (Docker) on managed Kubernetes or serverless. | FedRAMP/StateRAMP-aligned services where available. |
| **Observability** | Centralized logging, metrics, tracing; separate, access-controlled **audit log** stream. | Compliance + operability. |

## 4. Multi-tenancy & RBAC

- **Tenant model:** District → School → Grade → Class → Student hierarchy. Every row carries `tenant_id` (district) and relevant scoping keys.
- **Isolation:** Postgres Row-Level Security policies keyed to the authenticated principal's scope. The API layer *and* the database both enforce access — defense in depth.
- **RBAC:** Roles from [04](04-personas.md) map to permission sets. Access is scoped along two axes: **hierarchy** (which students/schools) and **subject** (ELA/Math). Coaches are subject-scoped; teachers are roster-scoped; support staff are task-scoped.
- **Audit:** Middleware logs every access to a student record (actor, record, action, purpose, timestamp) to an append-only store.

## 5. Data flow (see also [detailed flow narrative below])

1. **Ingest:** File upload / OCR / (later) API feed → validation → column mapping → normalization → student reconciliation → persisted as `assessment_results`. Emits `AssessmentImported` event.
2. **Analyze:** Analytics service consumes the event → computes per-standard mastery, growth, rankings, cohorts → writes to aggregate tables. Emits `AnalysisReady`.
3. **Recommend/Group:** DI service consumes `AnalysisReady` → identifies deficient standards → forms groups → creates draft DI plans. Emits `DIPlanDrafted`.
4. **Generate:** DI + AI orchestration generate the 7-day plan artifacts (RAG-grounded) as async jobs → stored in object storage → PDF render on demand.
5. **Surface:** Dashboards read aggregates; teacher sees groups + packets; AI Coach answers grounded in the same aggregates + standards index.
6. **Close loop:** Day-7 reassessment imported → back to step 1; growth updated; next recommendation produced.

Every step writes to the audit log where student records are touched.

## 6. AI grounding (RAG) pattern

The AI Coach and generators never answer from the model's parametric memory alone. Each request retrieves: (a) the relevant B.E.S.T. standard(s) and their metadata, (b) district pacing/priority context, (c) the relevant **de-identified** student/class analysis, and (d) prior interventions. This context is composed into the prompt; the model generates grounded, citable output. Details and safety in [11](11-ai-integration-strategy.md).

## 7. Deployment & environments

- **Environments:** dev → staging (synthetic data) → pilot (live, post-agreement) → prod.
- **IaC:** all infra in Terraform; reproducible, reviewable.
- **CI/CD:** automated tests (unit, integration, RBAC/authz tests, accessibility checks) gate deploys.
- **Backups:** encrypted, tested restores; district-retention-aligned; hard-delete supported.

## 8. Why a modular monolith first (not microservices)

At one-school pilot scale, microservices add operational cost without benefit. Avocado starts as a **modular monolith** with clean module boundaries and an event bus, so that the DI, Assessment, or AI modules can be extracted into independent services later when district-scale load justifies it — without rewriting domain logic.
