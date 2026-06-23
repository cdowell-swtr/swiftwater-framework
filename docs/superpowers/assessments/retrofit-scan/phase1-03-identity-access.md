# Retrofit Scan — Phase 1, Area 03: Identity & Access

**Agent:** identity-access
**Date:** 2026-06-22
**Scope:** authentication, authorization models (RBAC/ABAC/ReBAC), sessions/tokens,
API keys, multi-product SSO / shared auth, tenant-scoped permissions.

**Framing.** The single most expensive thing you can do to an application is to take
one that was written assuming a *single trust level* — "if you're logged in, you can
do the thing" — and try to teach it, after it has real users and real data, that
*which* user matters, *which* tenant they're in, and *which* specific resources they
may touch. Authorization is not a feature you add; it is a property of every read and
write in the system. When it is missing, retrofitting it means revisiting every query,
every endpoint, and every object reference. That is why this area is dominated by
High-retrofit-cost seams: the cost is proportional to the amount of data-access code
already written, and an opinionated scaffold's whole job is to put the seams in *before*
that code exists.

The empirical stakes are not abstract. **Broken Access Control is #1 in the OWASP Top 10
(A01), and it retains that position in the 2025 edition.** Because the most common
instance — IDOR — is scriptable, "a single vulnerable endpoint can expose an entire
database."
([OWASP IDOR](https://owasp.org/www-community/attacks/insecure_direct_object_reference),
[Authgear on IDOR](https://www.authgear.com/post/idor-insecure-direct-object-reference/))

---

## Seam 1 — The authorization *enforcement seam*: a default-deny, resource-scoped decision point

**The seam.** Where does the app *ask* "may this principal do this action on this
resource?", and is that question (a) asked by default on every protected path,
(b) answered by one place rather than scattered conditionals, and (c) scoped at the
*data-access layer*, not just the route? An opinionated scaffold can bake in a single
`authorize(principal, action, resource)` chokepoint, a default-deny posture (routes are
protected unless explicitly opened), and a convention that every tenant/owner-scoped
query carries its predicate — so the first thing a builder writes already has the seam.

**Why late is brutally expensive.** Cerbos's "Badly Designed Authorization Is Technical
Debt" names the exact failure mode: authorization logic gets "spread across different,
disconnected parts of the codebase," and "whenever the requirements change, a developer
is going to have to go back, find all the places where the logical checks are made,
decipher how it was implemented, and then update it — in every location."
([Cerbos](https://www.cerbos.dev/blog/badly-designed-authorization-is-technical-debt))
The Auth0 SaaS-authz guide describes the same scattering: access decisions become
conditionals like `if user.isAdmin`, `if user.tenantId === resource.tenantId`, or
`if user.email.includes('internal')` strewn through the code, which "is not really
scalable or sustainable."
([Auth0](https://auth0.com/blog/how-to-choose-the-right-authorization-model-for-your-multi-tenant-saas-application/))

The reason retrofit is *worse* than scattered debt elsewhere is the failure direction.
The opposite of default-deny is **default-allow with hand-placed checks**, and the bug
class it produces is silent: a forgotten check on one of 200 endpoints is invisible in
testing and catastrophic in production. The fix — IDOR prevention — is explicitly a
*data-layer* discipline: "Ensure that database queries and data access layers are scoped
to the current user's permissions (e.g.
`SELECT * FROM orders WHERE user_id = :current_user AND id = :order_id`)."
([OWASP IDOR](https://owasp.org/www-community/attacks/insecure_direct_object_reference))
Retrofitting that predicate into every query of an app that was written with bare
`SELECT ... WHERE id = :id` is a line-by-line audit of the entire data layer with no
tooling that can prove you found them all. Default-deny inverts the failure: "in case you
miss some conditions, traffic will be unexpectedly *denied*, instead of unexpectedly
*allowed*."
([DevSecOps Now on default-deny](https://www.devsecopsnow.com/default-deny/))

**retrofit_cost: H.** The cost scales with the number of endpoints and queries already
written; there is no mechanical migration, and the failure mode of getting it wrong is a
breach, not a bug ticket.

**Early scaffolding concretely looks like:** a single FastAPI dependency
(`require(action, resource_loader)`) that all protected routes go through; a default-deny
router convention (a route is unauthenticated/unauthorized only by an explicit opt-out
marker, enforced by a test that fails on any unmarked route); a thin `authorize()` policy
seam decoupled from handlers (so the policy can later move to OPA/Cerbos/Oso without
touching call sites); and a repository/query convention where the *owner or tenant
predicate is structurally required* (e.g. a base query helper that takes the principal
and refuses to build an unscoped query). Crucially this is the *interface*, not a policy
engine — keep it boring so a builder can grow it.

**Proposed disposition: concern.** This is a posture-level decision (default-deny + one
decision point + data-layer scoping) that must be set in the scaffold's bones, not an
opt-in surface. It is the backbone the rest of this area hangs off.

**Overlaps:** strongly adjacent to the in-flight **composability/shapes/shared-auth**
concern (this is the enforcement half of "shared auth") and to **multitenancy** (Seam 3).
Worth treating as the authz spine that those two share.

---

## Seam 2 — The identity / principal model: who can the system represent?

**The seam.** The shape of the `User`/principal record and the authentication abstraction.
Does the app assume one kind of actor (a human with a password), or does it have a
*principal* abstraction that can be a human, a machine (API key / service account), or a
human-backed-by-an-external-IdP, each potentially holding *multiple* credentials and
*multiple* identities that resolve to one account?

**Why late is brutally expensive.** EnterpriseReady (the canonical B2B-SaaS maturity
reference) states the trap directly: "When a product changes from only self-authenticating
users to having multiple options for authentication, it's tempting to emulate the current
user model in your system. This isn't a good idea because the different types of user
objects have different properties and it isn't often a perfect match."
([EnterpriseReady SSO](https://www.enterpriseready.io/features/single-sign-on/))
WorkOS's account-of-the-pattern is blunter: in many SaaS apps "one customer per
environment becomes an invisible design assumption — it works right up until the product
starts landing larger accounts," and tenant/identity routing "gets bolted on later."
([WorkOS](https://workos.com/blog/enterprise-sso-providers-b2b-saas))

The hardest retrofit here is **account linking / user merge**: once the same human has
signed up with a password *and* via Google *and* via their employer's SAML, you discover
they are three rows. Firebase's own docs describe the resulting surgery: "Account linking
will fail if the credentials are already linked to another user account, and in this
situation, you must handle merging the accounts and associated data… choose a primary
user, move sessions and linked accounts from the secondary user to the primary, then
deactivate or delete the secondary," and you must explicitly "retrieve and merge the
metadata" first.
([Firebase account linking](https://firebase.google.com/docs/auth/web/account-linking),
[Auth0 consolidating identities](https://auth0.com/blog/consolidating-multiple-identity-sources-with-auth0/))
Doing that *after* every other table foreign-keys to `user_id` means rewriting
relationships across the whole schema, with live sessions in flight.

**retrofit_cost: H.** A user-id model that assumed one-credential-per-human is referenced
by every other table; widening it later is a schema-wide foreign-key and data-migration
exercise plus a merge story for already-duplicated humans.

**Early scaffolding concretely looks like:** a `principal` abstraction distinct from
`user`, with identities (credential bindings) modeled as a *separate table* from the
account from day one (`accounts` 1—* `identities`), so a second auth method is a row, not
a migration; a stable opaque internal subject id that is *not* the email and *not* the
external IdP id; and the login surface designed for "identifier-first" routing (email →
which auth method) rather than a single password box. None of this requires shipping SSO —
it just refuses to bake in the one-credential-per-human assumption.

**Proposed disposition: concern.** The principal/identity *shape* is foundational and
should be scaffolded; the *providers* that plug into it (SSO, social) are batteries
(Seam 6).

**Overlaps:** the **composability/shapes/shared-auth** concern (this is the identity half;
"shared auth across multiple products" is exactly the multi-identity-per-account problem).

---

## Seam 3 — Tenant-scoped authorization & tenant-context propagation

**The seam.** Is "which tenant" a first-class, *authenticated*, automatically-propagated
property of every request and every query — or is it an afterthought passed around by
hand? This is the authorization-and-isolation facet of multitenancy specifically: even a
single shared DB needs the `tenant_id` predicate on every tenant-scoped read/write, and
needs it derived from the session, never from the client.

**Why late is brutally expensive.** OWASP's Multi-Tenant Security cheat sheet is
prescriptive about timing and placement: "Establish tenant context early in the request
lifecycle (middleware/interceptor)"; "Bind tenant context to the authenticated user
session"; "Never trust client-supplied tenant IDs without validation"; "Use composite keys
(tenant_id + resource_id) for all lookups"; and "Implement authorization checks at the data
access layer, not just API layer." The named primary threat is "Cross-Tenant Data Leakage:
Bugs or misconfigurations exposing one tenant's data to another."
([OWASP Multi-Tenant](https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html))

The retrofit pain is the same shape as the IDOR pain but worse in blast radius. As the RLS
literature puts it, the shared-DB model "is deceptively simple at the database level but
shifts the burden of isolation entirely to the application layer. Every single database
query that accesses tenant data must include a `WHERE tenant_id = ?` clause, and a single
programming error or forgotten `WHERE` clause… can lead to a catastrophic data leak."
Adding a `tenant_id` column to *existing* tables and proving every query now carries it is
the nightmare; whereas doing it from the start "does not add significant upfront effort but
preserves the option for a much smoother future migration."
([AWS RLS](https://aws.amazon.com/blogs/database/multi-tenant-data-isolation-with-postgresql-row-level-security/),
[Propelius tenant isolation patterns](https://propelius.ai/blogs/tenant-data-isolation-patterns-and-anti-patterns/))
And RBAC roles themselves must be tenant-scoped: roles like "admin" or "viewer" must "not
be globally applicable across the system but… assigned on a per-tenant basis," with the
app always verifying "which tenant the user is operating under when making role-based
decisions."
([Auth0](https://auth0.com/blog/how-to-choose-the-right-authorization-model-for-your-multi-tenant-saas-application/))

**retrofit_cost: H.** Adding a discriminator column to a populated multi-table schema and
re-proving every query is a full data-layer audit; a single miss is a cross-tenant breach.
Tenant-scoping roles after they were modeled globally is a second migration on top.

**Early scaffolding concretely looks like:** middleware that resolves tenant context from
the authenticated session into a request-scoped contextvar (never a header); a base
model/mixin carrying `tenant_id`; a repository layer that injects the tenant predicate
automatically (and, where Postgres is in play, RLS policies like
`USING (tenant_id = current_setting('app.current_tenant'))` as defense-in-depth); roles
modeled as `(tenant, principal, role)` from the start; and a test that fails if a
tenant-scoped model is queried without a tenant predicate.

**Proposed disposition: concern** (the authz/isolation contract), feeding the existing
**multitenancy (logical → physical)** board concern. The scaffold should set the
*shared-DB-with-discriminator + auto-scoped queries* baseline so the later logical→physical
escalation is a swap, not a rewrite.

**Overlaps:** **multitenancy (logical→physical)** on the board — this is its
identity/authz enforcement layer. Also overlaps Seam 1's data-layer scoping.

---

## Seam 4 — Authorization model evolution: roles today, relationships tomorrow (RBAC → ReBAC)

**The seam.** Whether authorization data lives behind an abstraction that can grow from
flat roles to *relationships and resource hierarchies* (this folder is in that project,
which belongs to that org; access flows down the tree) without re-plumbing every call
site. Almost every app starts with RBAC and almost every successful one eventually needs
ReBAC-shaped checks.

**Why late is expensive.** Oso's Authorization Academy frames the maturation: apps "begin
with role-based access control — straightforward role assignments like admin or user," but
"as products scale, inherent structural relationships… demand recognition." Crucially these
relationships "weren't new requirements — they were relationships already embedded in the
data model" (issue ownership, nested teams). Their guidance — "For a specific resource type,
use exactly one of roles or relationships" — exists *because* "retrofitting relationships
after building role-heavy systems creates confusion. Mixed approaches lead to multiple
authorization paths for the same resource."
([Oso ReBAC](https://www.osohq.com/academy/relationship-based-access-control-rebac))
This is precisely why Google built **Zanzibar** as one centralized authz service: with
many product teams each rolling their own, "multiple implementations would dramatically
increase the chances of bugs and security holes," so Google centralized to get "a single
source of truth" that answers consistently across services.
([authzed on Zanzibar](https://authzed.com/learn/google-zanzibar),
[Aserto on Zanzibar](https://www.aserto.com/blog/google-zanzibar-drive-rebac-authorization-model))
The trap to avoid is the *other* extreme — ABAC where "relationships between entities are
hardcoded throughout the application," so any change to the attribute structure "requires
code modifications."
([Auth0](https://auth0.com/blog/how-to-choose-the-right-authorization-model-for-your-multi-tenant-saas-application/))

The honest nuance (per Oso): you should "build authorization around your application, not
the other way around" — i.e. don't force a builder onto Zanzibar/SpiceDB on day one. The
seam to protect is the *decoupling of the policy decision from the handlers* (Seam 1's
`authorize()`), so the model can move RBAC → resource-roles → ReBAC behind a stable
interface. That makes this evolution mostly *less* than High **if** Seam 1 exists.

**retrofit_cost: M** (H only if Seam 1 was skipped). With a decoupled `authorize()` seam,
growing the model is changing one implementation; without it, every scattered check must be
found and rewritten, and you risk dual authorization paths for the same resource.

**Early scaffolding concretely looks like:** ship a flat RBAC default *behind* the
`authorize()` interface, with roles stored as data (not enum-in-code) and scoped per
tenant; model resources with an explicit `parent`/owner edge so a hierarchy already exists
to walk; document the RBAC→ReBAC upgrade path and keep the policy adapter swappable
(in-app → Oso/Cerbos → SpiceDB). Do *not* prescribe a relationship engine prematurely.

**Proposed disposition: concern** (decoupling + roles-as-data baseline). A pluggable
policy-engine integration could later be a **battery**, but the early win is the seam, not
the engine.

**Overlaps:** Seam 1 (shares the `authorize()` decision point); the
**composability/shapes/shared-auth** concern.

---

## Seam 5 — Session / token architecture: revocability and the opaque-vs-JWT fork

**The seam.** The token/session model and, specifically, whether the system can *revoke*
access immediately (logout, compromise, role change, offboarding) — i.e. whether there is
a server-side session/refresh authority — versus pure stateless JWTs that remain valid
until expiry.

**Why late is expensive.** The stateless-JWT logout gap is a well-known, hard-to-paper-over
property: "Since JWTs do not inherently involve server-side storage, there's no native way
to invalidate a token before its expiration. After a user logs out, any issued access
token is still cryptographically valid," letting "unauthorized users… continue making
reads/writes to the database even after session revocation."
([Descope](https://www.descope.com/blog/post/jwt-logout-risks-mitigations))
The architectural fork is load-bearing and entrenching: "opaque tokens tightly couple your
APIs to a central authorization server" (revocable but a runtime dependency), while JWTs
"shine in stateless, scalable systems"; the decision "affects your database schema, API
validation patterns, service communication, and scaling infrastructure — making migration
costly and disruptive." The widely-recommended resolution is the hybrid: "short-lived JWTs
for access with opaque [refresh] tokens for session management."
([ZITADEL](https://zitadel.com/blog/jwt-vs-opaque-tokens),
[Nordic APIs](https://nordicapis.com/jwt-vs-opaque-tokens-choosing-the-right-token-for-api-security/))

The retrofit pain: if you ship long-lived stateless JWTs and *then* a security review (or
an incident, or your first enterprise customer's offboarding requirement) demands instant
revocation, you must introduce a refresh/session store, shorten access-token TTLs, add a
revocation check (blocklist or session lookup) to the request path, and update every client
to the refresh flow — a change to the auth hot path of an already-deployed fleet and all
its consumers.

**retrofit_cost: M-to-H.** Not a schema-wide rewrite like Seams 1–3, but it touches the
auth hot path and *every client*, and it is the seam that an enterprise security review
will force; doing it after public API consumers exist means a coordinated client migration.

**Early scaffolding concretely looks like:** ship short-lived access tokens + a server-side
refresh/session record (revocable) by default; put a revocation/session check on the
authenticated path so "logout actually logs out"; centralize token issuance/validation in
one module so the opaque-vs-JWT choice and TTLs are a config seam, not a sprawl; emit a
`sid`/`jti` so revocation has a handle. This gives the hybrid posture from day one.

**Proposed disposition: concern.** Revocability is a posture decision; the scaffold should
default to "revocable sessions" rather than leave a builder with an un-revokable token.

**Overlaps:** Seam 2 (sessions hang off the principal); the **secrets-backing** concern
(token signing keys / session secrets must come from the secrets backend, not env-baked).

---

## Seam 6 — Enterprise SSO + SCIM lifecycle (the B2B identity motion)

**The seam.** First-class support for *federated* enterprise identity: SAML **and** OIDC,
per-tenant IdP config, just-in-time provisioning on first login, **and** SCIM for the full
create/update/**deactivate** lifecycle. This is the canonical "second customer wants the
protocol your first didn't" surface.

**Why late is expensive.** EnterpriseReady: when you add SSO you must redesign the login
flow to route standard vs SAML users (often "email-based routing rather than a unified
entry point"), add admin pages for "managing SAML certificates and redirect URIs," and keep
a "password-based admin login [to] prevent lockout scenarios during misconfiguration."
WorkOS quantifies the toil: without a broker "each new enterprise customer means exchanging
metadata, configuring certificates, and testing assertion quirks by hand… the per-connection
toil that produces the three-to-six-month timelines"; and "supporting both SAML and OIDC
from day one avoids a painful retrofit when your second customer wants the protocol your
first did not."
([EnterpriseReady](https://www.enterpriseready.io/features/single-sign-on/),
[WorkOS](https://workos.com/blog/enterprise-sso-providers-b2b-saas))

The under-appreciated half is **deprovisioning**. JIT-only provisioning "falls completely
flat during offboarding… JIT has absolutely no way to handle deprovisioning" because it
"only fires on a login event." Without SCIM "you will have no way to deprovision these
accounts," leaving orphaned/"zombie" accounts — and the risk is measured: a 2023 DoControl
survey "found that 31% of companies had former employees access SaaS assets after leaving,"
and an older OneLogin survey found "20% of organizations had suffered a breach tied to
failing to deprovision an ex-employee."
([Clerk SCIM vs JIT](https://clerk.com/articles/scim-vs-jit-provisioning-when-to-use-each),
[EnterpriseReady](https://www.enterpriseready.io/features/single-sign-on/))

**retrofit_cost: M.** The login-flow and identity-model retrofit is real, but if Seam 2
(multi-identity-per-account) and Seam 3 (per-tenant scoping) are already in place, SSO/SCIM
becomes *adding a provider and a provisioning endpoint* rather than re-architecting. The
cost is mostly integration toil, not a data-layer rewrite — which is exactly what a battery
should absorb.

**Early scaffolding concretely looks like:** a **battery** that adds OIDC/SAML provider
plumbing, per-tenant IdP config storage, identifier-first login routing, JIT provisioning
into the existing `accounts`/`identities` model, and a SCIM 2.0 endpoint for lifecycle
(create/update/`active:false`). The scaffold's job is to make sure Seams 2/3 don't *block*
this battery later.

**Proposed disposition: battery** (`--with sso` / enterprise-auth), riding on the Seam 2/3
concerns. The *seam that must be scaffolded early* is the multi-identity principal model
(Seam 2) so this battery is bolt-on, not rip-out.

**Overlaps:** Seam 2 (principal model); **composability/shapes/shared-auth** (multi-product
SSO is the same federated-identity surface). Distinct from anything already covered.

---

## Seam 7 — API keys / machine principals as first-class actors

**The seam.** Whether non-human callers (API keys, service accounts, M2M) are modeled as
*principals* that flow through the same `authorize()` path with their own scopes — or
bolted on as a side-channel that bypasses the authz spine.

**Why late is expensive.** When API keys are added after a human-only auth model, they tend
to become a second, parallel auth path with its own ad-hoc checks — re-introducing exactly
the scattered-authorization debt Seam 1 was meant to prevent, but now in a second code path.
Best practice is to treat the key as a credential for a *principal* (a "Service Account
[that] represents the identity for which an API key is issued") with **least-privilege
scopes** ("if a key only needs read access, do not grant write permissions"), **hashed
at rest** ("supports hashed storage"), and **rotatable** via a dual-credential window
("create a new key… verify… update… delete the old"). M2M is the OAuth2 client-credentials
shape, issuing "short-lived access tokens scoped to specific resources."
([Akeyless](https://www.akeyless.io/blog/power-of-api-keys/),
[AWS Confluent key rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/mes-partner-ConfluentCloudApiKey.html),
[IdentityServer secrets](https://identityserver4test.readthedocs.io/en/latest/topics/secrets.html))
If keys are stored in plaintext or unscoped, retrofitting hashing/rotation/scopes after
customers hold live keys means a credential-migration with customer-facing breakage.

**retrofit_cost: M.** Lower than Seams 1–3 because keys are usually fewer and newer than
user data — but if the principal abstraction (Seam 2) and `authorize()` seam (Seam 1) exist,
API keys are nearly free; if they don't, keys become a second authz sprawl and a credential
migration.

**Early scaffolding concretely looks like:** model an API key as a credential bound to a
principal that flows through the *same* `authorize()` path; store only a hash + prefix
(display the secret once); carry scopes; support overlapping active keys for rotation;
and route the key's tenant/scope through the same tenant-context machinery as a session.
This is mostly a consequence of getting Seams 1 and 2 right.

**Proposed disposition: battery** (`--with api-keys` / programmatic-access), dependent on
the Seam 1/2 concerns. The early scaffold need only ensure the principal model and authz
seam *admit* a machine principal.

**Overlaps:** Seam 1 (same decision point), Seam 2 (machine is a principal),
**secrets-backing** concern (key material handling).

---

## Cross-cutting notes & board reconciliation

- **Audit log of auth/security events.** The retrofit story is real and vivid — "Most
  teams add audit logging reactively: a compliance review flags the gap, or a security
  incident reveals that you have no record of who changed what. By the time you are
  retrofitting it, you are working around an existing schema, an existing permission model,
  and existing client code that was never designed with observability in mind."
  ([hoop.dev](https://hoop.dev/blog/immutable-audit-logs-the-baseline-for-security-compliance-and-operational-integrity))
  This is **already on the board** as the *audit-log/activity-trail battery*; I flag only
  that auth events (login, authz-deny, role change, key issuance, tenant switch) are its
  highest-value seed content and that the battery should hook the `authorize()` decision
  point (Seam 1) so events are captured by construction. **Disposition: park** (defer to
  the existing board item).

- **GDPR right-to-erasure / data-subject deletion** intersects the principal model
  (deleting a `user` that is FK'd everywhere) but, per the task framing, is **owned by the
  data-lineage / compliance / privacy reviewer**, not scaffolded here — flagging as
  reviewer-enforced so it isn't lost, but it is out of this area's scope.

- **Relationship to the in-flight concern.** Seams 1–4 are best understood as the
  *enforcement + identity spine* of the in-flight **composability/shapes/shared-auth**
  concern. The recommendation is that "shared auth" be scaffolded as: a multi-identity
  principal model (Seam 2) + a decoupled default-deny `authorize()` seam (Seam 1) +
  tenant-scoped, data-layer enforcement (Seam 3) + a roles-as-data model that can grow to
  ReBAC (Seam 4) — with SSO/SCIM (Seam 6) and API keys (Seam 7) as batteries that plug into
  that spine, and revocable sessions (Seam 5) as the default posture.

**Highest-leverage early bets, ranked:** Seam 1 (authz enforcement spine) and Seam 2
(principal/identity model) are the two that, if skipped, turn *every* later identity feature
into a data-layer rewrite. Seam 3 is co-equal for any product that will ever be
multi-tenant. These three are the cheap-now / brutal-later core of this area.
