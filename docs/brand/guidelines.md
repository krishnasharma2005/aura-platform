# Mesnium brand guidelines — the parts that decide how the product looks and speaks

Distilled from `mesnium-executive-brandbook-revised-v3.pdf` (Executive Edition 1.0). Page numbers refer to that PDF. Exact values (colours, type scale, motion timings) are in [`tokens.json`](tokens.json); the approved logo board is [`approved-reference-board.png`](approved-reference-board.png); the extracted artwork is in `apps/web/public/brand/` (see [`README.md`](README.md)).

This file covers only what affects the product. The brandbook also specifies a website, a coming-soon page, social templates and a slide system; those are separate deliverables and are not summarised here.

## Positioning (p. 3–5)

- **What it is:** "the operational intelligence layer between human intent and business execution." It understands context, coordinates connected systems, and carries work toward an outcome, with people in control of judgement.
- **For:** business owners and teams who want work accomplished, not another platform to manage.
- **Against:** "More capable than an assistant. More accessible than infrastructure."
- **Name:** from *mesne* — intermediate, situated between. Say MEZ-nee-um. Never change the spelling or split it into two words.

## Voice (p. 4, 37)

Six words: **intelligent, precise, calm, confident, operational, human.** Clear, concise, direct, technically credible.

> Say "Your report is ready for review", not "Our revolutionary AI has transformed your workflow."

Messaging territories (treat as a set; validate legal availability before registering any as a tagline):

| Territory | Line |
|---|---|
| Primary | The intelligent middle. |
| Outcome | Your business, coordinated. |
| Product | From intention to accomplished. |
| Behavioural | Understand. Coordinate. Execute. |

## What Mesnium never looks or sounds like (p. 6, 37)

A robot persona, a crypto project, a neon developer tool, a generic automation agency, or a crowded dashboard. No glowing brains, hype, false urgency or decorative complexity. No exaggerated autonomy claims, no purely decorative motion, no overcrowded technical diagrams, **no unverified trust or compliance badges.** Security claims are published only once verified (p. 27).

## Colour use (p. 9–10, 37)

Crimson is "a deliberate signal for one key action, a focal point, or brand emphasis" — 5–10% of a composition. Never rely on colour alone for meaning: pair every semantic colour with an icon and a written status. Danger actions use the error colour, explicit wording and a confirmation step — not signature crimson alone (p. 20).

## Product UI (p. 19–21)

**Navigation vocabulary:** Chat · Work · Automations · Knowledge · Inbox · Connections · Activity. (Settings, Approval, Agent, Memory, Search and Notifications also appear in the icon set.)

**Agent states** — plain-language, visible, and the same everywhere:
Ready · Understanding your request · Working on your report · Completed · Needs your attention (with an icon).

**System states**

| State | Wording from the brandbook |
|---|---|
| Empty | "No work here yet. Tell Mesnium what needs doing." |
| Error | "We couldn't connect. Your work is saved. Try again." |
| Loading | Name the actual work — not "AI thinking". |

**Approval card** (the pattern the product is built around): "Your approval is needed — A customer follow-up is ready to send. Review before it leaves your business." Action: "Approve follow-up".

**Business components** (the shape of the sample text, p. 20):

| Component | Example |
|---|---|
| Customer | Maya Chen · Northline · Last contact 2 days ago |
| Automation | Weekly summary · Every Monday · Review before sending |
| Connection | Google Workspace · Connected · Read and draft permissions |
| Knowledge | Operations handbook · Updated today · Available to your team |
| Workflow | New customer · 3 steps · Human approval before invoicing |
| Activity | Report compiled · 09:42 · Sources and decisions recorded |

**Workspace greeting** (p. 19): "Good morning, Alex." / "Your business, coordinated. You stay in control."

## Motion (p. 17–18)

Four tempos — 160 ms respond, 240 ms reveal, 480 ms resolve, 640 ms introduce — one easing for entrances (`cubic-bezier(0.22, 1, 0.36, 1)`) and linear for progress. No bounce, elastic scaling, overshoot, rotation, glow or looping logo. Always name the current state in text, respect reduced motion with the same end state, and stop at approval boundaries. Details in `tokens.json`.

## Imagery (p. 6)

Observe work: close-up material detail, quiet operational environments, human gestures. High-contrast neutral photography; diagrams stay vector-based. No staged teams, robot faces, glowing brains or neon networks.

## Before release (p. 38)

The brandbook's own checklist: test the favicon at 16 px, keyboard navigation, screen-reader names and contrast in each final application; confirm the original SVG/AI logo master; trademark clearance and real-world distinctiveness are separate, independent requirements ("this is a developed identity proposal, not a claim of legal uniqueness").
