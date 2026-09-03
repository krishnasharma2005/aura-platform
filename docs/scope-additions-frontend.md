# Frontend Scope Additions

*Reconstructed from the diff after the redesign session ended early — the agent didn't reach this file itself, so treat it as accurate on substance but not necessarily exhaustive on detail. Feeds `scope-ledger.md` §B.*

## New dependencies (5)

| Package | Why | Note |
|---|---|---|
| `three` | 3D runtime constellation on the dashboard home | The headline addition |
| `@react-three/fiber` | React renderer for three.js | |
| `@react-three/drei` | Helpers (controls, text, geometry) | |
| `@types/three` | Types | dev-only |
| `framer-motion` | Interaction/entrance choreography across all screens | Used well beyond the 3D |

These were not in the Phase 1 plan, which specified only "Next.js + Tailwind + shadcn/ui". They are the single largest scope addition in the project so far. Bundle impact is contained: the dashboard home is 151 kB first-load vs ~101 kB for other routes, and the 3D is lazy-loaded behind a static SVG fallback.

## New surfaces / capabilities

| Addition | Justification | In original plan? |
|---|---|---|
| **3D runtime constellation** (`components/runtime/`, `lib/runtime-graph.ts`) — six agents orbiting a shared "ONE RUNTIME" core, over three rings representing shared memory / documents / connected accounts | Founder-directed. Makes the platform's actual differentiator (one shared runtime, not six point tools) visible, which a sidebar list cannot do. | No — founder-directed after the initial build |
| **Dashboard home / overview route** (`/`) | Somewhere for the constellation to live and to orient a first-time owner. The original route list went straight from auth into per-agent chat. | No |
| **Approvals UI** (`components/approvals/`, `lib/approvals-context.tsx`, topbar badge) | Required by the backend human-approval gate, which *was* specified in the architecture doc. Arguably in-scope-by-implication rather than an addition. | Implied, not itemized |
| **Motion system** (`lib/motion.ts`) | Shared easing/duration tokens so animation is consistent rather than ad-hoc per component. | No |
| Design system (palette, type pairing, spacing scale) | The plan specified a stack but no visual identity; stock shadcn would read as a template in a pitch. | No |

## Verification status

`npm run build` and `npm run lint` both pass. I verified the dashboard home and the Receptionist chat visually at 1440×900 — both render correctly and the 3D animates in as intended.

**Not verified** (the session ended before this): mobile widths, the remaining routes (Knowledge, Activity, Settings, Integrations, auth/onboarding), dark theme, and `prefers-reduced-motion` / non-WebGL fallback behavior. The static SVG fallback does render — it's visible during 3D load — but its reduced-motion path wasn't explicitly tested.

## Observations worth a second pass

1. **Label collision in the 3D.** At default rotation the "Receptionist" and "Assistant" labels overlap the core sphere and each other; "Sales"/"Marketing" crowd on the right. Legible but not clean.
2. **Low contrast in places.** Several secondary text blocks (chat empty state, the ring labels in the constellation) sit at a very light grey on near-white. Worth an accessibility contrast check before this goes in front of customers — some of it likely fails WCAG AA.

---

# QA pass — additions and changes

Written during the QA sweep that closed out the two observations above. Nothing
here is a new feature; it is all repair, plus three small tokens/utilities that
exist so the repairs are systematic rather than per-component patches.

## New design tokens / utilities (4)

| Addition | Where | Why |
|---|---|---|
| `--subtle-foreground` → `text-subtle` | `app/globals.css`, `tailwind.config.ts` | The app had a third, quieter text tier written as alpha washes (`text-muted-foreground/70`, `/60`, `/45`, `/40`). Alpha lands wherever the backdrop happens to be, and all four fell under AA. This is a real colour, measured, one step below `muted-foreground` — the hierarchy is preserved, the failures are not. Every `muted-foreground/NN` in the codebase now uses it. |
| `--input` split from `--border` | `app/globals.css` | Card hairlines only separate two surfaces; a form-control border is the only thing that says "this is a control", so it has to clear WCAG 1.4.11's 3:1. `--border` is unchanged, so the change is confined to inputs and the chat composer. |
| `.tap` / `.tap-h` | `app/globals.css` | Grows a control to a 44px hit area on coarse pointers and phone widths only, so desktop keeps its compact instrument density. Applied to the Button primitive and to the hand-rolled pills (activity filters, settings tabs, chat suggestions, top-bar controls). |
| `errorMessage(err, fallback)` | `lib/utils.ts` | The backend's own sentence still wins when it has written one. A body that is only an HTTP status phrase ("Not Found") is replaced by the caller's plain-language fallback — that string was rendering under "Your documents". `lib/api-client.ts` is untouched. |

## New capability in an existing component

| Addition | Why |
|---|---|
| `RuntimeGraphStatic` gained a **`compact` layout** (a 460-unit viewBox alongside the 800-unit one), and `RuntimeScene` gained a **`compact` prop** (camera pulled back, smaller label pills) | The diagram's type scales with its box. The wide drawing's 13px labels render at ~5.5px inside a 340px phone column — unreadable, and that drawing is what reduced-motion and no-WebGL visitors get. The compact layout drops the three ring labels rather than shrinking them; the legend directly beneath already names all three with a sentence each. |

## Verification status (updated)

Swept all 16 routes at 1440×900 and 390×844, in light and dark, with an
injected in-page auditor computing real composited contrast ratios, horizontal
overflow, and touch-target sizes. All four combinations are clean on those
three measures. `prefers-reduced-motion` and no-WebGL were both verified to
render the static SVG with **zero** canvases and the three.js chunk never
requested — a genuine fallback, not a slowed animation. With no backend
reachable, every data surface shows an inline sentence; no white screens and
no unhandled exceptions.

## Deliberately not done — needs a product or backend decision

1. **General settings is now read-only.** The business-name field was editable
   above a permanently disabled Save button. Wiring it needs an organization
   update endpoint; until then the fields are locked with a line explaining
   how to change them.
2. **API-key generation** stays disabled, now with the reason and the way
   round it printed underneath.

---

# Phase 1 completion — Results (analytics) and Workflows

The two remaining Phase 1 surfaces. Frontend only; `apps/api` untouched. Both
are written against the agreed contract (`/analytics/summary`, `/workflows`,
`/workflows/{id}/enable|disable`, `/workflows/{id}/runs`), which the backend is
building in parallel.

## New routes (2)

| Route | Sidebar label | What it is |
|---|---|---|
| `/analytics` | **Results** | The money question, answered. Leads with recovered revenue, supports it with a 7/30/90-day trend and a per-agent breakdown. |
| `/workflows` | **Workflows** | Standing automations: what each one does in plain language, a working on/off switch, and per-run step history. |

Both are in the sidebar under Workspace, above Knowledge — Results first,
because "was this worth it" is the question the owner opens the product with.
The route is `/analytics` (it matches the endpoint); the word on screen is
"Results" everywhere, including the top bar.

## New files

| File | Role |
|---|---|
| `app/(dashboard)/analytics/page.tsx` | Results page + the per-agent breakdown |
| `app/(dashboard)/workflows/page.tsx` | Workflows list, empty/error states |
| `components/analytics/trend-chart.tsx` | Hand-drawn inline-SVG column chart |
| `components/analytics/stat-tile.tsx` | The quiet supporting-number tile |
| `components/workflows/workflow-card.tsx` | One workflow: copy, switch, run history |
| `components/ui/switch.tsx` | On/off control (new primitive) |
| `lib/analytics.ts` | Recovered-revenue derivation + range/date wording |
| `lib/workflows.ts` | Machine names → sentences an owner can read |

`lib/api-types.ts` and `lib/api-client.ts` were **appended to only** — the
existing adapters (org header, `data.error` parsing, response reshaping) are
untouched. No new dependencies.

## The design decision behind the lead metric

The demo script (deep-dive §6) specifies one tile: *"This week — 34
conversations handled, 11 booked, 6 no-shows recovered, ~$4,100 recovered."*
The number the buyer reacts to is the last one. So the page is built as a
**hero figure of recovered revenue** with everything else demoted to support,
rather than a KPI grid where money is the fourth counter along.

**The contract carries no money and no booking count.** So the figure is
derived and labelled as an estimate, with its arithmetic printed next to it:
`actions_taken × $375` (mid-range general-dentistry visit value, the pricing
model's own assumption), rounded to the nearest hundred because precision it
has not earned would be a lie. `AnalyticsSummary` already declares optional
`bookings_made` and `revenue_recovered`; the moment the backend sends either,
it wins and the estimate caveat disappears with no frontend change.

## Chart decisions (per the `dataviz` skill)

- **Inline SVG, no charting library.** ≤ 90 points, and drawing it by hand is
  the only way the marks, hairlines and type wear our own tokens in both
  themes instead of a library's defaults under a theme override.
- **One series, one hue (the brand teal).** Conversations-per-day is magnitude
  over time with no identity to distinguish — categorical would be wrong. The
  contract's second measure (messages) is at a different scale and gets its
  own stat tile; **no dual axis**, ever.
- Marks: ≤24px columns, 4px rounded data-end square at the baseline, solid
  hairline grid, direct label on the busiest day only — and suppressed when
  more than two days tie or the band gets tight, so labels never collide.
- Every value is reachable without a pointer: y-axis scale, focusable columns
  with spoken labels, hover/focus tooltip, and a **"Show numbers" table view**.
- Measured contrast on the chart (chart surface, both themes): axis/tick text
  4.97 light / 4.63 dark, peak label 16.8 / 14.7, **bars vs surface 8.1 / 6.6**
  (≥3:1 required). Gridlines are deliberately recessive chrome at ~1.35.

## Plain language

`lib/workflows.ts` is the only place a machine name is allowed to exist. It
maps triggers to sentences ("When someone doesn't turn up for their
appointment"), humanises step names, and falls back to a jargon-free sentence
for anything unrecognised — the raw string never reaches the screen. The words
"trigger", "webhook", "tool call", "payload" and "status code" appear nowhere
in user-facing copy. A failed run leads with *what* stopped and *why*, in the
words a front-desk manager would use.

## No-data, loading and error behaviour

Verified with the backend up, with it returning empty payloads, and with it
killed entirely.

| State | What renders |
|---|---|
| First load | Skeletons shaped like the real content, plus an `sr-only` status line |
| Refetch (range change) | Previous render held at 60% opacity — no skeleton flash, no layout jump |
| No backend | An inline sentence plus a **Try again** button. Never a white screen |
| Backend up, no data | An intentional state: the hero reads "Nothing yet" and points at Connect an account; the chart and breakdown each explain what will appear |
| Workflow never run | "Hasn't run yet — it's waiting for the next time this happens" (or "Turn it on and it'll start watching for you" when off) |
| Partial failure | If a refetch fails but stale data exists, the data stays and a quiet line notes it may be out of date |

The enable/disable switch is optimistic and **rolls back with a toast** if the
server disagrees, so the control never lies about what is saved.

## Verification

`npm run build` and `npm run lint` both pass. Verified in-browser at 1440×900
and 375×812, in light and dark, against a stub serving the contract: an
injected auditor computing real composited contrast, touch-target sizes and
horizontal overflow reports **zero failures on all four combinations**, with
one fix made in response (the run-history panel's tinted ground pushed
`text-subtle` to 4.44:1 in dark — those two spans moved up to
`muted-foreground`).

## Assumptions the contract did not cover

1. **Money and bookings** — as above. Derived from `actions_taken`, labelled an
   estimate, with optional fields ready for the real thing.
2. **The per-visit value ($375)** is hard-coded and belongs in organization
   settings once there is a field for it. The UI says so on screen.
3. **`trigger` values.** The map in `lib/workflows.ts` covers the obvious
   clinic set (no-show, missed call, reminders, recalls, schedules); anything
   else degrades to "Automatically, in the background". Worth reconciling with
   the backend's actual enum.
4. **`WorkflowStep.status`** is assumed to use the same vocabulary as a run
   (`success` / `failed` / `running`); anything else renders as done.
5. **`detail` on a failed step is assumed to be owner-readable prose.** If the
   backend puts an exception string there, this is the one place jargon could
   leak — there is a fallback sentence when it is absent, but not when it is
   present and unfriendly.
