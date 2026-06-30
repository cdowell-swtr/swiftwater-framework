# Backups — coverage contract

> `FWK133`. Backups are a **base scaffold capability** (Postgres is base → recovery is base,
> not a `--with` battery). This page is the coverage contract; the machine-checked forms are
> `tests/test_backup_completeness.py` (static) and `tests/acceptance/test_backup_drill.py` (docker).

`task backup` dumps every active durable store (age-encrypted) to `$BACKUP_DEST`; `task
backup:verify` drills the restore; `task restore` recovers the live stack. Scheduling is
operator-wired via a disabled-by-default systemd timer (`infra/backup/`). The generated project's
runbook is `infra/backup/README.md`.

## The two-layer gate (why a store can't be silently unbacked)

- **Static registration gate (fast tier) — `tests/test_backup_completeness.py`.** Renders each
  battery and scrapes the rendered compose **named volumes** against its `BatterySpec.data`
  disposition. A new battery that adds a volume with no declared disposition (`store` dumped /
  `rebuildable` skipped / `postgres-extension` no-volume) **fails the build**. This is the
  mandatory registration test for any data-persistence battery — statefulness is derived from the
  rendered artifact, so it cannot be forgotten.
- **Execution gate (full tier, docker) — `tests/acceptance/test_backup_drill.py`.** Actually
  round-trips baseline + all-data-batteries through encrypt → decrypt → restore into the
  **battery-correct** (built) postgres image, verifying `alembic_version` survives. The drill
  builds + uses the extension image (never vanilla `postgres:17`), so it can't false-green
  pgvector or always-fail timescale/age.

## Per-store handling

| Store / battery | `data` | Method |
|---|---|---|
| Postgres (base) | core | `pg_dump -Fc` / `pg_restore --single-transaction` (atomic live restore) |
| `mongodb` | `store` | `mongodump --archive --gzip` / `mongorestore --drop` |
| `age` / `timescaledb` / `pgvector` | `postgres-extension` | restored into the built extension image; AGE `CREATE EXTENSION … LOAD` first, TimescaleDB `pre_restore()`/`post_restore()` hooks |
| `redis` / `workers` | `rebuildable` | broker/cache — not backed up |
| `react` | `rebuildable` | `frontend_node_modules` build cache — not backed up |
| obs (loki / prometheus / tempo) | rebuildable (base) | retention-bounded telemetry, not SoT |

## Encryption & custody

Dumps are **age-encrypted from day 1** (`BACKUP_PUBKEY`). Key custody is **interim** — the private
identity lives on the box (`BACKUP_IDENTITY`) plus an off-box DR copy — and is the third driver
pulling **FWK85** (secrets-backing) forward; the only seam FWK85 changes is *how the key is
fetched*. The systemd unit sources `.env` through a shell (not `EnvironmentFile=`) so `~`/`$VAR`
expand identically on the timer and the `task` paths.

## Known limitations / follow-ups

- The restore-drill verifies **Postgres** (incl. its extensions); Mongo is backed up + restorable
  via `task restore` but is not drill-verified. Extending the drill to Mongo is a follow-up.
- **FWK134** encryption-at-rest (live volume/disk) and **FWK135** container log rotation are
  separate rows.
