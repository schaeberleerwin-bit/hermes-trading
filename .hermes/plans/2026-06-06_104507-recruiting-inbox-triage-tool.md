# Recruiting Inbox Triage Tool Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build an MVP tool for recruiting agencies that automatically classifies incoming inquiries, assigns priority/confidence, recommends or performs routing, and gives users a reviewable audit trail.

**Architecture:** Start as a local/web MVP with a small backend, database, and web UI. Use deterministic rules plus an LLM classification adapter behind a clean interface so the system can be demoed with sample data first and connected to real channels later. Keep the first version narrow: email/form-like messages in, classification + routing suggestion out, manual review and audit log visible.

**Tech Stack:** Recommended: Next.js/React frontend, Node.js API routes or FastAPI backend, SQLite/Postgres, Prisma/SQLAlchemy, OpenAI-compatible LLM adapter, optional webhook/email ingestion later. If the existing workspace already has a preferred stack, adapt the file paths to that stack before implementation.

---

## Product Scope

### First customer-facing outcome
A recruiter opens a dashboard and sees incoming messages automatically sorted into categories like:
- New customer lead
- New candidate
- Application for open role
- Interview reschedule
- Application status question
- Urgent client request
- Spam / irrelevant
- Existing client
- High-priority candidate
- Outside target profile

For each inquiry, the tool shows:
- source
- original message
- short AI summary
- category
- priority
- confidence score
- recommended destination/person/team
- reason/explanation
- status: new, needs review, routed, corrected, archived
- audit log of decisions

### First MVP boundaries
Include:
- Demo inbox with seeded recruiting examples
- Manual message creation/import via form or JSON fixture
- Classification pipeline
- Rules-based routing layer
- Review UI
- Audit log
- Basic settings for categories, routes, and thresholds

Exclude for MVP:
- Full ATS integration
- Real LinkedIn scraping
- WhatsApp production integration
- Billing/login/teams
- Autonomous replies without human approval
- Candidate ranking decisions that could create legal risk

---

## Key User Flow

1. New inquiry appears in the Inbox.
2. System classifies it automatically.
3. System assigns priority and confidence.
4. System suggests a routing target.
5. User opens detail view.
6. User reviews original message, summary, category, route, and reason.
7. User clicks one of:
   - Confirm route
   - Change category
   - Change routing target
   - Archive as spam
   - Save as rule
8. Audit log records what happened.

---

## Proposed Data Model

### `Inquiry`
Fields:
- `id`
- `createdAt`
- `updatedAt`
- `source` — email, website, linkedin, whatsapp, job_board, manual
- `senderName`
- `senderEmail`
- `companyName`
- `subject`
- `body`
- `status` — new, classified, needs_review, routed, corrected, archived
- `category`
- `priority` — low, medium, high, urgent
- `confidence` — 0.0 to 1.0
- `summary`
- `reasoning`
- `recommendedRouteId`
- `finalRouteId`
- `requiresHumanReview`

### `Route`
Fields:
- `id`
- `name`
- `type` — person, team, email, slack, webhook, ats
- `destination`
- `active`

### `RoutingRule`
Fields:
- `id`
- `name`
- `conditionsJson`
- `routeId`
- `active`
- `priority`

### `AuditEvent`
Fields:
- `id`
- `inquiryId`
- `createdAt`
- `actor` — system, user
- `eventType`
- `beforeJson`
- `afterJson`
- `note`

---

## Classification Contract

Create a classifier function that returns strict JSON:

```json
{
  "category": "new_customer_lead",
  "priority": "high",
  "confidence": 0.91,
  "summary": "Customer needs five warehouse workers in Stuttgart on short notice.",
  "reasoning": "The sender describes a staffing need, location, quantity, and urgency.",
  "suggestedRouteKey": "sales",
  "requiresHumanReview": false
}
```

Rules:
- If confidence `< 0.75`, set `requiresHumanReview: true`.
- If category is `spam_irrelevant`, default status should be `needs_review` or `archived` depending on setting.
- Never send automatic rejection/approval decisions in MVP.
- Always store raw model output separately only if it contains no secrets; otherwise store parsed safe fields only.

---

## Suggested File Structure

If building a fresh Next.js app:

```text
recruiting-triage/
├── package.json
├── prisma/
│   ├── schema.prisma
│   └── seed.ts
├── src/
│   ├── app/
│   │   ├── page.tsx                         # Dashboard
│   │   ├── inbox/page.tsx                   # Inbox list
│   │   ├── inbox/[id]/page.tsx              # Detail view
│   │   ├── rules/page.tsx                   # Rule builder
│   │   ├── integrations/page.tsx            # Integrations placeholder/settings
│   │   └── audit/page.tsx                   # Audit log
│   ├── components/
│   │   ├── InquiryTable.tsx
│   │   ├── InquiryDetail.tsx
│   │   ├── CategoryBadge.tsx
│   │   ├── PriorityBadge.tsx
│   │   ├── ConfidenceMeter.tsx
│   │   └── RouteSuggestionCard.tsx
│   ├── lib/
│   │   ├── db.ts
│   │   ├── classifier.ts
│   │   ├── routing.ts
│   │   ├── audit.ts
│   │   └── sample-data.ts
│   └── app/api/
│       ├── inquiries/route.ts
│       ├── inquiries/[id]/classify/route.ts
│       ├── inquiries/[id]/confirm-route/route.ts
│       ├── inquiries/[id]/correct/route.ts
│       └── rules/route.ts
└── tests/
    ├── classifier.test.ts
    ├── routing.test.ts
    └── audit.test.ts
```

If adding to an existing repo, first inspect its actual stack and map these concepts into the repo’s current folders.

---

# Implementation Tasks

## Task 1: Create project skeleton

**Objective:** Create the initial app structure, dependency setup, and empty pages.

**Files:**
- Create: `recruiting-triage/package.json`
- Create: `recruiting-triage/src/app/page.tsx`
- Create: `recruiting-triage/src/app/inbox/page.tsx`
- Create: `recruiting-triage/src/app/rules/page.tsx`
- Create: `recruiting-triage/src/app/audit/page.tsx`

**Verification:**
- Run: `npm run dev`
- Expected: app starts locally and dashboard route loads.

---

## Task 2: Add database schema

**Objective:** Add persistent models for inquiries, routes, rules, and audit events.

**Files:**
- Create: `prisma/schema.prisma`
- Create: `src/lib/db.ts`

**Test target:**
- migration should apply cleanly.

**Verification:**
- Run: `npx prisma migrate dev --name init`
- Expected: migration succeeds and database file/tables exist.

---

## Task 3: Seed demo recruiting inquiries

**Objective:** Create realistic demo data for the first customer demo.

**Files:**
- Create: `prisma/seed.ts`
- Create or modify: `src/lib/sample-data.ts`

**Demo examples:**
- “Wir suchen kurzfristig 5 Lagerhelfer für unseren Standort in Stuttgart.”
- “Hallo, ich habe Ihre Anzeige als Staplerfahrer gesehen und möchte mich bewerben.”
- “Gibt es schon Neuigkeiten zu meiner Bewerbung?”
- “Ich muss mein Interview morgen verschieben.”
- irrelevant vendor spam.

**Verification:**
- Run seed command.
- Expected: dashboard/inbox shows seeded inquiries.

---

## Task 4: Implement deterministic classification fallback

**Objective:** Build a no-API fallback classifier so the demo works without LLM keys.

**Files:**
- Create: `src/lib/classifier.ts`
- Test: `tests/classifier.test.ts`

**Behavior:**
- Keyword/rule-based mapping to category, priority, confidence, summary, suggested route.
- Low-confidence cases require human review.

**Verification:**
- Run: `npm test -- classifier`
- Expected: all sample messages classify into expected categories.

---

## Task 5: Add LLM classifier adapter behind same interface

**Objective:** Allow high-quality classification when an API key is configured, while preserving fallback mode.

**Files:**
- Modify: `src/lib/classifier.ts`
- Create: `src/lib/llm-classifier.ts`
- Test: `tests/classifier.test.ts`

**Rules:**
- Return strict parsed JSON.
- Validate category/priority enums.
- On LLM failure, fallback to deterministic classifier.
- Never fail the whole inbox because one model call fails.

**Verification:**
- Tests mock LLM output.
- Expected: valid output parses, invalid output falls back or returns `needs_review`.

---

## Task 6: Implement routing engine

**Objective:** Convert classification result into route recommendation.

**Files:**
- Create: `src/lib/routing.ts`
- Test: `tests/routing.test.ts`

**Default routes:**
- `sales` for customer leads
- `recruiter` for candidates/applications
- `support` for status questions
- `calendar` for interview reschedule
- `manual_review` for low confidence
- `archive_review` for spam

**Verification:**
- Run: `npm test -- routing`
- Expected: categories map to correct route, low confidence overrides to manual review.

---

## Task 7: Implement audit logging

**Objective:** Record classification, route confirmation, correction, and archive events.

**Files:**
- Create: `src/lib/audit.ts`
- Test: `tests/audit.test.ts`

**Verification:**
- Confirming or correcting an inquiry creates an audit event.

---

## Task 8: Build Inbox UI

**Objective:** Show classified inquiries in a scannable operational table.

**Files:**
- Create: `src/components/InquiryTable.tsx`
- Create: `src/components/CategoryBadge.tsx`
- Create: `src/components/PriorityBadge.tsx`
- Create: `src/components/ConfidenceMeter.tsx`
- Modify: `src/app/inbox/page.tsx`

**UI requirements:**
- Search/filter by status/category/priority/source.
- Visual highlight for urgent and low-confidence inquiries.
- Clicking a row opens detail page.

**Verification:**
- Manual browser check.
- Expected: seeded inquiries are visible and readable.

---

## Task 9: Build inquiry detail review flow

**Objective:** Let user review and approve/correct a classification.

**Files:**
- Create: `src/app/inbox/[id]/page.tsx`
- Create: `src/components/InquiryDetail.tsx`
- Create: `src/components/RouteSuggestionCard.tsx`
- Create: API routes for confirm/correct/archive.

**Actions:**
- Confirm route
- Change category
- Change route
- Mark as spam
- Save as rule placeholder

**Verification:**
- User can change one inquiry and return to inbox with updated status.
- Audit event appears.

---

## Task 10: Build dashboard overview

**Objective:** Provide high-level operational metrics.

**Files:**
- Modify: `src/app/page.tsx`

**Metrics:**
- inquiries today
- classified automatically
- routed
- needs review
- average confidence
- estimated time saved

**Caution:**
- Mark time saved as estimate, not proven fact.

**Verification:**
- Dashboard reflects seeded and updated data.

---

## Task 11: Build simple rule builder

**Objective:** Create a first version of rules without overengineering.

**Files:**
- Modify: `src/app/rules/page.tsx`
- Create: API route `src/app/api/rules/route.ts`

**MVP rule format:**
- condition category equals X
- optional confidence greater than Y
- route to Z

**Verification:**
- Adding a rule changes future route recommendation.

---

## Task 12: Add integrations placeholder/settings page

**Objective:** Show where future integrations connect without implementing all of them.

**Files:**
- Modify: `src/app/integrations/page.tsx`

**Integrations to show:**
- Email
- Website form/webhook
- LinkedIn manual import placeholder
- WhatsApp placeholder
- ATS/CRM placeholder
- Slack/Teams placeholder

**Verification:**
- Page clearly communicates connected vs planned integrations.

---

## Task 13: Add audit log page

**Objective:** Give transparency into all classifications and corrections.

**Files:**
- Modify: `src/app/audit/page.tsx`

**Verification:**
- Audit page lists system and user events for test inquiries.

---

## Task 14: Add webhook/manual intake endpoint

**Objective:** Allow external tools like website forms, Make/Zapier, or test scripts to add inquiries.

**Files:**
- Create: `src/app/api/inquiries/route.ts`

**Behavior:**
- Accept source/sender/subject/body.
- Create inquiry.
- Run classification.
- Run route recommendation.
- Create audit event.

**Verification:**
- POST a sample inquiry.
- Expected: new inquiry appears classified in inbox.

---

## Task 15: Polish demo experience

**Objective:** Make the MVP suitable for a sales call with a recruiting agency.

**Files:**
- Modify UI components and pages as needed.

**Demo script:**
1. Show dashboard pain: mixed inbound requests.
2. Open Live Inbox.
3. Filter to needs review.
4. Open urgent customer lead.
5. Show AI reason and suggested routing.
6. Confirm route.
7. Show audit log.
8. Add one new message via form/webhook.
9. Show instant classification.

**Verification:**
- Complete demo flow in under 3 minutes.

---

# Testing / Validation Plan

## Unit tests
- classifier: expected category/priority/confidence for sample messages
- routing: category + confidence to route
- audit: every state change logs event
- schema validation: invalid classifier JSON handled safely

## Integration tests
- create inquiry → classify → route → audit event
- correct inquiry → status updated → audit event
- low confidence → manual review

## Manual demo validation
- Browser opens dashboard.
- Inbox shows seeded messages.
- Detail view is understandable without explanation.
- Confirm/correct flow works.
- Audit page updates.
- No automatic external sending in MVP unless explicitly configured.

---

# Risks and Guardrails

## Legal / compliance risk
Recruiting workflows can affect candidates. MVP must avoid automated rejection/acceptance decisions. Position the tool as triage and routing, not candidate judgement.

## Hallucination risk
LLM output must be validated against strict enums. Low confidence and parsing failures go to manual review.

## Integration complexity
Real LinkedIn/WhatsApp/ATS integrations can slow down delivery. First version should support manual import and webhook intake, then add integrations based on the first customer’s actual channels.

## Trust risk
Users need to know why the AI classified something. Always show explanation and audit trail.

## Scope creep
Do not build a full CRM or ATS. The first product is inbox triage and routing.

---

# Open Questions Before Build

1. Should the first version be a standalone webapp or built into an existing site/app?
2. Preferred stack: Next.js/Node, Python/FastAPI, or no-code/low-code MVP?
3. First integration channel: email, website form, or manual CSV/JSON import?
4. Where should routing send in the first customer demo: email, Slack/Teams, Airtable/CRM, or just internal status?
5. Should the UI language be German-only first?
6. Do you want this as a demo prototype first or a real working MVP first?

---

# Recommended First Build Decision

Build a **working demo MVP** first, not just a mockup:
- local webapp
- seeded realistic recruiting inquiries
- classifier fallback
- review UI
- audit log
- manual/webhook intake

Then connect exactly one real input channel for the first customer, likely website form or email.

This keeps the first delivery sellable, understandable, and low-risk.
