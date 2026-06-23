# Retrofit Scan — Phase 1 / Area 09: Design System & Interactive Components

**Agent:** design-system-components
**Date:** 2026-06-22
**Area:** Adopting a design system / token layer late; component-library strategy (headless vs styled); theming/dark-mode; accessibility-by-construction; complex interactive widgets (data grids, rich editors, virtualized lists); Storybook / visual-regression.

## What the template already ships (verified against code, not memory)

The `react` battery renders a minimal Vite + React 18 + TypeScript frontend
(`src/framework_cli/template/{% if "react" in batteries %}frontend{% endif %}`):

- **No styling system at all.** `App.tsx` is bare semantic HTML (`<main>`, `<h1>`);
  there is **zero CSS** in the tree (no `.css`/`.scss`, no CSS-variable layer, no
  Tailwind, no token file, no theme).
- **No component library** — neither headless (React Aria / Radix / Base UI) nor
  styled (MUI / Chakra). Components are hand-rolled.
- **No Storybook, no visual-regression.**
- ESLint config = `js.configs.recommended` + `typescript-eslint` only — **no
  `eslint-plugin-jsx-a11y`** (no static accessibility lint).
- **Partial a11y tooling already present:** `@axe-core/playwright` is a devDependency,
  so the e2e tier *can* run axe against rendered pages (runtime a11y check). This is a
  real seam already started — the findings below harden the gap, they do not invent it.

So the frontend is itself opt-in, and where it exists it is a blank canvas. That makes
these decisions **how the frontend is constructed** (concern), with heavier surfaces as
opt-in (battery), and ongoing correctness as reviewer-enforced — exactly the three
dispositions, not one battery toggle.

---

## Finding 1 — Headless-primitive choice is the load-bearing meta-seam (H, concern)

**The seam.** Before tokens, before a11y, before dark mode, one decision gates whether
all of them are cheap or impossible: **what interaction/accessibility primitive layer do
your components sit on?** Two roads:

- **Headless primitives** (React Aria, Radix Primitives, Base UI, Ark UI): the library
  owns keyboard navigation, focus management, ARIA semantics, RTL, and controlled/
  uncontrolled state; **you own the markup and styling**, so a token layer and a custom
  design language drop straight in. React Aria ships the deepest a11y primitives (~43
  components); Radix ~28; both support incremental, per-component adoption (Radix's
  `asChild` lets you swap the rendered element).
- **Heavy styled libraries** (MUI, Chakra): components ship with baked-in visual design
  and their own theming engine. Convenient on day 1, but the design language is theirs;
  re-skinning to a real brand, or ripping the lib out later, is the multi-quarter
  migration (see Finding 2).

**Why late is expensive.** This choice is *upstream* of every other frontend seam. Pick a
styled lib and later need your own design system, and you inherit the 239-component
migration. Pick nothing (the current template state) and every hand-rolled `<div onClick>`
becomes an a11y/keyboard liability that the reviewer can only flag one PR at a time. A
headless default makes keyboard/focus/ARIA correct *by construction* and leaves styling to
your tokens.

**Live scaffold-default consideration (real, current):** Radix was **acquired by WorkOS and
updates have slowed for some components**; **Base UI (maintained by MUI) is now the more
actively maintained primitive layer**, and **React Aria (Adobe)** remains the deepest-a11y
option. shadcn/ui is the dominant *consumption* pattern (copy-paste components on top of a
headless primitive + Tailwind), not itself headless. A scaffold must pick a maintained
default deliberately, not inherit a stalled one.

**Retrofit cost: H.** Cost scales with accumulated components. Swapping the primitive layer
after a product has real screens means re-implementing every interactive component's
behavior; this is precisely the "70+ public exports / multi-quarter" migration class teams
describe.

**Early scaffolding.** When `react` is selected, render components on a **maintained
headless primitive** (recommend React Aria or Base UI as the default; document the
trade-off) instead of bare `<div>`s and ad-hoc handlers. Provide one or two worked
components (e.g. the Items list as a proper listbox/table with keyboard support) as the
pattern. This is a small render-time addition that determines whether tokens + a11y are
cheap forever.

**Disposition:** concern.
**Overlaps:** net-new to the board. Underpins Findings 2 & 3.

---

## Finding 2 — Semantic design-token / CSS-variable layer; dark-mode is the forcing function (H, concern)

**The seam.** Colors, spacing, radii, and typography expressed as **semantic tokens**
(`--text-primary`, `--background`, `--border` — role, not value) resolved through CSS
custom properties, instead of hardcoded hex/utility values scattered across components.

**Why late is expensive — the canonical frontend retrofit story.** Adding a token layer
(or its most common trigger, **dark mode**) after components exist means touching every
component. The recurring engineering-blog account:

- "I Thought Dark Mode Was a 30-Minute Task. It Turned Into a Full Refactor" — the author's
  conclusion is the quotable core: **"dark mode didn't sit on top of my UI. It ran through
  it."** Hardcoded Tailwind color utilities had to be rebuilt around semantic variables;
  literal names like `hover-dark` became meaningless when inverting; Tailwind `prose`,
  syntax-highlighting stylesheets (GitHub light vs dark), and SVG diagrams each needed a
  separate fix; and a flash-of-wrong-theme bug forced moving theme resolution before render.
  ([dev.to](https://dev.to/marshateo/i-thought-dark-mode-was-a-30-minute-task-it-turned-into-a-full-refactor-5bk5))
- The retrofit-into-existing-product literature: you must first inventory **how many
  hardcoded values exist**, where design and code have drifted, and which parts are
  consistent enough to tokenize vs need rebuilding first; replacement is done via
  **codemods** (grammar-aware find/replace of raw values → token references), phased
  (border-radius → spacing → color), with a **governance process** because "design and code
  start aligned and drift apart as sprints ship without updating both sides."
  ([Design Systems Collective](https://www.designsystemscollective.com/retrofitting-a-design-system-into-an-existing-product-a9ebfe3d7d30),
  [codemods](https://medium.com/@stevedodierlazaro/automate-design-token-migrations-with-codemods-a21cf8bbd53b))

The migration-cost evidence: one team's move of an existing app onto a design system was
**~15,000 LOC / 239 React components across 3.5 sprints, 16 tasks**, and even then net LOC
fell only 12.36% because containers/state/hooks were untouched — i.e. the *visual layer
alone* is a quarter-scale project once it's grown.
([dev.to migration report](https://dev.to/victorandcode/lessons-from-migrating-a-web-application-to-a-design-system-2701))

**Retrofit cost: H.** Cost scales directly with component count. Cheap when there are 2
components; brutal at 239. Dark-mode / re-brand is the moment the absence bites.

**Early scaffolding.** Ship a thin **semantic-token layer** with the `react` battery: a
`tokens.css` (or equivalent) defining role-named CSS variables with light + dark value
sets, a `[data-theme]` / `prefers-color-scheme` switch resolved **before first paint**
(no flash), and the worked components referencing tokens only — never raw hex. This is a
~one-file addition at render time that makes theming and re-branding a config change forever.
Note: **dark-mode is NOT a separate seam** — it is the canonical retrofit story *for* this
token finding; scaffolding the token layer delivers dark-mode for free.

**Disposition:** concern.
**Overlaps:** RTL/locale-aware theming touches the board's **i18n/l10n** concern (share
the direction/locale switch). Net-new otherwise.

---

## Finding 3 — Accessibility-by-construction: split scaffold vs reviewer (H, split)

**The seam.** WCAG correctness has two halves with different owners:

1. **Scaffoldable, thin, one-time:** the headless primitive (Finding 1 — free keyboard/
   focus/ARIA), `eslint-plugin-jsx-a11y` (static lint, *currently missing* from the
   template's eslint config), and **axe in CI** (`@axe-core/playwright` is already a
   devDependency — wire an assertion into the e2e/gate so a regression fails the build).
2. **NOT scaffoldable, ongoing, per-PR judgment:** semantic-HTML choices, meaningful
   focus order, color-contrast on real content, alt text, form-error association — these
   need human/agent review each change, exactly like the board's GDPR-right-to-erasure
   example that belongs to a reviewer, not a scaffold.

**Why late is expensive.** Accessibility retrofit costs **10–30% more than building it in**,
and the bill arrives as litigation, not a refactor ticket: ADA web-accessibility suits
settle for **$5,000–$75,000** plus attorney fees, audits, and ongoing monitoring (often
costing more than the settlement itself); remediation runs **2–8 weeks (small) to 3–6 months
(large)**. Marquee judgments: **Target $6M, Harvard $1.575M, Netflix $795K.** The overlay
trap is the proof retrofitting can't be faked: **>40% repeat-lawsuit rate** for sites using
an overlay instead of source fixes, and **25% of 2025 ADA suits targeted sites that already
had an overlay installed.** Automated tools only catch **~30% of WCAG issues**, which is
exactly why the other 70% must be a *review* discipline, not a one-time tool.
([a11y-collective](https://www.a11y-collective.com/blog/cost-of-ada-compliance/),
[accessibility.works](https://www.accessibility.works/blog/web-accessibility-process-cost-ada-compliance/),
[testparty overlay data](https://testparty.ai/blog/the-2026-guide-to-ada-website-lawsuits-what-to-do-when-you-get-sued-and-why-your))

**Retrofit cost: H.** The structural half (semantic markup, focus model) scales with
component count and is what the headless primitive buys you early; bolting ARIA/keyboard
onto a grown bag of `<div onClick>` is a full rework. The 10–30% premium understates it once
legal exposure is included.

**Early scaffolding.** (a) Headless primitive default (Finding 1). (b) Add
`eslint-plugin-jsx-a11y` to the rendered eslint config (closes the current gap). (c) Turn
the existing `@axe-core/playwright` into an enforced e2e/gate assertion. Keep it **thin** —
do not ship a single "a11y battery" toggle that overclaims coverage.

**Disposition:** split — **reviewer-enforced** for ongoing semantic/contrast/focus
correctness (the 70% tools miss; per-PR judgment), plus a **concern**-level thin scaffold
(jsx-a11y + axe-in-CI + headless default). The reviewer half is net-new review surface; flag
it for the review-agent registry (a `frontend-a11y` reviewer or extension of an existing UI
reviewer).
**Overlaps:** the scaffold half rides on Finding 1.

---

## Finding 4 — Structured-content / editor document schema (H, battery)

**The seam.** Any product with rich text, comments, docs, or notes needs a **canonical
document model**. The retrofit trap is storing rendered **HTML strings** (or an
editor-library's private format) instead of a **versioned, editor-agnostic structured
schema** (canonical JSON / a node tree) with import/export and HTML as a *cache*.

**Why late is expensive.** Editors are build-vs-buy quicksand and the data outlives the
editor. The framework options (ProseMirror, Lexical, Slate) cost **4–8 weeks of senior
engineering**, and a production editor on Lexical is cited at **$50K–$200K+** of senior-dev
time; ProseMirror is "meant for library authors, not application developers." Worse than the
build cost: **migration between editors is itself 4–8 weeks**, and it's only survivable if
you planned for it — the recommended discipline is to **"store the editor's canonical JSON,
version your document schema, generate rendered HTML as a cache, and write import/export
tests before switching editors."** If you stored raw HTML or a proprietary blob with no
schema version, every stored document is now a migration liability, and collaborative
editing (OT/CRDT) layered on an unversioned schema multiplies the conflict-testing burden.
([pkgpulse editor comparison](https://www.pkgpulse.com/guides/tiptap-vs-lexical-vs-slate-vs-quill-rich-text-editor-2026))

**Retrofit cost: H.** Cost scales with **accumulated user content**, not code. Changing the
storage model after users have authored thousands of documents is a data migration over
content you cannot regenerate — the worst retrofit class.

**Early scaffolding.** Offered as a **battery**, scaffold the *content seam* even if the
editor is pluggable: a versioned structured-content column/model (canonical JSON +
`schema_version`), a render-to-HTML cache path, and import/export round-trip tests — so the
editor choice (Tiptap/Lexical/etc.) stays swappable and the *data* is portable from day 1.
Prescribe the schema-versioning decision FROM the builder (the repo's
"offload-architecture-don't-delegate" value).

**Retrofit cost note:** the editor *widget* itself is M (swappable if the data seam exists);
the *content storage schema* is H. Scaffold the H part.

**Disposition:** battery.
**Overlaps:** strong overlap with the board's **CMS + admin/CRUD UI** battery — the
structured-content schema + versioning + HTML-cache evidence belongs under that battery's
content model. Surface there rather than as a standalone battery.

---

## Finding 5 — Interactive data-grid strategy: headless engine, not a styled grid (M, battery)

**The seam.** Meridian-class apps live on tables. The decision is **headless table engine**
(TanStack Table — "sells the engine, not the component"; sorting/filtering/grouping/
pagination/selection/pinning as opt-in row models; pair with TanStack Virtual for
virtualization) **vs a batteries-included styled grid** (AG Grid / MUI DataGrid — keyboard
nav + ARIA + virtualization built in, but its design language and licensing, harder to
re-skin to your tokens).

**Why late is expensive (moderately).** TanStack Table is headless: **keyboard navigation is
NOT built in and you are responsible for ARIA attributes** — so a table built without that
discipline becomes an a11y/keyboard retrofit across every grid in the app. Conversely, if you
start on a styled grid and later need your own design language, you fight its theming engine.
A consistent *engine + token styling* decision up front keeps every table on one
interaction/a11y/design model. ([TanStack Table docs](https://tanstack.com/table/latest),
[Simple Table: headless vs batteries-included](https://www.simple-table.com/blog/tanstack-table-vs-simple-table-headless-batteries-included))

**Retrofit cost: M.** Real but bounded: a grid can be replaced screen-by-screen, and a
headless engine keeps the column/sort/filter logic portable. It bites mainly through a11y
(keyboard/ARIA bolt-on) and design-language lock-in, not data migration — so M, not H.

**Early scaffolding.** As a battery (or part of the `react` worked-components set): ship one
exemplar **headless data-grid** wired to the headless primitive (Finding 1) and tokens
(Finding 2), with keyboard nav + ARIA + virtualization demonstrated, as the prescribed
pattern. Reduces the builder's job to columns/config, not interaction architecture.

**Disposition:** battery.
**Overlaps:** rides on Findings 1–2; complements the **CMS + admin/CRUD UI** battery (CRUD
lists are data grids).

---

## Finding 6 — Storybook / visual-regression (M→L, park / light battery — honest downgrade)

**The seam.** Component isolation (Storybook) + visual-regression (Chromatic / Playwright
snapshots) to catch unintended UI/theme/state regressions.

**Why it is NOT high retrofit cost.** Unlike Findings 1–4, **the cost does not scale with
accumulated artifacts.** The evidence is explicit that this is a *late, cheap* add: "**your
stories already exist, adding Chromatic is a one-line CI change**," and Chromatic "requires
no configuration" on top of Storybook. You can introduce VRT at any time and it
retroactively protects whatever components exist. Its value *grows with* the component count
("a design system with 500 components and 2,000 stories needs automated visual testing"),
but its *adoption cost stays flat* — the definition of a non-high-retrofit seam.
([Chromatic for Storybook](https://www.chromatic.com/storybook),
[Storybook visual testing](https://storybook.js.org/tutorials/ui-testing-handbook/react/en/visual-testing/))

**Retrofit cost: M→L.** A one-line CI change late. Not a corner you paint yourself into.

**Early scaffolding (optional, light).** Could ship a Storybook config + a Playwright
visual-snapshot example as a small convenience, but it does not need to be baked early to
avoid pain. Honest call: **park**, or a *light* battery — do not inflate it to co-equal H to
match the others.

**Disposition:** park (with optional light-battery upside).
**Overlaps:** none on the board; complements any frontend-testing posture.

---

## Not surfaced (deliberately): drag-drop reordering

Of the assigned widget list, **drag-and-drop** (sortable lists, kanban) is the one I did
not raise as a finding. It is a localized M/L add — a `dnd-kit`-style library drops into an
existing component without touching data storage or the design language, so it is not a
high-retrofit corner. The one durable-data wrinkle (persisting an explicit `position`/order
column rather than relying on insertion order) is a small data-model decision better caught
by the data-modeling reviewer than scaffolded. Omitted rather than padded.

---

## Summary

| # | Seam | retrofit_cost | Disposition | Scales with |
|---|------|---------------|-------------|-------------|
| 1 | Headless-primitive choice (meta-seam) | H | concern | components |
| 2 | Semantic token / CSS-var layer (dark-mode = forcing function) | H | concern | components |
| 3 | Accessibility-by-construction | H | reviewer-enforced + thin concern scaffold | components + legal exposure |
| 4 | Structured-content / editor document schema | H | battery (overlaps CMS) | **user content** |
| 5 | Interactive data-grid strategy | M | battery | screens (bounded) |
| 6 | Storybook / visual-regression | M→L | park (light battery) | flat — late & cheap |

**Throughline:** Findings 1→2→3 are a dependency chain — the headless-primitive default is
the keystone that makes both the token layer and accessibility cheap-forever; without it
they are 239-component migrations. The framework already started the a11y seam
(`@axe-core/playwright`) but left the keystone (no component primitive), the token layer
(no CSS at all), and the static a11y lint (`eslint-plugin-jsx-a11y` absent) unscaffolded.
Finding 4's content-schema is the only one whose cost scales with **irreplaceable user
data**, making it the highest-stakes battery and a natural extension of the CMS battery.
Finding 6 is honestly a low-retrofit add and should not be inflated.
