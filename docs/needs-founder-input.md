# Needs Founder Input

Everything below is fully built (code, data model, error handling) but cannot
be turned on until the founder supplies real credentials from the listed
provider. Nothing on this list blocks building, testing, or demoing the rest
of AURA — every feature that needs one of these shows a clean "please connect
this" message instead of crashing when it's missing.

## 1. OpenAI API key
**What:** an API key from https://platform.openai.com/api-keys, billing enabled.
**Why:** every AI feature — agent conversations, embeddings for the knowledge
base — goes through this. Without it, `POST /agents/{slug}/chat` and the
knowledge upload/search endpoints return a 503 with a plain "AI features
aren't set up yet" message.
**Where it goes:** `OPENAI_API_KEY` in `.env`.

## 2. Google Cloud OAuth app (Calendar + Gmail)
**What:** a Google Cloud project with the Calendar and Gmail APIs enabled, an
OAuth 2.0 client (client ID + secret), and a configured consent screen +
redirect URI.
**Why:** the Receptionist and Executive Assistant agents' calendar/email
tools (`src/tools/calendar.py`, `src/tools/gmail.py`) need a real Google OAuth
token per customer organization to book appointments or send/read email.
**What's already built:** the token storage model (`integrations` table) and
the tool code that uses a stored token. **What's missing:** the actual OAuth
consent redirect flow — right now an org owner would have to paste a token
manually via `POST /api/v1/integrations`, which only works for testing.
**Where it goes:** `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET`.

## 3. WhatsApp Business Cloud API
**What:** a Meta developer app with WhatsApp Business Cloud API access, a
phone number ID, and a permanent access token.
**Why:** the Receptionist agent's WhatsApp tool (`src/tools/whatsapp.py`)
sends customer messages through this API.
**Where it goes:** `WHATSAPP_PHONE_NUMBER_ID` / `WHATSAPP_ACCESS_TOKEN` (per
customer org, stored via the integrations endpoint).

## 4. Slack app
**What:** a Slack app with a bot token (`chat:write` scope) installed into
each customer's workspace.
**Why:** used across all six agents for internal notifications (e.g. "a new
lead came in," "an appointment needs review") — `src/tools/slack.py`.
**Where it goes:** `SLACK_BOT_TOKEN` (per customer org).

## 5. HubSpot private app token
**What:** a HubSpot private app token with CRM read/write scopes, created by
each customer in their own HubSpot account (or a HubSpot OAuth app if we want
a one-click "Connect HubSpot" flow later).
**Why:** the Sales and Marketing agents read/update contacts and deals
through this — `src/tools/hubspot.py`.
**Where it goes:** `HUBSPOT_ACCESS_TOKEN` (per customer org).

## 6. Shopify Admin API access
**What:** a Shopify custom app access token and the store's `*.myshopify.com`
domain, created by each customer in their own Shopify admin.
**Why:** the E-Commerce Intelligence agent's order/inventory/sales tools
(`src/tools/shopify.py`) call the Shopify Admin API directly.
**Where it goes:** `SHOPIFY_ACCESS_TOKEN` / `SHOPIFY_SHOP_DOMAIN` (per
customer org).

---

**Common pattern for #2–6:** every one of these tools already shares
`src/tools/oauth_common.py` for reading/writing per-org tokens from the
`integrations` table, and raises a clean, plain-language error (never a stack
trace or "OAuth"/"token" jargon shown to the customer) when a tool is called
before its integration is connected. The only remaining work once real
provider credentials exist is building the actual OAuth consent redirect for
Google (WhatsApp/Slack/HubSpot/Shopify use pasted tokens by design at this
scale, matching how most SMB tools connect these).

## 7. Application encryption key (`ENCRYPTION_KEY`)
**What:** a Fernet key, generated once with
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`,
stored in the deployment's secret manager (not in git, not in `.env.example`).
**Why:** integration access/refresh tokens for Google, WhatsApp, Slack, HubSpot
and Shopify used to sit in the `integrations` table in plaintext — a database
dump alone was enough to take over a customer's inbox and calendar. They are
now encrypted at rest with this key (`src/core/crypto.py`). Data privacy is the
#1 stated hesitation of our buyers (see `docs/customer-profile.md`), so this is
worth being able to answer directly in a sales conversation.
**Migration path:** none needed. Encrypted values carry an `enc:v1:` prefix and
anything without it is read as legacy plaintext, so existing connections keep
working and are re-encrypted the next time they're saved. To re-encrypt
immediately, re-save each connection through `POST /api/v1/integrations`.
**Where it goes:** `ENCRYPTION_KEY` in the environment. **The API refuses to
start in production without it** (same guard as `JWT_SECRET`); development and
test run without one and log a warning instead.
**Decision needed:** where the key is stored and who can rotate it. There is no
key-rotation path yet — rotating today means re-connecting every integration.

## 8. Business timezone at onboarding
**What:** a decision, not a credential — do we ask the owner for their timezone
during signup, or infer it from the browser and let them correct it?
**Why:** the calendar tool now sends an explicit timezone on every read and
write (`organizations.timezone`, falling back to `DEFAULT_TIMEZONE`). Without a
real value per organization, "book me Tuesday at 3pm" is booked at 3pm UTC —
wrong for every customer outside the UK in winter. The column and the fallback
exist; nothing in the product asks for the value yet.
**Where it goes:** `organizations.timezone` (IANA name, e.g. `Europe/London`);
deployment-wide default in `DEFAULT_TIMEZONE`.

## 9. How owners are told an action is waiting for approval
**RESOLVED 2026-08-16 — mechanism built, one credential still missing.**
Consequential agent actions — booking or cancelling an appointment, sending an
email or WhatsApp message, changing a CRM contact — queue in `tool_approvals`
and wait for an owner or admin to approve them (`GET /api/v1/approvals`).
`src/notifications/notifier.py` now fires a notification the moment one is
created (`ToolApproval.create_pending`), through a pluggable `Notifier`
interface:
- **`ConsoleNotifier` (default, live today, no credentials needed).** Writes a
  structured log line with the org, agent, tool, and plain-language summary.
  This is not a placeholder — every deployment has logs, and it's what makes
  "did the notification fire" provable in `tests/test_notifications.py`
  without a mail account.
- **`EmailNotifierStub` (correctly shaped, not wired to a real provider).**
  Subject, recipient resolution, and body are already written correctly for a
  transactional-email provider. It does **not** send — with no provider key
  configured it logs a clear "not configured" warning and returns, never
  fakes success.

**What's still needed:** a transactional-email provider key (SendGrid,
Postmark, or similar) in `NOTIFY_EMAIL_PROVIDER_API_KEY`, plus a decision on
where the recipient email comes from (today `EmailNotifierStub._recipient`
returns `None` — it needs the owner's membership email looked up, which is a
few lines once there's a real provider to send through). Set
`NOTIFY_CHANNEL=email` once both exist. In the dashboard, the topbar
Approvals badge already polls every 20 seconds (`lib/approvals-context.tsx`)
so a pending approval surfaces without a manual refresh while the owner is in
the app — that part needed no founder input.
**Separately still open:** which actions genuinely need a human in Phase 1 —
the current per-agent lists are in `src/agents/configs/*.yaml` under
`requires_approval` and are a starting guess, not a researched default.

## 10. WhatsApp inbound webhook (Meta Cloud API)
**What:** in addition to the sending credentials in #3, the inbound direction
needs (a) a **Meta app secret**, (b) a **verify token** — any random string we
choose, entered identically in the Meta dashboard and in our environment — and
(c) a **public HTTPS callback URL** for the deployed API, registered as the
webhook for the `messages` field on the WhatsApp product.
**Why:** this is what makes "your Receptionist answers your customers" literal
rather than a demo of the owner typing as the customer. A customer messages the
practice's WhatsApp number, Meta POSTs it to us, the Receptionist answers on the
same thread.
**What's already built:** `GET/POST /api/v1/public/whatsapp/webhook` —
the verification handshake (`hub.mode`/`hub.verify_token`/`hub.challenge`),
`X-Hub-Signature-256` HMAC validation over the raw request body, multi-tenant
routing (the inbound `phone_number_id` is matched against the `phone_number_id`
each org stored when it connected WhatsApp), contact capture, conversation
persistence, and the reply send. Signature rejection and the handshake are
covered by tests.
**What cannot be verified without the credentials:** the end-to-end round trip.
Nothing exercises a real Meta payload, a real signature from Meta's own secret,
or the outbound reply hitting the Graph API. Expect one round of small fixes on
the day the credentials arrive — this is built to be *ready*, not proven.
**Where it goes:** `WHATSAPP_VERIFY_TOKEN` and `WHATSAPP_APP_SECRET` in the
environment; the per-org `phone_number_id` continues to go in the integration
metadata via `POST /api/v1/integrations`.

## 11. Where the public web-chat widget is allowed to run
**What:** a decision, plus one deployment setting. `POST /api/v1/public/chat/{public_id}`
is the embeddable website chat — the only unauthenticated endpoint in the
product. Two things need a call:

**(a) Cross-origin access.** The API currently allows only the origins in
`CORS_ORIGINS` (the dashboard). A browser on `riversidedental.co.uk` cannot
call it until that customer's domain is allowed. Options: allow any origin for
the `/public` routes only (simplest, and the endpoint is designed to be safe
without origin trust — the org id is opaque, everything is rate limited, and
nothing consequential happens without owner approval), or keep an allowlist of
customer domains per organization (tighter, but adds an onboarding step and a
support burden). **Recommendation: allow any origin on `/public` only**, and
revisit if abuse appears. Not done yet because it changes the deployed CORS
posture and should be a deliberate choice.

**(b) Client IP behind the proxy.** The per-IP rate limit reads the socket
address by default. Once the API sits behind a load balancer or CDN, that is
the proxy's address for every visitor, and the limit becomes global rather than
per visitor. Set `TRUST_PROXY_HEADERS=true` **only** once a proxy that
overwrites `X-Forwarded-For` is in front of it — enabling it while the API is
directly reachable lets any visitor forge the header and skip the limit
entirely.

**Also worth knowing:** the current caps are a starting guess, not a researched
default — 20 messages per IP per 5 minutes, 10 per conversation per minute, 60
messages per conversation, 2,000 characters per message. All five are settings
(`PUBLIC_CHAT_*`), so tuning them is a config change, not a deploy.

## 12. What counts as a no-show (the truth source)
**What:** a decision, and possibly one integration. The appointment-reminder
workflow is built and running, but AURA has no appointments table and no
attendance data — Google Calendar tells us an event exists, never whether the
patient turned up.
**Why it matters:** the whole renewal argument in the segment deep dive rests on
the $215k–455k a year a 3–5 provider practice loses to no-shows, and the
workflow is what turns that number into a promise. Today the template infers a
no-show from **"never replied to the reminder"**, which is a real signal but not
the truth: plenty of patients attend without replying, and a few reply and still
don't come. That means the rebooking offer will sometimes land on someone who
sat in the chair yesterday, which is the kind of small wrongness an owner
notices immediately in a pilot.
**Options:** (a) keep the reply-based inference and say so plainly in the demo;
(b) add a one-tap "did they attend?" prompt in the dashboard the morning after,
which also makes good demo material; (c) get attendance from the practice
management system — Boulevard first, per the deep dive's ranked gap list — which
is the real answer and the one that also fixes the "will it book into
Boulevard?" objection.
**Recommendation:** (b) for the pilot, (c) for GA. Not built either way, because
which one is right depends on how the first pilots are run.

## 13. The recall interval, per treatment
**What:** a clinical decision. The treatment-recall workflow runs on a
configurable interval stored per organization
(`workflow_definitions.trigger_config.recall_after_days`, currently defaulted to
**90 days**).
**Why it matters:** 90 days is a placeholder, not a researched default. A
hygiene recall is usually 12 weeks, filler 16–24, and a routine dental
examination 6 or 12 months depending on risk. One number for a whole practice
will be wrong for most of its patients, and a recall message that arrives too
early reads as a sales push rather than care — exactly the tone the customer
profile says loses this buyer.
**What's already built:** the interval is data, so changing it per customer is a
row update, not a deploy. What is *not* built is per-treatment-type intervals,
because we don't record what treatment a contact had.
**Decision needed:** whether Phase 1 ships one interval per practice (fine for a
pilot) or per treatment type (needs a treatment field on `contacts`, and a list
of treatment types from a clinician).

## 14. Whether the three workflow templates are on by default for a new customer
**What:** a decision. New organizations get all three templates installed and
**switched off**; the owner turns each on from the dashboard. The demo
organization has all three on so the screens aren't empty.
**Why:** enabling an automation means it starts messaging that customer's
patients. Defaulting that to on is not a decision engineering gets to make,
even though every consequential send still queues for approval.
**Worth knowing:** with the approval gate in front of them, "on" today means
"drafts and queues", not "sends". If white-glove setup is part of the pilot (§3
of the deep dive says setup is where pilots die), turning them on during
onboarding with the owner watching is probably the right flow — but that's a
sales-motion decision, not a code one.
