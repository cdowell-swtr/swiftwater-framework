<!-- CROSS-REPO-convention: v4 -->
# Promote-Up Record — behind-edge dev mode (local-reverse-proxy → swiftwater-framework)

> Generator-seeded record per the vendored [`cross-repo-convention.md`](../../../cross-repo-convention.md)
> (`CROSS-REPO-convention: v4`). **Generator = `local-reverse-proxy`** (a box-specific, deliberately
> no-git helper); **absorber = `swiftwater-framework`**. This record reports the **generator side only** —
> what was built and the capability gap it implies. The absorber owns the generalization decisions,
> migration sequence, and conformance design; those sections are intentionally left to the absorber.

## Status

**`proposed` → being disposed (2026-06-28).** Seeded by the generator and handed to the absorber. The
absorber has now made the generalization decisions in the **first worktree-parallel experiment carving**
(`docs/superpowers/specs/2026-06-28-worktree-parallel-experiment-carving-design.md`): behind-edge dev
mode is framework stream **A1** (`FWK75`), built against the frozen **`FWK88`** Docker-discovery seam
contract. Reconciliation note: the framework chose the **Docker-discovery** model (instance-labels,
routing over the docker network, no host ports), which the generator's current **static
`stacks.yml`→nginx→host-ports** edge does *not* match — so the **generator reworks its edge to discover
the `FWK88` labels** and deletes its interim static edge + the README "exclude Traefik" instructions
(the generator-side copy-deletion). Per the operator, this generator-side rework runs **in parallel**
with A1/A2/B, fed the same carving spec; `local-reverse-proxy` is not git-backed, so no worktree and no
merge-collision. Flip toward `adopted` once the framework ships A1's labels and the generator's reworked
edge passes a behind-edge behavior conformance test.

## Source / generator

- **Repo:** `local-reverse-proxy` (`$DEV_ROOT/local-reverse-proxy` on the origin box). **Deliberately not
  under version control** — a single-box dev helper, by design. There is no remote to clone; this record is
  written to stand alone.
- **What it is:** one shared nginx HTTPS edge (Docker, host networking) that owns host `:80`/`:443`,
  terminates TLS with an mkcert cert, and routes clean `*.localhost` hostnames to multiple Swiftwater dev
  stacks' published host ports. Built because adopting git worktrees across `bearing`/`meridian`/framework
  multiplies live dev stacks on one box, and each generated stack's own Traefik wants host `:443` — so two
  live stacks collide.

## What the generator built and validated

- The shared edge: nginx host-networking container; TLS via the local mkcert CA; host-based routing driven
  by a generated `name → 127.0.0.1:port` table from a small `stacks.yml` registry; unknown hosts rejected.
- An **interim "behind-edge" run mode**: bring a stack up with its **per-stack Traefik excluded** so `:443`
  stays free for the shared edge, separating stacks' published host ports by a `PORT_OFFSET` (step 1000;
  `bearing=0`, `meridian=1000`). This is a hand-rolled workaround documented in the generator's README, not
  a framework-supported mode.
- **End-to-end proven:** `bearing.localhost` → stack A's app, `meridian.localhost` → stack B's app, unknown
  host → `444`; clean teardown, no port leaks. Routing verified through the real edge against two upstreams.

## The capability gap this implies for the framework (the need — not a prescription)

1. **Run a full dev stack behind a shared external edge.** I have multiple live dev stacks on one box that
   each want host `:443`, so they collide. I need a supported way to run each stack's *full* dev experience
   (app + observability) behind one shared edge that owns `:443` — rather than the hand-rolled "exclude
   Traefik" workaround above. **How to offer that is the absorber's call.**
2. **Trust the proxy's forwarded scheme behind a terminating edge.** Behind any TLS-terminating proxy the
   app currently builds `http://` URLs — `X-Forwarded-Proto` isn't trusted. This is **pre-existing and
   affects the per-stack Traefik too** (not introduced by the shared edge); a shared edge just makes it
   routine. Surfaced here as a gap; the remedy is the absorber's call.

## What stays box-specific (NOT to promote)

The nginx edge itself, the `*.localhost` (and nested `grafana.<slug>.localhost`) naming, the mkcert edge
cert, `stacks.yml`, and the name→port generator all belong to this box and stay in `local-reverse-proxy`.
Only the **generic capability** — a stack that can run behind a shared edge — is in scope for the framework.

## Generator-side notes (no-git generator)

The convention's generator-side **git** machinery does not apply here, because the generator is a no-git
helper by design: there is no `generator@<sha>` to pin, no generator-tip-seeded conformance suite, no
adopt-time `git diff` drift check, no git copy to delete, and no implementer registration. The convention's
"generator deletes its copy" step maps to a concrete **non-git** action instead: **once the framework ships
native behind-edge support, the generator strips the interim "exclude Traefik" instructions from its README**
and points at the supported mode. (Conformance survives in spirit as a behind-edge behavior test owned by
the absorber — just not seeded from a generator git tip.)

## Over to the absorber

The framework owns, and this record does **not** prescribe: how a dev stack runs behind a shared edge
(profile shape, Traefik decoupling, port conventions); whether and how to address forwarded-scheme trust;
the upstream-first migration sequence; and any conformance/behavior tests. `bearing` and `meridian` are
ordinary downstream adopters that pick the capability up by upgrading once it ships.

## References

- Generator design spec (origin box): `$DEV_ROOT/local-reverse-proxy/docs/superpowers/specs/2026-06-27-local-reverse-proxy-design.md`
- Generator README incl. the interim behind-edge run mode (origin box): `$DEV_ROOT/local-reverse-proxy/README.md`
- Convention: `cross-repo-convention.md` (`CROSS-REPO-convention: v4`)
