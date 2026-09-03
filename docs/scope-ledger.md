# AURA — Scope Ledger (Phase 1 MVP)

*Running record of every deviation from the documented Phase 1 MVP scope, in both directions. Baseline is `AURA Phase 1 MVP Roadmap and Plan of Action.pdf` §2 (scope table) and §3 (the six agents). Reviewed by the founder before Phase 2 planning.*

Last updated: 2026-08-16

---

## A. Behind plan — committed MVP scope not yet built

These were in the agreed Phase 1 scope table and are **not** done. They matter because the pitch narrative in §5 of the roadmap depends on them.

| Item | Committed scope | Actual state | Impact on the pitch |
|---|---|---|---|
| ~~**Workflow Engine**~~ | "3 pre-built, working automation templates" (Sprint 7) | ✅ **RESOLVED 2026-08-15.** `src/workflows/` is a working engine, not a schema. Definitions live in the database (`workflow_definitions`: trigger + ordered JSON steps, per-org, enabled per-org); runs and per-step results are persisted (`workflow_runs`, `workflow_step_runs`) so history is browsable and a failure is debuggable. Triggers: scheduled and event-based (subscribing to the existing bus). Steps: call an agent, call a tool, wait, branch, escalate. Waits **suspend and resume** rather than sleeping, so a multi-day workflow survives a restart. Steps retry with exponential backoff, and a failed run is always closed out — never left wedged. Scheduling is an asyncio task in the app lifespan (**no Celery, no broker**), made safe on multiple instances by a DB-level claim; `python -m scripts.run_workflows --once` is the cron alternative. Three templates seeded per org: appointment reminder → no-show recovery → rebook offer, treatment recall on a configurable interval, and new-enquiry escalation. `GET /workflows`, `POST /workflows/{id}/enable|disable`, `GET /workflows/{id}/runs`. | Was the largest remaining gap; now closed. Tool steps route through the same server-side approval gate as chat — a workflow is not a way around it, and `tests/test_workflows.py::test_a_workflow_cannot_bypass_the_approval_gate` pins that. |
| ~~**Analytics dashboard**~~ | "One unified cross-agent dashboard" (Sprint 7) | ✅ **RESOLVED 2026-08-15 (API side).** `GET /api/v1/analytics/summary?days=N` returns conversations handled, messages sent, actions taken, approvals pending/approved, a per-agent breakdown and a zero-filled daily series. Org-scoped through the same membership check as every other route. The demo seed now carries ~24 conversations and a week of workflow history behind it, because a dashboard showing zeroes is worse than no dashboard. Dashboard page in the UI is being built against this contract in parallel. | Medium-high; API closed. |
| ~~**Demo-org seeding**~~ | "Seed a demo organization with realistic synthetic business data (fictional clinic + e-commerce brand)" (Sprint 8) | ✅ **RESOLVED 2026-08-15.** `apps/api/scripts/seed_demo.py` (`python -m scripts.seed_demo`) builds **Riverside Dental** end to end: owner login, five patients, three clinic documents ingested through the real pipeline, six conversations across four agents, an activity trail, one pending approval. Idempotent; runs with no `OPENAI_API_KEY` (embeddings stubbed deterministically). The fictional e-commerce brand is **not** seeded — clinic only. | Was high for the pitch; now closed for the clinic narrative. |
| ~~**Human-approval gate**~~ | Architecture doc puts "Approval Check" in the request lifecycle; guiding principle #6 is "human approval precedes critical operations". | ✅ **RESOLVED 2026-08-15.** Implemented server-side in the runtime (`agents/approvals.py`, `tool_approvals` table, `api/v1/approvals.py`), enforced against YAML config the model cannot influence, and re-checked at approve time. | Was critical; now closed. Frontend wiring in progress. |
| ~~**Inbound customer channel**~~ | The pitch is "your Receptionist answers your customers." | ✅ **RESOLVED 2026-08-15.** `POST /api/v1/public/chat/{org_public_id}` is a public, unauthenticated web-chat endpoint routed through the existing runtime (opaque org id, per-IP and per-conversation rate limits, message and conversation caps, untrusted framing on inbound text, approval gate intact, no internal detail in any response). A WhatsApp inbound webhook with Meta's verification handshake and signature validation is built but **unproven end to end** pending founder credentials — see `needs-founder-input.md` §10. | Was critical; the web channel now closes it for a demo. |
| ~~**Conversation persistence**~~ | Implied by "conversation history" in the spec. | ✅ **RESOLVED 2026-08-15.** `contacts`, `conversations` and `messages` tables (migration `c3e91b4d75a2`). Redis stays the hot path; the runtime writes through to Postgres and falls back to it on a cold conversation. `GET /conversations` (list, filterable by agent, paginated) and `GET /conversations/{id}` added. No separate `leads` table — a lead is a `contact` with an open conversation, which is the same thing at this scale. | Was high; now closed. |

| ~~**Embeddable web-chat widget**~~ | The public chat endpoint existed but there was no way for an owner to actually put it on their website. | ✅ **RESOLVED 2026-08-16.** `apps/web/public/widget.js` — a dependency-free vanilla JS bundle, no build step, rendered inside a closed Shadow DOM so it can neither leak styles onto a host page nor inherit them. Persists the conversation token per-org in `localStorage` so a returning visitor continues their thread. A new `GET /api/v1/public/chat/{org_public_id}/status` endpoint (always 200, one boolean, same non-answer for "disabled" and "no such org") lets the script decide whether to render the bubble at all — `public_chat_enabled` is now genuinely respected client-side, not just server-side. Dashboard: a "Add chat to your website" panel on Settings → Integrations (plain-language copy per the customer profile, never "widget" or "embed" in visible text) shows the exact script tag with the org's real `public_id`, a copy button, a live preview (`widget-preview.html`, loaded in an iframe so the preview can never affect the dashboard's own styles), an on/off toggle (`POST /organizations/{id}/public-chat/enable|disable`, new), and a "get a new code" rotate action. Verified end to end in a real browser against a live API: signed up, opened the panel, saw the real script tag, opened the bubble in the preview iframe, sent a message, got the plain-language "chat isn't available" apology (expected — no `OPENAI_API_KEY` in this environment) rather than a stack trace or leaked detail. | Closes the "how do I actually put a chatbot on my site" gap in the demo script. |
| ~~**Approval notification + conversation takeover**~~ | `approvals.py` wrote a database row and nothing else; the owner only found out by looking. No way for a human to answer a live conversation directly. | ✅ **RESOLVED 2026-08-16.** Pluggable `Notifier` interface (`src/notifications/notifier.py`): `ConsoleNotifier` (default, always works, structured log line) and `EmailNotifierStub` (correctly shaped — recipient/subject/body — but does not send; no-ops with a loud warning when `NOTIFY_EMAIL_PROVIDER_API_KEY` is unset, never fakes success). Fired from `approvals.create_pending` right after commit, fire-and-forget with its own error handling so a dead notifier can never fail the approval itself. Topbar badge already polled every 20s (`lib/approvals-context.tsx`) — confirmed live, no changes needed. **Conversation takeover:** `conversations.mode` (`"agent"` \| `"human"`, migration `e4a29d6f1c3a`). `POST /conversations/{id}/takeover`, `/handback`, and `/messages` (owner/admin only). While `mode == "human"`, `run_agent` records the inbound message but returns without calling the model or any tool — proven directly by `tests/test_takeover.py`, not just asserted. A human message is stored with `role="human"` (never `"assistant"`), shown distinctly in the transcript UI and in Activity ("Riverside Owner sent a message directly"). New `/conversations` list + detail page in the dashboard with Take over / Hand back and a compose box that only appears once a human is in control. **Known limitation, not a bug:** a human message on a `web_chat` thread has no open connection to push to — the visitor's browser already got its HTTP response. It's recorded and appears the next time that thread is polled or reopened, same as any async handoff would work in a widget this size. WhatsApp threads *do* get an immediate push (`src/tools/whatsapp.py`). | Closes both trust-critical demo-script beats: "can I stop it before it sends" (already had approvals; now the owner is told) and implicitly extends "can I see what it did" to "can I step in." |

**Recommendation:** these are Phase 1 commitments, not nice-to-haves. The approval gate and the inbound channel are the two that most change whether this is demoable as described. **As of 2026-08-15 all six rows are closed on the backend.** The remaining Phase 1 work is frontend: the analytics dashboard page and the workflow screens, both being built against the contracts above.

Two things the Workflow Engine surfaced that need a founder decision rather than more code — both written up in `needs-founder-input.md` (§12 no-show truth source, §13 recall interval per treatment). Neither blocks the demo; both change how honest the no-show claim is with a real customer.

---

## A2. Found only by running the full stack (2026-08-15)

Everything above was verified by tests, builds and screenshots against *mocked or absent* backends. Standing the whole stack up against real Postgres + Redis with the demo seed surfaced two defects that no amount of unit testing would have caught, because both only appear for a **pre-existing user** — which is every demo and every returning customer.

| Defect | Cause | Fix |
|---|---|---|
| **A returning user had no active organization.** Login succeeded, then every org-scoped request 404'd with "That organization doesn't exist." The entire product was unusable for anyone who wasn't creating an org for the first time. | The client only set `X-Organization-Id` inside `organizations.create` (the onboarding path). There was no endpoint to ask "which organizations do I belong to?", so a returning session had a valid token and no tenant. | Added `GET /api/v1/organizations` (scoped to accepted memberships, so it cannot reveal an org the caller isn't in) and made the login flow resolve and store the active org. |
| **Editing an already-applied Alembic migration left a stale schema.** `organizations.business_type` was missing on a database that had been migrated *before* the edit, so the demo seed crashed. | The `business_type`/`primary_goal` columns were added by editing the initial migration in place rather than adding a new revision. Alembic had already recorded that revision as applied, so the edit never ran. | The chain is correct from scratch — verified by dropping and recreating the database, after which all four migrations apply and the schema matches the ORM. **Lesson, not a shipping bug:** never edit an applied migration; anyone who had already migrated needs a fresh database or a repair revision. |

**Process point worth keeping:** these were the two most severe defects found in the entire build, and both were invisible until the stack ran end to end with seeded data. Standing up the real thing should happen earlier next phase, not as a final check.

---

## B. Ahead of plan — built beyond documented scope

Each of these was added because something downstream genuinely needed it. None were speculative, but they are still additions the founder should sign off on.

### Backend

| Addition | Why it was added | Cost |
|---|---|---|
| `business_type` + `primary_goal` columns on `organizations` | The onboarding flow captures what kind of business the customer runs, to personalize agent prompts and demo/empty-state copy. Directly supports the customer-profile strategy. | Two nullable columns. Trivial. |
| `GET /knowledge` (document list) | The Knowledge page needs to show what's been uploaded. The spec listed upload + search but no list endpoint; the UI is unusable without it. | One endpoint, grouped query. Small. |
| `GET /audit-logs` (Activity feed) | Audit logging was in scope as a *table*; exposing it to the owner as a readable "Activity" feed was not explicitly specced, but the trust story in the customer profile depends on the owner being able to see what agents did. | One endpoint + plain-language summarization. Small. |
| `POST /integrations/{provider}/connect` | The UI needs a one-click connect affordance. Currently returns an honest `coming_soon` for every provider, since no OAuth app exists yet. | One endpoint. Trivial. |
| `organizations.public_id` + `public_chat_enabled` | The public web-chat widget needs to address a business by something that is neither the internal tenant UUID nor the guessable slug, and an owner needs a way to switch the widget off or rotate a link that's being abused. | Two columns, one generator, one rotate endpoint. Small. |
| `GET /organizations/{id}` and `POST /organizations/{id}/public-chat/rotate` | There was no way to *read* an organization back, so the owner could not retrieve the public id needed to embed the widget. The read also mints a `public_id` for orgs created before the feature existed, which removes the need for a data backfill. | Two endpoints. Small. |
| `GET /conversations` and `GET /conversations/{id}` | Conversation persistence is worthless to the owner without a way to browse it. The spec implied history but listed no endpoint. | Two endpoints. Small. |
| `escalate` step type + `workflow.escalation_raised` activity event | The deep dive §4 lists "what if it breaks and I lose a lead?" as an open objection with **no escalation path**. A workflow that can only act through an integration is useless as a safety net on a machine with nothing connected, so escalation is internal: it writes to the Activity feed and needs no credential and no approval. The public web-chat handler now also persists the customer's message when the agent reply *fails*, so a broken enquiry is still an enquiry. | One step type, one event name, one salvage path. Small. |
| `GET /analytics/summary` | Committed as a "dashboard" in the scope table but with no endpoint specified. Contract agreed with the frontend before building. | One endpoint, four queries. Small. |
| `contacts` table | The market analysis flagged that there was nowhere to put a customer's identity, and lead capture is a core Receptionist function. Populated today by the WhatsApp webhook and by the demo seed; the web-chat widget does not yet ask for a name. | One table. Small. |
| Auto-derived org slug | Removed the client-supplied `slug` field — an SMB owner should not be asked to choose a URL slug during a sub-minute onboarding. Server derives and de-duplicates it. | Net *simplification*. |
| `evals/runner.py`: `mock_turns` + `blocked` expectation | Eval coverage was 2 scenarios, both Receptionist, both happy-path — the market research names eval coverage as the single highest-leverage reliability lever. Expanding to 14 scenarios across 4 agents needed the harness to run deterministically in CI without a live AI provider (a scenario now scripts its own gateway responses) and to express "this tool call must be refused" (a model asking for a tool outside its `allowed_tools`), which the original harness had no way to assert. | One optional field per scenario, one new expectation flag. Backward compatible — a scenario with no `mock_turns` still spot-checks against a real gateway exactly as before. |
| `GET /api/v1/public/chat/{org_public_id}/status`, `POST /organizations/{id}/public-chat/enable\|disable` | The embed script needs to decide whether to render at all without attempting a real chat turn, and the dashboard needed a way to actually flip `public_chat_enabled` — it existed as a column with no endpoint to change it. | Three endpoints, no schema change (`enable`/`disable` reuse the existing column). |

### Frontend

| Addition | Why it was added | Cost |
|---|---|---|
| Custom design system (palette, type pairing, spacing scale) | The roadmap said "Next.js + Tailwind + shadcn/ui" but specified no visual identity. Shipping stock shadcn would have read as a template in a pitch. | Design time only. |
| Onboarding business-type/goal step | Feeds the personalization above; supports the "under 10 minutes to value" goal in the customer profile. | One screen. Small. |
| 3D runtime constellation + premium redesign | Founder-directed after the initial build. Makes the shared-runtime differentiator visible. See `scope-additions-frontend.md`. | 5 new deps (`three`, `@react-three/fiber`, `@react-three/drei`, `@types/three`, `framer-motion`). **Largest single scope addition to date.** Bundle impact contained (151 kB on the home route vs ~101 kB elsewhere; 3D lazy-loaded). |
| Dashboard home / overview route (`/`) | Somewhere for the constellation to live and to orient a first-time owner; the original route list went straight from auth into per-agent chat. | One route. |
| Approvals UI (tray, inline cards, topbar badge) | Required by the backend approval gate, which *was* specified in the architecture doc — so in-scope-by-implication rather than a true addition. | Moderate. |

---

## B2. Temporary simplification — the Receptionist's scripted chat (2026-09-03)

**Founder-directed:** *"keep everything predefined, give options to user to select from and reply according to that, we will build the proper chatbot later."*

The Receptionist now answers from a fixed decision tree instead of the AI pipeline. This is a **downgrade in capability but an upgrade in working state**: with no `OPENAI_API_KEY` configured, every chat surface previously returned a 503, so both the dashboard chat and the public widget were non-functional. They now work end to end with zero AI dependency.

| Aspect | Detail |
|---|---|
| **Scope** | `receptionist.yaml` only. The other five agents are untouched and still use `run_agent` (still 503 without a key — out of scope). |
| **How it's selected** | A `chat_mode: scripted` field on the agent config. `api/v1/agents.py` and `api/v1/public.py` branch on it. |
| **What it does NOT touch** | `agents/runtime/pipeline.py` (`run_agent`) is fully intact, tested, and unused for this agent only. The approval gate, takeover, tool permissions, and untrusted-content framing all still apply on the AI path. |
| **Reverting** | Delete `chat_mode: scripted` from the YAML. No other change required — the UI falls back to free-text automatically whenever a response carries no `options`. |
| **Honesty** | Every "I've noted / passed this to the front desk" line describes what genuinely happens (an Activity entry is written). Nothing claims a real booking, notification, or calendar write. Activity labels these `agent.scripted_reply` → "Answered using the guided menu", never implying free-form reasoning. |
| **Composer** | Disabled while a menu is on screen, because the scripted flow only understands a picked option — typed text would silently bounce the visitor to the main menu. Says so plainly rather than accepting input it can't use. |
| **Test impact** | Six `test_public_chat.py` tests exercise the AI path on the public endpoint. Rather than weaken them, they now force AI mode via `_force_ai_mode()`, so that machinery keeps real coverage for when the flag flips back. |

**To remove later:** `src/agents/scripted/` (2 files), the `chat_mode` field, the two branch points, and the `agent.scripted_reply` case in `audit.py`.

---

## B3. Bug found by embedding the widget on a real third-party origin (2026-09-03)

**The widget could never have worked on a customer's website.** CORS allowed only the dashboard origin (`http://localhost:3000` / the configured allowlist), but the entire point of an embed script is that it runs on every customer's own domain. The browser blocked it before the first request completed, so the bubble never rendered.

Fixed with a second, tightly-scoped CORS layer for `/api/v1/public/` only: wildcard origin, **no** `Access-Control-Allow-Credentials`, and it answers the preflight itself (the strict inner middleware 400s an unknown origin before the widget gets a reply). Every authenticated route keeps the strict allowlist — pinned by `test_authenticated_routes_keep_the_strict_allowlist`.

Safe because these endpoints authenticate by opaque public id and signed conversation token, never by cookie — a wildcard origin grants a caller nothing it couldn't already do with `curl`.

**Process point, again:** this is the second time a defect was invisible to tests, builds and screenshots, and only appeared when the thing was actually run the way a customer would use it. The unit tests passed against the same endpoint the whole time — they just never crossed an origin.

---

## C. Deliberate deviations from the spec's stated approach

| Deviation | Spec said | We did | Reasoning |
|---|---|---|---|
| Test infrastructure | Tests against the docker-compose Postgres | sqlite + aiosqlite, with fakeredis | Keeps `pytest` runnable with zero external services, which matters for CI and for onboarding a new engineer. **Tradeoff:** pgvector's `<=>` operator is Postgres-only, so semantic search is *not* exercised by the automated suite — it's been validated manually only. This is a real coverage gap worth closing before Phase 2. |
| Integration token storage | Not specified | Plaintext in the `integrations` table | Flagged as a known deferral by the backend build. Under review in the current hardening pass. Should not ship to a real customer as-is. |

---

## D. Open tensions for founder decision

1. **Visual direction vs. stated buyer psychology.** `docs/customer-profile.md` argues for "calm, professional, not flashy — dependable infrastructure" because the buyer is a non-technical owner whose top hesitation is data privacy. The current direction (striking, highly interactive, 3D signature element) pushes the other way. These are reconcilable — a premium *instrument* rather than a consumer toy — but it is a real tension and the profile should be updated to reflect whichever way you want to land, so future work stops pulling in two directions.

2. **Six agents at demo depth vs. one agent at production depth.** The original market research recommended proving one agent (Receptionist) before generalizing; the founder chose full breadth for pitch legibility. That decision stands, but it means no single agent is yet production-hardened. Worth an explicit call before the first paying pilot on which agent gets deepened first.
