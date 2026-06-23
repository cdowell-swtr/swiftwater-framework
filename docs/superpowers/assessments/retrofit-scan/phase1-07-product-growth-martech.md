# Phase 1-07 — Product / growth / martech retrofit

**Agent:** product-growth-martech
**Area:** product analytics / event instrumentation · experimentation (flags/A·B/MVT) · attribution & consent-gated marketing pixels · admin UI · feature management.
**Date:** 2026-06-22

## Orientation (what the framework already has, and the seam boundary)

Before researching, I checked the template + reviewers. The framework already ships an
**ops-RUM / attribution surface** in the `react` battery:
`src/framework_cli/template/src/{{package_name}}/.../frontend_rum/metrics.py` +
`POST /internal/rum`, with a **fail-closed UTM allowlist**
(`frontend_rum_allowed_query_params` defaults to the `utm_*` set in `config/settings.py.jinja`),
server-side re-application of that allowlist, distinct-value caps with an `other` overflow bucket,
and a `review-observability-fe` + `review-privacy` pair that already flags PII-in-attribution
(`rum-allowlists-pii` fixture) and unbounded cardinality.

This is the crucial boundary the prompt names: **product analytics is a DIFFERENT surface from
ops observability.** What exists is *operational* RUM (Core Web Vitals, JS-error rate, page views
by bounded campaign label, scraped via `/metrics` → Prometheus). What does **not** exist is a
**product-analytics event surface**: a typed, server-side, consent-gated *behavioral event
stream* (object-action events, identity stitching, a persisted/forwardable event record) from
which experimentation exposure logging and consent-gated marketing pixels also hang. The
framework's own existing posture — *expose a capability the safe way; allowlist, never trust the
browser; capture nothing by default* — is exactly the design pattern these new seams want, which
is strong evidence the framework should own the **collection point**, not the analytics vendor.

The findings below are ordered by retrofit cost (the scaffold's reason to exist).

---

## Seam 1 — The product-analytics **event collection point** (consent-gated, server-side, typed)

### The seam
A single first-party **event-collection seam**: one `track(event_name, props, consent_state)`
entry point on the server, behind which sits (a) a typed event taxonomy validated at write time,
(b) a consent gate, and (c) a swappable forwarder/sink (warehouse, CDP, ad-platform CAPI). This
is the *backbone* from which Seams 2 (experimentation exposure) and 3 (marketing pixels) hang —
they are all the same event stream with different downstream fan-out.

### Why late is expensive (the retrofit story)
Product-analytics debt is **structural entropy, not a one-time mistake**. Tracking is implemented
at the *edges* of a codebase, by many people, over a long stretch of time, under deadline
pressure — so each engineer makes a locally-defensible choice (`checkout_complete` vs
`Checkout Completed` vs `purchase`) at the moment a feature ships. Atticus Li's framing (quoted in
DigitalApplied's taxonomy guide):

> "Each engineer makes a locally rational naming choice at the moment of implementation, but the
> cumulative effect of many locally rational choices, made without coordination, produces a
> globally irrational system."

The retrofit is uniquely brutal for one reason that does not apply to most refactors: **you
cannot backfill behavioral events.** The DigitalApplied guide is blunt — once `distinct_id`
fragmentation happens at login, or property types diverge in already-collected data, "there is no
recovering it from the data, because the data was overwritten." Renaming an event after shipping
"creates two broken time series instead of one." Amplitude treats `Song Played` and `song played`
as **separate events**. So the cost is not "rewrite some code" — it is **permanently corrupted
history**: every cohort, funnel, and retention curve computed before the fix is poisoned, and the
clock to re-accumulate clean data starts at zero the day you fix it. A SaaS that discovers at
Series A that its activation funnel is un-analyzable has lost the data, not just the code.

The fix the whole industry converged on is a **gate, not a plan**: "treat tracking like code and
enforce it in CI before events ship... The plan is not the solution — the gate is." Validate
schema at write time; require review for tracking changes; populate an owner field; restrict the
verb vocabulary; fix event names as constant strings (never dynamically generated). And critically
for privacy + durability: **prefer server-side collection** — ad blockers strip 25–40% of
client-side traffic (DigitalApplied/PostHog), so a browser-only design loses both data and the
ability to gate on consent server-side.

### retrofit_cost: **H**
Highest in my area. The cost is not proportional to code size — it is *unrecoverable historical
data* + identity-stitch corruption + a vendor-coupling rip-out if the SDK was wired directly into
business logic. Cheap to scaffold one typed `track()` seam on day 1; impossible to un-corrupt a
year of events on day 700.

### What early scaffolding concretely looks like
A `product-analytics` battery (mirrors the existing RUM discipline):
- A server-side `track(event: EventName, props: TypedProps, *, consent: ConsentState)` seam — the
  one collection point. Events are a **closed enum / typed registry** (an `events.py` taxonomy
  module), object-action naming enforced, fixed string names, an `owner` field per event.
- **Capture-nothing-by-default + allowlist** for properties, reusing the existing fail-closed
  allowlist pattern (`frontend_rum_allowed_query_params` is the template).
- A **consent gate** in the seam (see Seam 3): marketing/analytics events suppressed unless
  consent-state permits; consent state is a first-class request/session field.
- A **swappable sink interface** (`AnalyticsSink`) defaulting to a structured-log/warehouse sink,
  with the forwarder (CDP / Segment-shape / CAPI) as an adapter — never the vendor SDK inlined
  into route handlers (that inlining IS the rip-out cost).
- **Identity discipline** baked in: a stable pseudonymous `distinct_id` + an `identify()`-on-login
  alias seam, so the login-stitch corruption class is structurally prevented.
- A CI/reviewer check that new events conform to the taxonomy (see disposition).

### Proposed disposition: **battery** (the collection-point capability) **+ reviewer-enforced**
(the per-diff taxonomy/consent conformance check)
The *capability* fits the battery model cleanly. The *governance* ("this new event is mis-named /
un-owned / collects un-consented PII") is exactly a per-diff obligation — better caught by a
reviewer than a generic scaffold, and it leans on the existing `review-privacy` + a thin taxonomy
check. Split disposition, like the board's split-disposition exemplars.

### Overlaps
Board first-class concern **"product analytics (consent-gated)"** — this is its concrete shape,
and the central finding: it should be a *battery* (the seam) + *reviewer-enforced* (the taxonomy
gate), not just a concern. Adjacent to the **audit-log/activity-trail** battery (different intent:
audit = who-did-what for compliance; analytics = behavioral measurement — keep separated, same way
RUM and audit are separated today). Reuses the existing RUM allowlist pattern and `review-privacy`.

---

## Seam 2 — **Experimentation backbone**: assignment + **exposure logging** wired to the event stream

### The seam
The decision is not "which A/B vendor." It is whether the app has (a) a deterministic
**assignment/randomization** point, and (b) an **exposure-logging** point that emits an exposure
event into the *same* event backbone as Seam 1 — because an experiment is only analyzable if "user
X was exposed to variant Y at time T" lands in the analytics/warehouse pipeline alongside the
conversion events.

### Why late is expensive (the retrofit story)
Two distinct retrofit pains, both confirmed by primary sources:

1. **Exposure logging must ride the existing event backbone.** Warehouse-native experimentation
   (Statsig/Optimizely/Amplitude/Eppo docs) is explicit: "Assignment Sources define the exposure
   table structure... Metric sources define the event structure." Eppo's whole pitch is that their
   "in-app randomization SDK leverages your existing eventing infrastructure so that you can have
   instrumentation without betraying user trust." If you have no event backbone (Seam 1), you have
   nowhere for exposures to land, and you cannot compute a single trustworthy experiment result —
   so experimentation is *gated on* analytics being built first. Bolting exposure logging on after
   the fact means re-instrumenting every experiment touchpoint.

2. **Statistical correctness must be in the platform, not per-experiment.** Airbnb's "Experiments
   at Airbnb" is a catalog of failure modes that recur unless the *platform* prevents them: the
   **peeking problem** ("the pattern of hitting 'significance' early and then converging back to a
   neutral result" — their price-filter test showed p<0.05 at 4% after 7 days and converged to
   neutral); **assignment bias** (a real bug — a 75/25 split showed "a massive bias against the
   treatment group," traced to faulty visitor-assignment logic for *not-logged-in users*, exactly
   the identity-stitch problem from Seam 1); **sample-size underestimation**; and the **multiple-
   comparisons** trap. They built dynamic p-value-threshold curves *into the framework*. Airbnb
   built bespoke because their marketplace shape (logged-out browsing, cross-device, delayed/
   inventory-dependent conversions) broke off-the-shelf tools — and ERF grew "from a few dozen in
   2014 to about 500 concurrent experiments." Without the assignment seam designed in, every team
   re-derives (and re-breaks) randomization.

The board itself notes experimentation "enables parallel build streams" — release toggles are how
incomplete work ships dark on trunk, so the *absence* of this seam also blocks the framework's own
parallel-stream ambition.

### retrofit_cost: **H**
Assignment + exposure logging touches every experiment-bearing code path; retrofitting it means
re-instrumenting all of them and reconciling against a missing exposure history (same un-backfillable
problem as Seam 1). The statistical-correctness layer, if absent, ships silently-wrong decisions
(the most expensive kind — see Airbnb's converged-to-neutral example). High, and *dependent on*
Seam 1 — which is why they should ship together.

### What early scaffolding concretely looks like
Folds into / extends the board's `experimentation/rollout` concern:
- A **feature-flag/toggle abstraction** (Seam 4) doubles as the experiment-assignment point: a
  deterministic, salted hash → variant bucket, stable per `distinct_id`.
- An **exposure-logging seam** that emits a typed `$experiment_exposure` event into Seam 1's
  backbone the first time a user hits a variant gate (so exposure lands in the warehouse next to
  conversions).
- A documented assignment contract that handles the logged-out / cross-device case (the Airbnb
  bug class) — pin assignment to a stable pseudonymous id, not a per-request coin flip.
- Scaffold the *correctness guardrails as documented defaults*: "decide minimum-detectable-effect
  and sample size before launch; don't peek." (The framework can't run the stats engine, but it
  can scaffold the exposure plumbing + a reviewer note, and leave the analysis to a warehouse tool.)

### Proposed disposition: **concern** (folds into the existing `experimentation/rollout` board
item) **+ battery** (the exposure-logging adapter, which is a `product-analytics` extension)
The rollout/flag posture is a scaffolded concern; the exposure-event *plumbing* is a battery
surface that `requires` the analytics collection point (Seam 1) — exactly the `agents requires llm`
dependency shape already in `batteries.py`.

### Overlaps
Board first-class concern **"experimentation/rollout (feature flags + A/B + MVT)"** — this is its
backbone half (assignment + exposure logging), and it surfaces the hard dependency:
**experimentation `requires` product-analytics**. Tightly coupled to Seam 1 and Seam 4.

---

## Seam 3 — **Consent-gated marketing pixels / attribution** (CAPI-first, consent as a first-class state)

### The seam
A consent-state field that is **threaded through the event collection point**, plus a
**server-side conversions (CAPI) forwarder** as the default attribution path — so marketing/ad-
platform events are (a) suppressed-until-consent by construction and (b) sent server-to-server,
not from an inlined browser pixel that fires on page load.

### Why late is expensive (the retrofit story)
This is the seam with the hardest *legal/financial* retrofit evidence in my area.

- **Pixel-fires-before-consent is the #1 GDPR violation, and it is a money number.** By default,
  the Meta Pixel fires on page load; "if the consent banner loads and the pixel fires while the
  banner is still on screen or before it appears, that's a violation — the pixel should be
  completely blocked until after a user actively clicks 'Accept.'" France's **CNIL fined Google
  €100M and Amazon €35M (€135M total, Dec 2020)** specifically because advertising cookies were
  placed *before* consent was collected. A Swedish online pharmacy was fined **8M SEK (≈€700k)**
  for a Meta Pixel transmitting health-related data without proper consent. France's CNIL has
  found that *most standard Meta Pixel setups violate GDPR*. The retrofit story is therefore: a
  product that inlined pixels client-side has to (1) rip every pixel out of page-load, (2) re-route
  it through a CMP/consent gate, and (3) it is *already non-compliant in the meantime* — the
  retrofit clock runs against active legal exposure, not just tech debt.

- **The privacy-safe path (server-side CAPI) is also the data-durable path.** iOS 14.5 / ITP /
  ad-blockers strip "30–40% of conversion data" client-side; Meta CAPI recovers "20–30% more
  conversions" because it's server-to-server. So the *same* architectural move — collect the event
  server-side, gate it on consent, forward via CAPI — solves both the legal problem and the data-
  loss problem. A browser-pixel-first design has to be torn out twice (once for consent, once for
  durability); a server-side-first design never incurs either.

This is the prompt's exact "privacy tension," and the resolution is the framework's existing
house style: **expose-capability-safe-by-default → consent-gated, allowlisted, server-side,
capture-nothing-by-default.** The framework already does this for UTM attribution; Seam 3 extends
the same discipline to marketing-pixel fan-out.

### retrofit_cost: **H**
Driven up by *legal exposure during the retrofit window* (active fines, not just debt) and the
"tear out twice" problem (consent gate + CAPI). The consent-state *plumbing* (threading a consent
field through every event) is the part that's cheap-early / brutal-late: retrofitting a consent
predicate into thousands of scattered tracking calls is the same edges-of-the-codebase problem as
Seam 1.

### What early scaffolding concretely looks like
Extends Seam 1's collection point:
- **Consent state as a first-class field** on the session/request, threaded into `track()`; the
  seam suppresses marketing-category events unless consent permits (and analytics-category per the
  app's lawful basis). Categories modeled (necessary / analytics / marketing) so the gate is
  granular, like a CMP.
- A **CAPI/server-side forwarder adapter** as the default attribution path (Meta/Google-shape),
  behind the swappable `AnalyticsSink` — *not* an inlined browser pixel.
- If a client-side pixel is offered at all, scaffold it **blocked-until-consent** (the CMP pattern:
  "until the visitor accepts marketing cookies, the script does not execute and no cookie is set").
- Reuse the fail-closed allowlist for any URL/attribution params forwarded (already in the template).
- A `review-privacy` check that an event reaching a marketing sink passed the consent gate.

### Proposed disposition: **battery** (the consent-gated CAPI forwarder) **+ reviewer-enforced**
(consent-gate compliance per diff)
The forwarder is an opt-in capability (a `product-analytics` sink adapter). "Did this marketing
event actually pass the consent gate / is this pixel blocked-until-consent" is an
implementation-specific obligation against real diffs → `review-privacy` (which already owns
consent/PII and already flags `rum-allowlists-pii`). The board's split-disposition pattern again.

### Overlaps
Board concern **"product analytics (consent-gated)"** (the consent half) + a new **martech/CAPI**
forwarder battery. Strongly reinforced by the existing `review-privacy` reviewer and the existing
UTM-allowlist posture (this seam is the *outbound* analogue of the inbound RUM allowlist). The
broader GDPR-erasure/data-residency obligations remain **reviewer-enforced** per the board's
`data-lineage`+`compliance`+`privacy` ruling — Seam 3 is only the consent-at-collection slice.

---

## Seam 4 — **Feature-management abstraction** (typed flags, owned, behind a toggle router)

### The seam
A **flag-evaluation abstraction** — a single `flags.is_enabled(name, context)` / feature-decisions
seam — rather than `if config.SOME_FLAG:` scattered through the codebase. Flags are typed by
*purpose* (release / experiment / ops / permission) with owners and expiry from creation. This is
the substrate Seam 2's assignment rides on.

### Why late is expensive (the retrofit story)
Feature-flag debt is one of the best-documented retrofit horror stories in engineering, and the
canonical guidance (Martin Fowler / Pete Hodgson, *Feature Toggles*) is precisely an *architectural*
prescription:

- **Toggles are inventory with a carrying cost.** Hodgson: *"Savvy teams view their Feature
  Toggles as inventory which comes with a carrying cost and seek to keep that inventory as low as
  possible."* Stale flags clutter the codebase, and (LaunchDarkly/Unleash/Statsig docs) "can
  introduce risks, such as security vulnerabilities, by unintentionally exposing sensitive
  features or data" and cause "unexpected application behavior" from conflicting flags.

- **The cost is real money at the limit.** The Uber/Piranha writeup cites the canonical disaster:
  "obsolete code made live due to mismanaging a feature flag led to a major financial firm losing
  hundreds of millions of dollars" (Knight Capital). And Uber's own scale: **Piranha processed
  1,381 flags, auto-deleted ~71,000 lines of code, Dec 2017–May 2019** — they had to *build an
  AST-rewriting tool* because manual cleanup of scattered conditionals was intractable. That tool
  only exists because the flags weren't behind a clean abstraction in the first place.

- **The retrofit cost is set by the abstraction, not the flag system.** Hodgson's core
  architectural rule is *decouple decision points from decision logic*: a **toggle router / feature-
  decisions object** centralizes evaluation; **inversion of decision** injects the decision at
  construction time so business logic never queries the flag system; long-lived toggles use a
  Strategy pattern, not scattered `if/else`. The differing lifecycles make this non-optional:
  release toggles live weeks (static routing), experiment toggles live hours-to-weeks (dynamic per
  request), ops toggles are short-lived kill-switches (dynamic reconfig), permissioning toggles
  live *years* (per-request, highly dynamic). If they all enter as bare `if` checks, you cannot
  reason about lifecycle or clean them up — which is exactly how Uber ended up needing Piranha.

The cheap-early move is a one-screen abstraction + a typed flag registry. The brutal-late reality
is auditing thousands of scattered conditionals across a live codebase (and possibly building your
own Piranha).

### retrofit_cost: **M–H**
The *abstraction* is cheap to add at any time in isolation — but every flag added before it exists
is a scattered conditional that must be hunted down and rewritten, and the count compounds fast
(Uber: 1,381). The retrofit cost is in the *accumulated call sites*, not the seam itself; that's
what makes early scaffolding high-leverage. Rated M–H (lower than Seams 1–3 because there's no
un-backfillable-data or legal-fine multiplier — it's "merely" expensive refactoring at scale).

### What early scaffolding concretely looks like
Part of the board's `experimentation/rollout` concern (the flags half):
- A `flags.is_enabled(name, context)` seam + a **typed flag registry** (`name`, `kind` ∈
  {release, experiment, ops, permission}, `owner`, `created`, `expires`), so the lifecycle is
  declared at birth.
- Toggle-router decoupling baked into the scaffold so call sites never query the flag store
  directly (inversion-of-decision).
- A backend interface swappable between an in-DB/config store and an external provider
  (Unleash/LaunchDarkly-shape) — same swappable-backend ethos as the reviewer engine.
- A **staleness check** (a reviewer or a `task`/test that flags expired or owner-less flags) — the
  closed-world ratchet the framework already favors (cf. `test_every_surface_is_classified`).

### Proposed disposition: **concern** (folds into `experimentation/rollout`) **+ reviewer-enforced**
(stale/un-owned/scattered-flag detection)
The abstraction is a scaffolded posture decision (concern); "this flag is stale / un-owned / this
is a scattered conditional that should go through the router" is an excellent per-diff reviewer
check (a thin new reviewer or an extension of `architecture`/`application-logic`).

### Overlaps
Board first-class concern **"experimentation/rollout (feature flags + A/B + MVT)"** — this is the
feature-management/flags half; Seam 2 is the A/B/exposure half; they share the same assignment
substrate. Also touches `architecture`/`application-logic` reviewers.

---

## Seam 5 — **Admin / internal-CRUD UI** (the "free Django admin" the FastAPI stack doesn't get)

### The seam
A generated **admin/CRUD surface** over the app's models (list/search/edit/inspect), behind auth,
for internal ops / customer-support / data-correction — the thing Django ships free and FastAPI
conspicuously does not.

### Why late is expensive (the retrofit story)
This is real but **lower-retrofit** than Seams 1–4, and I'm honest about that. The evidence:
Django's admin "saved countless hours"; for internal tools <50 users "Django's admin is 3× faster
to build, and its admin panel reduces development time by 60%." FastAPI's "tight coupling" of
Django's admin to its ORM "makes it less suitable" — so FastAPI teams either hand-roll CRUD
("would cost weeks") or adopt `sqladmin` / `starlette-admin` / `fastapi-amis-admin`.

But the *retrofit* cost is genuinely moderate, not high: an admin UI is **additive and reads/writes
existing models** — adding it at month 12 is mostly wiring, not a data migration or a history
corruption. There's no un-backfillable-data or legal-fine multiplier. The pain is *opportunity
cost during the gap* (teams hand-build one-off support scripts and bespoke internal pages), not an
expensive untangling later. The one place it climbs: if the app accreted bespoke
support/admin pages everywhere first, consolidating onto a generated admin is a real cleanup — but
that's M, not H.

### retrofit_cost: **L–M**
Additive over existing models; no data/history/legal multiplier. The cost is the wasted bespoke
tooling built during the gap, plus a modest consolidation if those accreted. Honestly low-to-medium.

### What early scaffolding concretely looks like
A `admin` battery: a `sqladmin`/`starlette-admin`-backed CRUD UI auto-derived from the SQLAlchemy
models, behind the app's auth, with the **audit-trail** battery wired in (every admin write is an
audited action — admin UIs are a top insider-risk surface, so audit-by-default is the safe posture)
and a `review-privacy`/`review-security` note that admin routes are authz-gated and PII-aware.

### Proposed disposition: **battery**
Clean fit for the opt-in battery model; an obvious `requires`-the-`audit-log` relationship.

### Overlaps
Board batteries **"CMS + admin/CRUD UI"** (this is the admin/CRUD half — the CMS half is
content-modeling, distinct) and **"audit-log/activity-trail"** (admin writes should be audited).
Already named on the board; this finding *confirms* it and pins its honest retrofit cost as L–M
(below the analytics/experimentation/consent cluster), and flags the audit-by-default coupling.

---

## Summary table

| # | Seam | retrofit_cost | disposition | overlaps |
|---|------|---------------|-------------|----------|
| 1 | Product-analytics event collection point (typed, server-side, consent-gated) | **H** | battery + reviewer-enforced | board "product analytics (consent-gated)" — concretizes it |
| 2 | Experimentation backbone (assignment + exposure logging on the event stream) | **H** | concern (`experimentation/rollout`) + battery | board "experimentation/rollout"; `requires` Seam 1 |
| 3 | Consent-gated marketing pixels / CAPI attribution | **H** | battery + reviewer-enforced | board "product analytics (consent-gated)"; `review-privacy` |
| 4 | Feature-management abstraction (typed flags, toggle router) | **M–H** | concern (`experimentation/rollout`) + reviewer-enforced | board "experimentation/rollout"; substrate for Seam 2 |
| 5 | Admin / internal-CRUD UI | **L–M** | battery | board "CMS + admin/CRUD UI" + "audit-log" |

**The through-line:** Seams 1–3 are *one backbone* — a server-side, typed, consent-gated event
collection point — viewed from three downstream fan-outs (analytics, experiment exposure, marketing
pixels). The framework's existing RUM/UTM posture (fail-closed allowlist, capture-nothing-by-default,
never-trust-the-browser, `review-privacy`) is the exact design language these want, which is the
strongest signal that the framework should own the **collection seam** and leave the analytics
*engine* to a warehouse/vendor. Seam 4 is the flag substrate Seam 2 rides; Seam 5 is the honest
lower-retrofit admin battery already on the board.

## Sources
- Uber Piranha (flag-debt scale + Knight-Capital reference): https://medium.com/@sandeepchakravartty/piranha-automated-flag-debt-refactoring-at-uber-240c8f1309a1
- Martin Fowler / Pete Hodgson, *Feature Toggles* (taxonomy, carrying-cost, toggle-router): https://martinfowler.com/articles/feature-toggles.html
- Unleash — managing feature-flag technical debt (flag staleness/lifecycle): https://docs.getunleash.io/concepts/technical-debt
- LaunchDarkly — reducing feature-flag tech debt: https://launchdarkly.com/docs/guides/flags/technical-debt
- DigitalApplied — product-analytics event taxonomy that won't rot (Atticus Li quote; "no recovering it from the data"; CI-gate): https://www.digitalapplied.com/blog/product-analytics-event-taxonomy-tracking-plan-2026
- Airbnb Engineering — *Experiments at Airbnb* (peeking, assignment bias, dynamic p-value, ERF scale): https://medium.com/airbnb-engineering/experiments-at-airbnb-e2db3abf39e7
- Eppo — Series A (in-house experimentation; "leverages your existing eventing infrastructure"): https://www.geteppo.com/blog/series-a
- Statsig — warehouse-native experimentation (exposure/assignment sources; warehouse coupling): https://www.statsig.com/blog/warehouse-native-experimentation
- Ingest Labs — server-side tracking guide (iOS/ITP/ad-blocker data loss): https://ingestlabs.com/blogs/the-complete-guide-to-server-side-tracking-2026/
- Cookie Information — 8M SEK Meta Pixel fine (Sweden): https://cookieinformation.com/resources/blog/8-million-fine-for-meta-pixel-use-in-the-eu/
- FlowConsent — Meta Pixel & GDPR (CNIL €135M; pixel-before-consent is a violation): https://www.flowconsent.com/en/blog/meta-pixel-cookies-gdpr-compliance
- Leapcell — beyond Django admin / FastAPI admin options: https://leapcell.io/blog/beyond-django-admin-exploring-alternative-python-admin-interfaces
