# Design principles

The shape of a scaffolded project is not arbitrary. Every structural decision in the framework traces back to a small set of principles, and each principle traces back to a specific antipattern the framework refuses to let projects fall into. This page is the spine: it states *why* the scaffold is built the way it is. The [Why this framework](../overview/why.md) page summarizes this reasoning; here it is in full.

The framework's stated purpose is to let any builder — regardless of experience level — produce solid, observable, testable, deployable applications from their first line of code to their ten-millionth, by offloading quality, testing, observability, security, and deployment concerns so the builder can focus on application logic. The principles below are how that purpose is made real.

## 1. Separation of concerns

Each part of the system has one job, and responsibilities don't bleed across boundaries. The most visible expression of this is the [review system](review-system.md): instead of one generalist reviewer, there's a panel of single-concern agents — security reviews security, observability reviews observability, data integrity reviews data integrity. A finding belongs to exactly one agent's remit. The same discipline runs through the project structure (routes don't call the database directly; that's a layering violation the architecture review flags), through configuration (every value goes through one settings door, never scattered `os.getenv` calls), and through the Compose overlays (focused files that each add one environment's concern, merged rather than duplicated).

Separation of concerns is what makes the whole thing legible: when each piece does one thing, you can reason about it in isolation, and you can change it without disturbing the rest.

## 2. Expose capability, not policy

The scaffold gives you a safe, working default *and* leaves the capability open, rather than locking a decision down. The data stores ship self-hosted so dev mirrors prod out of the box — but a documented escape hatch lets you point at a managed Postgres, Mongo, or Redis by changing a URL and omitting the service. GraphQL introspection is a setting you can toggle per environment, not a hardcoded on/off. The contract gates seed a spec for you if you haven't committed one, then enforce it once you do — they enable the behaviour without forcing it before you're ready.

The principle is to hand the builder a capability with a sensible default already wired, not to impose a policy they have to fight. The default is safe; the door is open.

## 3. Offload architecture from the builder

The scaffold makes the strategic decisions so the builder *configures* rather than *architects*. The hard, easy-to-get-wrong choices — test layout and the four-tier coverage model, the observability stack, the environment topology, the secrets-naming convention, the deployment seam — are already made and wired end-to-end. A builder running `framework new` doesn't decide *whether* to have a staging environment or *how* to propagate a correlation ID; those are settled. Their job collapses to choosing batteries and filling in values, then writing application logic.

This is the heart of the framework's purpose: a less-experienced builder shouldn't have to be an expert in CI, observability, and deployment to ship something solid. The expertise is baked into the scaffold so the builder inherits it instead of having to author it.

## 4. Environment parity by construction

Dev, CI, staging, and prod share one set of *definitions* and differ only in *values* — and that sameness is structural, not a convention someone has to remember. The same Compose definitions span every environment; the same registry image is *promoted* through the chain rather than rebuilt per stage; the same observability stack that runs in production also runs locally, so you see your SLO dashboard before anything reaches CI. The one config surface (`settings.py`, `APP_`-prefixed) reads the same variable names everywhere, and `.env.example` is the single committed contract every environment fills in.

Because the parity is built into how the project is assembled, "works on my machine" drift can't quietly creep in — the behaviour you see locally is the behaviour you get deployed. See [Secrets & environment parity](secrets-and-env-parity.md) and [Services](services.md) for the mechanics.

## 5. Dogfooding

A framework that exempts itself from its own discipline can't be trusted to enforce it. So the framework holds itself to the standard it imposes: its own CLI gets the same Python gates (tests, `ruff`, `mypy`, coverage) it gives generated projects, and the **same review agents** that gate your changes also gate the framework's. The template — the most safety-critical asset, since a broken template silently breaks every new project — isn't validated by inspecting its source; it's validated by *rendering* real projects across a matrix of battery combinations and asserting the generated output lints clean, verifies its integrity lock, and passes its own CI. The template is never released unless rendered projects are green.

Dogfooding is the principle that keeps the others honest. The framework discovers the rough edges in its own scaffold the same way a builder would — by living inside a generated project — and the proof that the discipline works is that the framework survives it.

## How the principles connect

These aren't five independent rules; they reinforce each other. Offloading architecture from the builder is only safe because the offloaded decisions are good ones — and dogfooding is how the framework proves they are. Environment parity is achievable because configuration is separated into one door and exposed as capability (the managed-store escape hatch) rather than frozen as policy. Separation of concerns is what lets each of those decisions be reasoned about and reviewed independently. Together they answer the framework's core question — *how does a builder ship something solid from their very first line of code?* — by making the solid thing the default, and the unsolid thing hard to reach by accident.
