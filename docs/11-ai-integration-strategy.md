# 11 — AI Integration Strategy

AI is central to Avocado — but it must be **grounded, safe, and compliant**, never a free-floating chatbot guessing about children. This document defines how.

## 1. Principles

1. **Grounded, not generative-from-memory.** Every AI output is anchored in retrieved, authoritative context: the actual B.E.S.T. standard, district pacing, and the relevant (de-identified) student/class data. The model composes and adapts; it does not invent facts or scores.
2. **De-identify by default.** Prompts reference students by pseudonym + attributes ("Student A, Grade 3, ELL L3, deficient on ELA.3.R.2.2") unless a real name is genuinely required (e.g., a parent-letter draft the teacher will personally review). See [00](00-compliance-and-guardrails.md).
3. **Zero-retention, no-training.** The LLM provider operates under enterprise terms: no retention of prompts/outputs beyond the request, and **no training on our data**. This is contractual and verified before any live-data use.
4. **Human-in-the-loop, always.** AI *drafts and recommends*; educators approve, edit, and act. Nothing high-stakes (placement, retention, eligibility) is ever AI-decided. Nothing external (parent communication) is ever auto-sent.
5. **Cite the driver.** Every recommendation names the assessment/standard that drove it (`grounding_refs` in [07](07-database-schema.md)), so educators can trust and verify.
6. **Editable & labeled.** All AI output is clearly labeled AI-generated and fully editable before use.

## 2. Where AI is used

| Feature | AI role | Grounding | Safeguard |
|---------|---------|-----------|-----------|
| **AI Coach** (conversational) | Answer "what to teach next," explain data, generate materials on request | Standards library + pacing + de-identified class analysis + prior interventions | Role-scoped, cited, editable |
| **DI plan generation** | Draft 7-day cycle artifacts | Focus standard details, misconceptions, vocabulary, grade level, group profile | SME-validated templates; edit-before-print |
| **Grouping** | Suggest groups from shared deficiencies | Item-level `standard_mastery` | Teacher overrides membership |
| **PLC prep** | Draft agenda, root-cause, discussion Qs | Grade/subject rollups + standards | Coach edits before meeting |
| **Reports** | Draft narrative + next steps | Aggregates + growth | Human reviews before sharing |
| **Parent letters** | Draft communication | Student growth + standards | **Never auto-sent**; staff review + send |
| **Early warning** | Surface schools/students trending to risk | Trend + growth analytics | Advisory only; humans decide support |

## 3. Architecture: Retrieval-Augmented Generation (RAG)

```
User request (role + scope known)
      │
      ▼
[Context assembler]
   ├─ Retrieve standard(s) + details/misconceptions/vocab   (standards index)
   ├─ Retrieve district pacing/priority context             (curriculum)
   ├─ Retrieve de-identified analysis for the scope         (analytics, RBAC-filtered)
   ├─ Retrieve prior interventions (de-identified)          (interventions)
      │
      ▼
[Prompt composer]  → system prompt (role, guardrails, format) + retrieved context
      │
      ▼
[LLM  — zero-retention, no-training]
      │
      ▼
[Post-processor] → validate structure, attach grounding_refs, label AI-generated
      │
      ▼
Editable draft in UI  (+ audit log entry)
```

- **Vector index (pgvector → dedicated store at scale):** standards, misconceptions, exemplar strategies, pacing text. Student data is retrieved via **structured, RBAC-scoped queries**, not embedded wholesale into a shared vector space.
- **Model choice is configuration.** Avocado targets a frontier LLM under enterprise terms but abstracts the provider behind an interface so models can be swapped/upgraded, or a smaller/self-hosted model used for lower-sensitivity tasks.

## 4. Prompt & safety controls

- **System prompts** encode role, allowed scope, output format, and hard guardrails ("never fabricate scores," "cite the driving standard," "do not make eligibility/placement decisions").
- **Scope injection:** the assembler only ever retrieves data the requesting user is authorized to see — the model physically cannot receive out-of-scope student data.
- **Output validation:** structured outputs (e.g., DI artifacts) are schema-validated; malformed or ungrounded responses are rejected/regenerated.
- **Content appropriateness:** generated instructional material is grade-band-appropriate; templates are SME-reviewed; a feedback loop lets teachers flag bad output to improve prompts/templates.
- **Rate limiting & cost controls:** async generation jobs, caching of standard-level artifacts (a reteach for ELA.3.R.2.2 at grade 3 can seed many classes), and reuse.

## 5. Evaluation & quality

- **Golden-set evaluation:** a SME-curated set of standards × scenarios with expected-quality rubrics; regression-tested on model/prompt changes.
- **Human review metrics:** track edit rate (how much teachers change AI drafts) as a quality signal; high edit rates flag weak templates.
- **Hallucination guardrail:** any numeric/data claim must trace to a `grounding_ref`; unsupported claims are stripped.

## 6. Compliance posture (summary)

- No student PII in model training — contractually and architecturally.
- De-identification by default; real names only where a human-reviewed artifact requires them.
- Full audit trail of AI generations (`ai_generation_jobs`, `ai_messages.grounding_refs`).
- All external-facing AI output gated behind human review and send.

## 7. Roadmap for AI capability

- **P3:** grounded DI generation + grouping.
- **P4:** full AI Coach + report narratives.
- **P6+:** OCR-assisted item analysis; retrieval quality tuning on real (de-identified) usage.
- **P8+:** predictive early-warning models (see [12](12-future-expansion.md)) — built as **advisory** analytics with transparent drivers, never opaque high-stakes automation.

> Avocado's AI is a tireless instructional aide that drafts, groups, and explains — always grounded in the school's real data, always leaving the professional judgment with the educator.
