# AURA — Customer & Target Audience Profile

*Read by: agent prompt design, frontend copy/UX, demo-org seeding. Keep this in view for every product decision — prompts, copy, empty states, error messages, onboarding.*

## Primary ICP (Phase 1)

**Local and small-to-midsize service businesses, 3–50 employees, owner-operated or small management team.** Concretely: medical/dental/aesthetic clinics, salons and spas, contractors and home-service businesses, small agencies (marketing/creative/consulting), and small e-commerce brands (Shopify-based).

- **Buyer:** the owner or office manager — not a technical buyer. They evaluate on "does this save me time/money this week," not architecture.
- **Budget reality:** willing to pay $300–$1,500/month for a tool that demonstrably replaces missed bookings, slow replies, or manual admin work (matches 2026 SMB agent pricing norms).
- **Technical comfort:** low-to-moderate. They use WhatsApp, Gmail, Google Calendar, Instagram, and one CRM/e-commerce tool daily. They do not want to learn a new paradigm ("agents," "RAG," "tokens" are not words that should appear in the product).
- **Trust posture:** cautiously optimistic about AI ROI, but **data privacy/security is their #1 hesitation** (49% cite it as the top adoption barrier). Every touchpoint that gives AURA access to their calendar, inbox, or CRM needs to visibly explain what it can and cannot do, and show a human-approval option for anything consequential.
- **Buying trigger:** a missed booking, a slow reply that lost a customer, or a busy season where the front desk/inbox is overwhelmed. The demo needs to land on this pain within the first two minutes.

## Secondary audience (Phase 1, smaller weight)

Founders/ops leads at slightly larger SMBs (up to ~100 employees) evaluating AURA as a pitch-stage platform — this is the audience for the "one platform, six agents" narrative, not just the single-agent ROI story. They care about extensibility and want to see the roadmap, not just today's feature set.

## What this means for the product

- **Copy:** plain language everywhere. "Never miss a booking," not "autonomous appointment orchestration." Agent names stay human ("Receptionist," "Assistant") not technical ("Agent_01").
- **Onboarding:** must get a business from signup to "the Receptionist can answer a real question" in under 10 minutes — no multi-day setup.
- **Trust UI:** every tool connection (Calendar, Gmail, WhatsApp, CRM) shows a plain-language permission summary before connecting, and every consequential action an agent takes should be logged somewhere the owner can see in one click (this is the Audit Log, but it should be labeled "Activity," not "Audit Log," in the UI).
- **Visual tone:** professional and calm, not flashy/consumer. This is a business tool an owner trusts with their customer relationships — steer away from playful SaaS-startup visual clichés (gradient hero, emoji icons) and toward something that reads as dependable infrastructure: clear hierarchy, restrained color, real data in every screen (not empty-state illustrations).
- **Demo narrative:** seed a demo org as a fictional clinic ("Riverside Dental") — this is the flagship Receptionist story — plus a small e-commerce brand for the E-Commerce Intelligence agent, so both halves of the ICP see themselves in the product.
