# Phase 1 Retrofit Scan — Internationalization & Content (agent: i18n-content)

Area: i18n/l10n across UI + content + DB; number/date/currency formatting; RTL;
pluralization; CMS; timezone-aware display.

**Thesis.** Localization is the canonical "cheap early, brutal late" retrofit.
Every string an English-only team ships is debt that *compounds*: the seams that
make a product localizable (externalized strings, a message-format that respects
plural/gender/word-order, UTC-everywhere storage with locale-aware *display*,
Unicode-complete encoding, direction-agnostic layout) cost ~a day to scaffold and
**months** to retrofit once content, code, data, and a UI exist. As one
practitioner's framing put it: "Every feature you ship without internationalization
multiplies the cost of fixing it later" — what looks like cleanup in a 200k-line
codebase "becomes months of rebuilds that touch every corner of your product" at
800k+ lines ([Localazy](https://localazy.com/blog/technical-debt-in-i18n-why-building-for-localization-from-day-one-pays-off)).
The widely-cited rule of thumb is that adding i18n post-launch costs **2–3×** more
than building it in, because it requires refactoring core data models, UI
components, and business logic ([SimpleLocalize](https://simplelocalize.io/blog/posts/internationalization-guide-software-localization/)).

This scan targets the highest-retrofit-cost *seams* — the architectural decisions a
scaffold can pin so a builder never paints into the English-only corner — and is
explicit about which are scaffold-shaped vs better caught by a reviewer.

Note on board overlap: **i18n/l10n is already on the candidate board as a
first-class concern.** This document does NOT re-surface it as new; it decomposes
the concern into the specific *seams* a scaffold must bake, rates each on retrofit
cost, and flags which are scaffold vs reviewer-enforced — so the concern can be
implemented with the right granularity rather than as a vague "add i18n" task.

---

## Seam 1 — String externalization + message-format choice (no concatenation, ICU-shaped)

**The seam.** Two coupled decisions, made once, that everything downstream
depends on: (a) every user-visible string lives in a catalog behind a `t()` call
keyed from code, never inline; (b) the message format supports CLDR plural
categories, gender/select, and translator-controlled word order — i.e. an
**ICU MessageFormat**-shaped layer, not Python `%`/f-string concatenation.

**Why late is brutal.** This is the single most-documented expensive retrofit in
the field, with named war stories:

- **Slack** had to wrap **~20,000 strings across ~2,000 files** to make its codebase
  localizable — "a massive undertaking" that required pulling in the *entire* Web
  Engineering team and running multi-day "string jams" where the i18n team sat with
  each team to rewrite their code. They adopted ICU MessageFormat over gettext
  specifically for `select`/`plural` blocks — and then had to disable most of their
  TMS's built-in parsing/validation because no TMS supported ICU
  ([Slack Engineering](https://slack.engineering/localizing-slack/)).
- **Shopify** had to build linters/cops and run them "against every file of their
  application" to find violations, then mechanically extract content into per-module
  catalogs keyed by file-path+content
  ([Shopify Engineering](https://shopify.engineering/internationalization-i18n-best-practices-front-end-developers)).
- The concatenation antipattern is described as "the original localization sin": the
  moment you write `"You have " + count + " messages"` you "have guaranteed that your
  app will produce grammatically wrong output for most of the world's top twenty
  languages — without a single error being thrown"
  ([Crowdin ICU guide](https://crowdin.com/blog/icu-guide)). It breaks on
  pluralization, gender, **and word order** — Shopify's "Added: January 1" becomes
  Dutch "1 januari toegevoegd" (date first) and Korean "1월 1일 추가" (entirely
  different structure), so the *whole sentence* must be the translatable unit
  ([Shopify](https://shopify.engineering/internationalization-i18n-best-practices-front-end-developers)).
- Key-naming chaos is its own debt: one team's login module had `login.button`,
  `BTN_LOGIN`, and `auth.signinButton` → **nine** separate translations of "Log in"
  across 14 languages, with translators billing extra and QA flagging terminology
  mismatches every release
  ([Localazy](https://localazy.com/blog/technical-debt-in-i18n-why-building-for-localization-from-day-one-pays-off)).

The asymmetry: setting up translation keys and an ICU-style format adds "maybe a day
or two" up front; retrofitting a mature codebase "can take weeks" — and the work
"touch[es] every corner of your product"
([SimpleLocalize](https://simplelocalize.io/blog/posts/internationalization-guide-software-localization/),
[Localazy](https://localazy.com/blog/technical-debt-in-i18n-why-building-for-localization-from-day-one-pays-off)).
Late retrofits also force a release *postponement* because the work cuts across
every team at once (Slack's whole-org "string jam").

**retrofit_cost: H.** It is O(number of strings × number of templates) of manual
rewrites, every one a code change with review/QA, and the rewrites change call sites
across the entire UI + API + email + notification surface simultaneously. The
concatenation→message-format conversion in particular cannot be mechanized safely
(word order is language-specific).

**Early scaffolding looks like.** Ship a thin translation layer the builder uses by
reflex: a `t(key, **params)` helper backed by a catalog (e.g. Babel `.po`/`.mo` or a
JSON/ICU catalog) wired into both the FastAPI side and any rendered templates;
seed a `locales/` tree with a default-locale catalog and an extraction command
(`pybabel extract`/equivalent) in the Taskfile; an ICU-style plural/select example
in the scaffolded sample feature so the first string a builder writes is *already*
plural-correct. Provide a CLDR-backed plural helper so `count` is passed in, never
branched on. (The hard lever is the *prompt/example shape*, not the library: the
scaffold's example string is the antipattern-pre-empting artifact.)

**Disposition: battery** (the runtime/catalog/format surface) **+ reviewer-enforced**
(a hardcoded-string / concatenation-in-user-strings reviewer — see Seam 6). The
battery installs the seam; the reviewer keeps it from rotting on every new feature.

**Overlaps.** Board first-class concern **i18n/l10n** (this is its core seam);
also overlaps the **CMS + admin/CRUD UI** battery (content strings) and the
**outbound-comms (email/notifications)** battery (those strings need the same `t()`
layer — a classic place teams forget to externalize).

---

## Seam 2 — UTC-everywhere storage with timezone-aware *display* (timestamptz, not naive)

**The seam.** Store every instant as an unambiguous UTC `timestamptz` and keep all
locale/timezone conversion at the *display* boundary; never persist naive local
datetimes. Decide this before the first row lands.

**Why late is brutal.** This is the cleanest example in the whole scan of a retrofit
that is *information-theoretically impossible to do perfectly* after the fact.
Django's own docs are blunt: if you flip `USE_TZ=False → True`, "you must convert
your data from local time to UTC — **which isn't deterministic if your local time has
DST**," because a DST fall-back hour occurs *twice*, so a stored naive local datetime
can map to two different UTC instants and you cannot tell which
([Django docs](https://docs.djangoproject.com/en/3.2/topics/i18n/timezones/)). The
retrofit then cascades:

- Every place that instantiates a datetime must be refactored to produce *aware*
  objects, or you get `TypeError: can't compare offset-naive and offset-aware
  datetimes` "wherever you compare a datetime that comes from a model or a form with
  a naive datetime you've created in your code"
  ([Django docs](https://docs.djangoproject.com/en/3.2/topics/i18n/timezones/)).
- Serialized fixtures change format (`2011-09-01T13:20:30` → `...+03:00`), making it
  "impossible to write a fixture that works both with and without time zone support"
  — every fixture must be regenerated/edited
  ([Django docs](https://docs.djangoproject.com/en/3.2/topics/i18n/timezones/)).
- The naive-datetime hazard is general, not Django-specific: "Timezone-naive
  datetimes are one of the most dangerous objects in Python" because they silently
  participate in arithmetic/comparison and only blow up (or worse, *silently
  mis-compute*) under DST or cross-zone load
  ([lobste.rs discussion](https://lobste.rs/s/wg6mgh/timezone_naive_datetimes_are_one_most)).

The corrupted-data half is unrecoverable: you can refactor code, but you cannot
reconstruct which UTC instant a year of ambiguous local timestamps meant.

**retrofit_cost: H.** Schema change + a sweep of every datetime call site + fixture
regeneration + a non-deterministic, lossy data backfill that you can never fully
trust around DST boundaries.

**Early scaffolding looks like.** Default the ORM column to `timestamptz`
(SQLAlchemy `DateTime(timezone=True)`) and a `server_default`/app default of
`now()`-in-UTC; ship a `utcnow()`-aware helper (avoiding the deprecated naive
`datetime.utcnow()` — itself "now deprecated"
([Miguel Grinberg](https://blog.miguelgrinberg.com/post/it-s-time-for-a-change-datetime-utcnow-is-now-deprecated)));
provide a display helper that takes a user/request locale+tz and formats at the
edge; a migration-template comment that bans naive datetime columns; and a sample
model whose timestamp fields are already `timestamptz`. This is nearly *free* to
pin and impossible to recover later.

**Disposition: concern** (a posture decision — "instants are UTC, locale lives at the
edge" — baked into the model/migration scaffolding) **+ reviewer-enforced** (flag
naive datetime columns / naive `datetime.now()` in new code).

**Overlaps.** Sits under the broader **i18n/l10n** concern (timezone-aware display);
the *storage* posture also reinforces the framework's existing **DB migrations +
expand-only contract guard** (a naive→aware column change would itself be a painful,
non-expand-only migration — best never needed).

---

## Seam 3 — Unicode-complete encoding end to end (utf8mb4 / proper UTF-8, BMP-safe)

**The seam.** Every storage and transport layer is full-Unicode from row zero:
4-byte-capable UTF-8 (`utf8mb4` on MySQL; UTF-8 everywhere on Postgres),
UTF-8 client connections, and no BMP-only assumptions. Emoji, supplementary-plane
CJK, and rare symbols must round-trip.

**Why late is brutal.** MySQL's `utf8` is the textbook trap — it is a **3-byte**
encoding that silently cannot store 4-byte characters (emoji 😀, some Chinese
characters, supplementary-plane symbols)
([OneUptime](https://oneuptime.com/blog/post/2026-03-31-mysql-how-to-convert-a-mysql-database-from-utf8-to-utf8mb4/view)).
The retrofit to `utf8mb4` after data exists is a known-painful DBA exercise:

- It is a full `ALTER TABLE ... CONVERT TO CHARACTER SET utf8mb4` per table — and
  "high traffic applications may require that no locking should be involved (ie. no
  `ALTER TABLE`)," forcing online-schema-change tooling on a live DB
  ([OneUptime](https://oneuptime.com/blog/post/2026-03-31-mysql-how-to-convert-a-mysql-database-from-utf8-to-utf8mb4/view)).
- **Index keys shrink**: a `utf8mb4` char can be 4 bytes, so the indexable prefix
  drops from 255 to 191 chars; "existing indexes longer than 191 characters must be
  redefined" — a schema change that can ripple into application query assumptions
  ([OneUptime](https://oneuptime.com/blog/post/2026-03-31-mysql-how-to-convert-a-mysql-database-from-utf8-to-utf8mb4/view)).
- The fix is multi-layer: even with the right column charset, "the application must
  communicate using the correct encoding" (connection charset), so it is not a single
  switch ([sqlpey](https://sqlpey.com/mysql/fixing-mysql-emoji-support-utf8mb4/)).
- Atlassian ships a dedicated multi-step migration runbook for exactly this on
  Fisheye/Crucible — evidence that vendors treat it as a real, risky operation, not a
  config tweak ([Atlassian docs](https://confluence.atlassian.com/fishkb/migrate-mysql-database-to-utf8mb4-character-encoding-962356253.html)).

The insidious part is the *silent* failure mode: a user pastes an emoji, MySQL
truncates the row at the 4-byte char (or errors), and the data loss is discovered
months later.

**retrofit_cost: H (MySQL) / L–M (Postgres).** On MySQL it is a live-DB charset
migration with index redefinition and connection-layer changes. The framework
*defaults to Postgres*, where UTF-8 is the norm and this is mostly already handled —
so the realistic residual cost is **L–M**: ensure collation/encoding are
explicitly UTF-8 at create-time and connections are UTF-8, so a builder who swaps in
MySQL (or a non-default collation) doesn't inherit the trap. Rated as a seam because
the *posture* ("never assume BMP-only; pin UTF-8 at create time") is what's cheap to
bake and easy to forget.

**Early scaffolding looks like.** Pin `client_encoding=UTF8` / `utf8mb4` in the
scaffolded DB/compose config and the SQLAlchemy URL; for the Postgres default,
ensure `template`/`createdb` encoding is UTF-8 explicitly; document the MySQL
`utf8mb4`-not-`utf8` gotcha in the DB section so a future MySQL swap is born correct;
include a round-trip test for a 4-byte character (emoji) in the sample model's tests.

**Disposition: concern** (encoding posture pinned at scaffold time) **+ park** for the
MySQL-specific depth (low immediate pull given the Postgres default — but the
one-line "explicit UTF-8 at create-time + emoji round-trip test" is worth doing now).

**Overlaps.** Reinforces the framework's existing **DB migrations / expand-only**
posture (a charset change is the kind of painful non-expand migration to avoid);
loosely overlaps **i18n/l10n**.

---

## Seam 4 — Locale-aware formatting at the edge (CLDR-backed numbers / dates / currency)

**The seam.** Numbers, dates, and currency are formatted through a CLDR-backed
locale formatter at the display boundary — never with hardcoded separators, formats,
or symbol placement. Coupled: **money is stored in minor units / explicit currency**,
not formatted strings or naive floats.

**Why late is brutal.** Format assumptions get *baked into output and sometimes into
data* and are then everywhere. CLDR/Intl encode rules that hardcoded format strings
get wrong by default:

- Separators invert by locale: `12345.678` is `12,345.68` in en-US but `12'345,67`
  (apostrophe group, comma decimal) in de-CH; CLDR substitutes the correct local
  glyphs into a neutral pattern — code that hardcodes `,` and `.` is wrong for most of
  Europe ([CLDR docs](https://cldr.unicode.org/translation/number-currency-formats/number-and-currency-patterns)).
- Currency symbol *placement* is locale-specific (`¤` may lead, trail, or replace the
  decimal separator) and the number of fraction digits is **currency-specific** (JPY
  has 0, most have 2) — so "format as `$%.2f`" is wrong for ¥ and for euro-trailing
  locales ([CLDR docs](https://cldr.unicode.org/translation/number-currency-formats/number-and-currency-patterns),
  [W3C i18n](https://w3c.github.io/i18n-drafts/questions/qa-number-format.en.html)).
- Even "correct" CLDR data has in-country mismatches that get litigated (e.g. the
  en-ZA grouping-separator bug filed against Node), underscoring that this is a *data*
  problem you want delegated to ICU/CLDR, not re-implemented per app
  ([nodejs/node #48120](https://github.com/nodejs/node/issues/48120)).
- Date field *order* and structure differ (Shopify's Dutch/Korean examples) — so date
  display is really a message-format problem, not a `strftime` problem
  ([Shopify](https://shopify.engineering/internationalization-i18n-best-practices-front-end-developers)).

The retrofit cost is the same string-sweep as Seam 1 — every formatted number/date/
money in the UI + emails + exports is a call site to find and rewrite — *plus*, if
money was stored as a formatted string or float, a data migration to minor-units.

**retrofit_cost: M–H.** M for display formatting (a call-site sweep, mechanical-ish
once a formatter exists); H if money got stored as floats/strings and must be
re-modeled (data migration + rounding-correctness audit). The framework already
nudges good money modeling in places, so the realistic residual is M.

**Early scaffolding looks like.** Ship a locale-aware formatting helper backed by
`Babel`/CLDR (`babel.numbers.format_currency`, `format_decimal`, `format_date`) used
in the sample feature; model money as integer minor-units + an ISO-4217 currency code
(or `Decimal` + currency), never float; a formatter that takes the request locale; an
example in docs showing why `f"${amount:.2f}"` is a bug. Pin the boundary: "format
only at the edge, with the user's locale."

**Disposition: battery** (formatting + currency-modeling surface, fits alongside the
i18n catalog battery) **+ reviewer-enforced** (flag hardcoded format strings,
`%.2f`-style money, and float money columns).

**Overlaps.** Board **i18n/l10n** concern; the float-money / minor-units half is
arguably owned by a **data-modeling / correctness reviewer**; **CMS** and
**outbound-comms** batteries both emit formatted values and need this helper.

---

## Seam 5 — Direction-agnostic layout (CSS logical properties, `dir`, mirroring) for any UI surface

**The seam.** Any scaffolded UI uses *logical* CSS properties (`margin-inline-start`,
`padding-inline-end`, `text-align: start`) and a `dir`-driven `<html>` direction,
rather than physical `margin-left`/`text-align:left` — so RTL (Arabic, Hebrew,
Persian, Urdu) is a one-attribute flip, not a stylesheet rewrite.

**Why late is brutal.** Physical-direction CSS is debt that only detonates when the
first RTL locale ships, and by then it's *everywhere*. Evil Martians states it plainly:
"if your stylesheet uses `margin-left`, `padding-right`, `border-right`, and
`text-align: left` throughout, you'll spend **hours manually overriding** every
physical direction" — versus logical properties that "express directional *intent*"
and swap automatically under `dir="rtl"`
([Evil Martians](https://evilmartians.com/chronicles/600-million-people-write-right-to-left-2-fixes-your-app-needs)).
Logical properties "handle roughly 80% of RTL layout issues" and "take the same
effort" as physical ones when used from the start
([SimpleLocalize RTL guide](https://simplelocalize.io/blog/posts/rtl-design-guide-developers/)).
The market is real — **600M+ people write RTL** — and competitively under-served,
which is the upside of getting the seam right
([Evil Martians](https://evilmartians.com/chronicles/600-million-people-write-right-to-left-2-fixes-your-app-needs)).
Coupled to RTL is **text expansion**: German runs **+20–35%** longer (and forms long
compounds like *Datenschutzgrundverordnung*), so fixed-width containers, `overflow:
hidden`, and truncation silently break under translation — "a truncated label is an
accessibility failure"
([SimpleLocalize](https://simplelocalize.io/blog/posts/internationalization-guide-software-localization/),
[Localazy](https://localazy.com/blog/technical-debt-in-i18n-why-building-for-localization-from-day-one-pays-off)).
Slack used **pseudo-localization** (accent every char + add 35% length) to catch
both inflexible UI and unwrapped strings *before* any real translation existed
([Slack](https://slack.engineering/localizing-slack/)).

**retrofit_cost: M.** High *effort* (a full stylesheet sweep + icon-mirroring audit)
but contained to the presentation layer, mechanizable in part (codemods exist), and
— critically — the framework's primary surface is a FastAPI **backend/API** scaffold;
the frontend story is thinner. So while RTL retrofit is genuinely painful *for a
team that has a big UI*, the framework's direct exposure is moderate. Rated M, not H,
on that scoping.

**Early scaffolding looks like.** For any scaffolded UI/admin surface (the **CMS +
admin/CRUD UI** battery is the natural home): default to logical CSS properties and a
`dir` on `<html>` driven by the active locale; never ship fixed-width text
containers in the template; include a pseudo-localization toggle/locale in dev so a
builder sees expansion + unwrapped strings immediately. Document the icon-mirroring
rule (mirror directional icons, never logos/media controls/numbers).

**Disposition: reviewer-enforced** (a CSS-logical-properties / no-fixed-width-text /
no-`dir`-hostile-layout reviewer on scaffolded UI) **+ battery** detail (the CMS/admin
UI battery ships logical-property defaults + a pseudo-loc dev locale). Leaning
reviewer-enforced because the framework is backend-first; where it *does* render UI,
catch the antipattern rather than hand-build a full RTL system.

**Overlaps.** Board **CMS + admin/CRUD UI** battery (the UI it ships should be
direction-agnostic by default); board **i18n/l10n** concern.

---

## Seam 6 — A hardcoded-string / i18n-antipattern reviewer (the rot-guard)

**The seam.** A code reviewer that flags the i18n antipatterns *as new code is
written*, so the externalization seam (Seam 1/4) doesn't silently rot: inline
user-visible string literals not behind `t()`; string concatenation / interpolation
that assembles user-facing sentences from fragments; hardcoded number/date/currency
format strings (`%.2f`, manual `,`/`.` separators); naive `datetime.now()` / naive
datetime columns; physical-direction CSS in scaffolded UI.

**Why late is brutal — and why a reviewer, not a scaffold.** The empirical pattern in
*every* war story is that the seam decays linearly with features unless *enforced*:
Shopify had to build "cops and linters" and run them "against every file"
([Shopify](https://shopify.engineering/internationalization-i18n-best-practices-front-end-developers));
Slack needed org-wide "string jams" because thousands of strings had already escaped
([Slack](https://slack.engineering/localizing-slack/)); the multiplicative-debt
framing ("every feature you ship without i18n multiplies the cost") *is* the argument
for catching it per-PR rather than in a quarterly cleanup
([Localazy](https://localazy.com/blog/technical-debt-in-i18n-why-building-for-localization-from-day-one-pays-off)).
A scaffold installs the seam once; only a reviewer keeps the 500th feature from
re-introducing a concatenated, hardcoded-format, naive-datetime string. This mirrors
how the board already assigns cross-cutting hygiene (GDPR erasure → privacy/
data-lineage reviewers) to reviewers rather than scaffolds.

**retrofit_cost: (meta) H prevented.** The reviewer's value is precisely that it
keeps Seams 1–5 from becoming an H-cost retrofit; without it, an early scaffold's
i18n seam erodes back to the 20k-string-sweep state.

**Early scaffolding / enforcement looks like.** An agentic review agent
(`review/agents/i18n.md`-style) in the reviewer registry that flags: user-facing
string literals outside the catalog; sentence concatenation/interpolation; hardcoded
format strings and float-money; naive datetimes; physical-direction CSS — with a
sane `block_threshold` so it surfaces findings without over-blocking the backend-only
paths where it doesn't apply. Pair with a pseudo-localization dev locale (Seam 5) as
the runtime tell.

**Disposition: reviewer-enforced** (this *is* the reviewer half of the i18n concern).

**Overlaps.** Board **i18n/l10n** concern (its enforcement arm); the framework's
existing reviewer system is the delivery vehicle. Note the framework's own memory
([[check-agent-prompt-fit-before-adding-to-target]]) warns that agent *names* mislead
— this agent must be prompt-scoped to genuine user-facing-string contexts so it
doesn't over-fire on backend-only code (cf. [[flags-is-dual-use-gate-skips-advisory]]
for keeping it advisory where appropriate).

---

## Seam 7 — Request-scoped locale context + URL i18n structure (locale negotiation)

**The seam.** A locale is resolved *once* per request by a middleware (precedence:
explicit URL/path prefix or `?lang=` → cookie/user preference → `Accept-Language`
content negotiation → default) and made ambiently available to `t()` and every
formatter via a request-scoped context (e.g. a `contextvar`), rather than threaded by
hand through call sites. Coupled: the *URL structure* for localized content
(path-prefix `/<locale>/...` vs cookie-only) is decided before content is published
and links are shared.

**Why late is brutal.** Two distinct retrofits, both backend-shaped — the seam the
framework is *most* exposed to:

- **Locale plumbing.** If locale isn't ambient from day one, retrofitting it means
  finding and rewiring every `t()` / number / date / currency call to receive a
  `locale` argument — the *same* full call-site sweep as Seam 1, on top of the
  formatter sweep of Seam 4. The standard fix is a single middleware that parses
  `Accept-Language` per RFC 7231 and stores the negotiated locale in request context;
  the documented precedence is URL prefix → cookie → `Accept-Language`
  ([next-intl middleware](https://next-intl.dev/docs/routing/middleware),
  [Pixenio on Accept-Language](https://medium.com/pixenio/things-to-know-about-language-negotiation-via-accept-language-header-ad7604edcbdd)).
  Getting precedence wrong is itself a documented bug class (the Next.js
  "locale negotiation is incorrect for i18n routing" issue), so it's worth pinning a
  correct, override-ordered resolver once
  ([vercel/next.js #18676](https://github.com/vercel/next.js/issues/18676)).
- **URL i18n structure.** Whether localized content lives under a path prefix
  (`/fr/...`), a query param, or only a cookie is *cheap to choose up front and
  expensive to change after launch*: once URLs are indexed by search engines, shared
  in links, and cited externally, switching the scheme forces wholesale redirects,
  `hreflang` annotations, and risks SEO/link-equity loss — which is exactly why the
  JS frameworks (Astro, next-intl, Eleventy) bake URL-prefix routing as a first-class,
  middleware-resolved concern rather than leaving it to per-page logic
  ([Astro i18n routing](https://docs.astro.build/en/guides/internationalization/),
  [next-intl middleware](https://next-intl.dev/docs/routing/middleware)). The override
  hierarchy is well established: a path `/:lang/` overrides `Accept-Language`, and a
  `?lang=` query overrides both
  ([aah framework i18n](https://docs.aahframework.org/v0.9/i18n.html)).

**retrofit_cost: M.** The locale-plumbing half is the same call-site sweep as Seam 1
(M, because much of the cost is *shared* with Seam 1 once you're already doing that
sweep) — but if Seams 1/4 exist and only locale-threading is missing, it's a focused
context-plumbing change. The URL-structure half is genuinely H *for a content-heavy
site with indexed URLs*, but the framework is API/backend-first, so the realistic
residual is M: pin the resolver + a documented URL-structure decision now, and the
expensive SEO-redirect retrofit is avoided for whoever adds public localized content.

**Early scaffolding looks like.** Ship a FastAPI middleware/dependency that resolves
the request locale by the documented precedence and stores it in a `contextvar` the
`t()` helper and formatters read by default (so a builder never threads `locale=`
manually); a documented, override-ordered resolver; and a documented default URL
i18n posture (path-prefix-ready) so the structure decision is made consciously, not
by accident. The sample feature reads the ambient locale, never an argument.

**Disposition: concern** (a posture/middleware decision baked early — locale is a
request-scoped ambient, resolved once, with a chosen URL structure) — overlaps the
in-flight **composability/shapes/shared-auth** concern, since locale is exactly the
kind of request-scoped ambient (like auth principal / tenant) that belongs in the
shared request-context shape.

**Overlaps.** Board **i18n/l10n** concern (its request-resolution seam); strongly
overlaps the in-flight **composability/shapes/shared-auth** concern (locale is a
request-scoped ambient alongside auth/tenant) and the **multitenancy** concern
(tenant + locale are resolved by the same middleware layer).

---

## Summary table

| # | Seam | retrofit_cost | Disposition | Primary board overlap |
|---|------|---------------|-------------|-----------------------|
| 1 | String externalization + ICU-shaped message format (no concat) | **H** | battery + reviewer-enforced | i18n/l10n concern; CMS; outbound-comms |
| 2 | UTC-everywhere storage + tz-aware display (timestamptz, not naive) | **H** | concern + reviewer-enforced | i18n/l10n; DB expand-only contract |
| 3 | Unicode-complete encoding (utf8mb4 / explicit UTF-8, BMP-safe) | **H** MySQL / **L–M** Postgres-default | concern + park | DB migrations; i18n/l10n |
| 4 | Locale-aware formatting (CLDR numbers/dates/currency) + minor-units money | **M–H** | battery + reviewer-enforced | i18n/l10n; data-modeling reviewer; CMS |
| 5 | Direction-agnostic layout (logical CSS, `dir`, text-expansion) | **M** | reviewer-enforced + battery | CMS + admin/CRUD UI; i18n/l10n |
| 6 | Hardcoded-string / i18n-antipattern reviewer (rot-guard) | **H prevented** | reviewer-enforced | i18n/l10n (enforcement arm) |
| 7 | Request-scoped locale context + URL i18n structure (negotiation) | **M** (URL-structure half H for indexed content) | concern | i18n/l10n; composability/shapes/shared-auth; multitenancy |

**Highest-signal, do-early picks for a backend-first scaffold:** **Seam 2 (UTC
storage)** and **Seam 3 (explicit UTF-8 + emoji round-trip)** are nearly free to pin,
impossible-to-recover if missed, and squarely in the framework's existing
DB/migration wheelhouse — bake them as posture *now*. **Seam 1 + Seam 4** (the
catalog + ICU + CLDR-formatting + minor-units-money battery) is the substantive
i18n/l10n concern build-out, with **Seam 6** as its reviewer arm so it doesn't rot.
**Seam 5 (RTL/logical-CSS)** rides the CMS/admin-UI battery and is best caught by a
reviewer given the backend-first scope. **Seam 7 (locale negotiation)** is the most
backend-shaped seam here — a one-time request-context middleware that pins locale as
an ambient (alongside auth/tenant) and avoids both the call-site re-threading sweep
and the SEO-redirect URL-restructure retrofit; fold it into the shared request-shape
work.
