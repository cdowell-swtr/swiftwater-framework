---
name: traefik-configfile-excludes-cli-and-env
description: Traefik `--configfile` makes the file the SOLE static-config source — CLI flags + TRAEFIK_ env vars are silently ignored; for a compose-interpolated (dynamic) value, drop --configfile and use inline command flags
metadata:
  type: reference
---

Traefik treats static configuration as coming from **one source only**. When
`--configfile=…` is passed, the file *wins* and any `--providers.*` / `--entrypoints.*`
**CLI flag OR `TRAEFIK_*` environment variable is silently ignored** (no error, no warning).
Proven empirically (traefik:v3.6, FWK97): constraint as a CLI flag *or* env var alongside
`--configfile` → both `app-demo` and `app-other` discovered; constraint *inside* the file →
only `app-demo`. Traefik does **no `${VAR}` substitution** in its config file either.

Consequence for instance-scoped discovery: a per-instance value (e.g.
`${STACK_INSTANCE}` for the `swiftwater.instance` constraint, [[testing-traefik-tls-route-from-python]])
can't be a mounted-file value (file = render-time slug only) and can't be a CLI/env override
while `--configfile` is present. To get a **compose-interpolated runtime value**, drop
`--configfile` and express the whole static config as inline `command:` flags on the traefik
service — then compose interpolates `${VAR}` into the flag at up-time. The TLS dynamic config
is loaded by the **file provider** (`--providers.file.directory`), a *separate* source from the
static `--configfile`, so dropping the static file leaves TLS untouched.

Contrast: **promtail/Loki DO support `${VAR}`** in the config file via `-config.expand-env=true`
(used by FWK97's promtail project filter) — so promtail keeps its mounted file and stays dynamic.
Traefik has no equivalent; that asymmetry is why FWK97 used inline flags for Traefik but kept
the file for promtail.
