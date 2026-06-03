# Plan 15 spike — timescaledb-ha base validation (2026-06-03)

**Decision: GO, with a pivot** — the approved `FROM timescale/timescaledb-ha` base swap is **blocked**, but a cleaner alternative (COPY timescaledb from `-ha` onto `postgres:17`) is **validated**. User approved the pivot.

## Findings

- **`-ha` runtime:** `timescale/timescaledb-ha:pg17.10-ts2.27.1` is **Ubuntu 22.04 (Jammy), glibc 2.35**. It bundles timescaledb (loader `timescaledb.so` + versioned `timescaledb-*.so`/`-tsl-*`/`-invalidations-*`) and **pgvector** (`vector.control`) + pgvectorscale; AGE is not bundled; pg layout is the standard `/usr/{lib,share}/postgresql/17/...`.

- **`FROM -ha` is BLOCKED (glibc).** The AGE `age.so` from `apache/age:release_PG17_1.6.0` requires **GLIBC_2.38**; on the `-ha` base (2.35) it fails to load → `FATAL: could not load library ".../age.so": ... GLIBC_2.38 not found` → postgres won't start. So `timescaledb+age` (and all-batteries) breaks on the `-ha` base. (Forward-incompatible: a 2.38-built `.so` can't run on 2.35.)

- **COPY-from-`-ha`-onto-`postgres:17` WORKS (glibc-safe).** Keep `FROM postgres:17` (trixie, glibc 2.41); replace only the flaky timescaledb **packagecloud apt** block with a multi-stage `COPY --from=timescale/timescaledb-ha:pg17.10-ts2.27.1` of the timescaledb `.so` + extension files. glibc is backward-compatible in this direction (a 2.35-built `.so` runs on 2.41). pgvector stays via PGDG apt (reliable; never the flaky part); AGE COPY unchanged. **Validated** — built the all-three (timescaledb+pgvector+age) image, started it with `postgres -c shared_preload_libraries=timescaledb,age`, and all three `CREATE EXTENSION` succeeded: `timescaledb 2.27.1`, `vector 0.8.2`, `age 1.6.0`.

## The validated Dockerfile change (timescaledb block: apt → COPY)

```dockerfile
# (FROM postgres:17 stays; pgvector PGDG apt + AGE COPY unchanged)
# timescaledb — COPY the prebuilt extension from the official Timescale image (no packagecloud
# apt; the .so are built on the -ha image's older glibc, which loads fine on the newer base).
COPY --from=timescale/timescaledb-ha:pg17.10-ts2.27.1 /usr/lib/postgresql/17/lib/timescaledb.so /usr/lib/postgresql/17/lib/
COPY --from=timescale/timescaledb-ha:pg17.10-ts2.27.1 /usr/lib/postgresql/17/lib/timescaledb-*.so /usr/lib/postgresql/17/lib/
COPY --from=timescale/timescaledb-ha:pg17.10-ts2.27.1 /usr/share/postgresql/17/extension/timescaledb.control /usr/share/postgresql/17/extension/
COPY --from=timescale/timescaledb-ha:pg17.10-ts2.27.1 /usr/share/postgresql/17/extension/timescaledb--*.sql /usr/share/postgresql/17/extension/
```

(`timescaledb-*.so` deliberately excludes `timescaledb_toolkit*` [underscore]; `timescaledb--*.sql` is the install/upgrade scripts, not the toolkit.)

## Why this beats the base swap

Smaller + lower-risk (no base change → testcontainers/compose/entrypoint/AGE/pgvector all untouched), glibc-safe, and it eliminates packagecloud for **both** the framework render-matrix and real builders' CI. The build-once-reuse fallback is now unnecessary.

## Pinned tag

`timescale/timescaledb-ha:pg17.10-ts2.27.1` — pinned (not floating `pg17`), so it can't drift.
