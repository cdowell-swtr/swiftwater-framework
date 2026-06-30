# Battery-aware encrypted backups + restore-drill — design

> Status: design (brainstormed 2026-06-29). Next: writing-plans → FWK row(s).
> Driver: Meridian and Bearing become the **authoritative source of truth** for
> FWK/MDN/BRG (and possibly more) task/planning data **within a week**, running on
> **unstable dev**, with **no prod instance**, and the framework today ships **zero**
> data-recovery capability. The thing protecting the soon-to-be SoT does not exist yet.

## 1. Problem & current state

Confirmed gaps in the current template (`src/framework_cli/template/`):

- **No data backups anywhere.** Postgres (and Mongo/Redis when those batteries are
  on) live in *local Docker named volumes* (`pgdata:/var/lib/postgresql/data` in
  `infra/compose/dev.yml.jinja`, mirrored in prod/staging/test). A stray
  `docker compose down -v`, volume corruption, a bad migration, VM loss, or host loss
  destroys the data with no recovery path. No `pg_dump`/`mongodump`/`pgBackRest`/WAL-G
  anywhere.
- **No battery-aware coverage even if we added a naive backup.** A Postgres-only
  `pg_dump` would *silently* miss MongoDB data and *mangle* Apache AGE graph data and
  TimescaleDB hypertables — manufacturing false confidence, which is worse than no
  backup because the gap is only discovered mid-recovery.

(Container log rotation is *also* absent — every service uses Docker's unbounded
`json-file` driver — but the self-DoS risk is low here: single user. It is split out
as its own small follow-up, not part of this spec.)

## 2. Goals / non-goals

**Goals**
- A **generic, configurable** backup capability shipped in the **base scaffold**:
  Postgres is base — every generated project has a DB out of the gate — so backups are
  **core, not a `--with` battery**. The *destination* is a setting (this box →
  `/mnt/<gdrive>`; a future prod → S3/managed snapshots).
- **Battery-aware by construction**: backups cover *every durable store the active
  batteries introduce*, with per-store-correct dump/restore. It is **structurally
  impossible** to think a store is handled when it isn't.
- **Encrypted from day 1** (dumps leave the box to Google Drive, a third party).
- A load-bearing **restore-drill** that exercises the *full* chain (decrypt → restore →
  verify), so key-custody and per-extension restore mistakes fail **loudly and early**.
- A **registration gate**: a new data-persistence battery cannot ship without its
  backup handling.

**Non-goals (captured as follow-ups, §11)**
- Secrets-backing (FWK85) — the age key custody here is *interim*.
- Encryption-at-rest of the live volumes/disk — a distinct threat from backup-leaving-box.
- Container log rotation — separate small row.
- Continuous PITR / sub-24h RPO — overkill for single-user daily-RPO dev data.
- Operating the backup on the live Meridian/Bearing instances — the framework ships the
  capability; the operator (this box) wires `BACKUP_DEST` + enables the timer.

## 3. Threat model & durability layers

Everything (Meridian, Bearing, framework dogfood) runs as Docker volumes inside **one
WSL2 VM** on one Windows host. Loss scenarios, increasing severity:

| # | Scenario | Survived by |
|---|---|---|
| 1 | `down -v` / volume corruption / bad migration | a dump anywhere (even local) |
| 2 | WSL VM dies / reset / distro reinstall | dump on the **Windows host** (`/mnt/...`) |
| 3 | Windows host dies | dump **off the machine** (Google Drive sync) |

Writing the encrypted dump to a **Google-Drive-synced folder under `/mnt/`** covers all
three in layers with zero new infra: the file lands on the Windows host filesystem
(survives #1+#2) and Drive sync pushes it off-machine (survives #3).

## 4. Architecture — backups (a base scaffold capability)

Generic, configurable, **ships in the base scaffold** (not a battery), lives in every
generated project.

**Flow (per Postgres store):**
`docker compose exec -T postgres pg_dump -Fc` (container's version-matched client,
compressed custom-format) → pipe through `age -r $BACKUP_PUBKEY` → write
`$BACKUP_DEST/<slug>-<store>-<utc-ts>.dump.age` → prune.

**Task targets (`Taskfile.yml.jinja`):**
- `task backup` — enumerate the active data surface (§6) → dump + encrypt + write each
  store → prune.
- `task backup:verify` — **the restore-drill.** Decrypt the latest dump → restore into a
  *throwaway ephemeral instance of the battery-correct image* → assert integrity
  (Postgres: `alembic current` == head + row-count sanity; Mongo: collection counts) →
  tear down. Exercises the whole chain including **decryption**.
- `task restore` — guarded decrypt + restore into the **live** store (explicit
  confirmation prompt; refuses without it).
- `task backup:prune` — GFS-lite retention (`BACKUP_RETENTION_DAILY` default 7 +
  `BACKUP_RETENTION_WEEKLY` default 4), prune older in `$BACKUP_DEST`.

**Config (`.env.example.jinja`):**
- `BACKUP_DEST` — destination path. Default `./backups` (a local dir, works out-of-box);
  on this box → `/mnt/<gdrive-shared-folder>`.
- `BACKUP_PUBKEY` — age recipient public key (public; safe in config).
- `BACKUP_IDENTITY` — path to the age private identity *on the box* (read by
  restore/drill). Default `~/.config/<slug>/backup-identity.txt`.
- `BACKUP_RETENTION_DAILY` / `BACKUP_RETENTION_WEEKLY`.

**Scheduling — operator-wired, framework un-opinionated.** Ship a
`*.service` + `*.timer` systemd unit template (disabled by default) under
`infra/backup/`, plus a runbook recipe (`systemctl --user enable --now <slug>-backup.timer`).
The framework ships the *targets + retention + drill*; it takes no opinion on the
scheduler (systemd here, cron or managed snapshots elsewhere).

**Tooling prereq:** `age` as a documented host tool (single static binary, consistent
with how mkcert/shellcheck/go-task are already documented for this box). Decryption in
the drill needs `BACKUP_IDENTITY` present — see §5.

## 5. Encryption & key custody

Dumps are encrypted with **age** to `BACKUP_PUBKEY` *before* leaving the box. Plaintext
SoT dumps in cloud would quietly undo the confidentiality the multitenant-auth work
bought — non-negotiable.

**Key custody (interim — superseded by FWK85):**
- The recipient **public** key lives in config (safe).
- The **private identity** lives at `BACKUP_IDENTITY` on the box for day-to-day
  decrypt/drill, **and** is custodied off-box by the operator (password manager / a
  separate location) as the disaster-recovery copy.
- This is a documented **hard prerequisite**: *lose this key and the off-box backups are
  unrecoverable.* It is itself a secret under ad-hoc custody — a real weakness, and the
  third driver pulling **FWK85 (secrets-backing)** forward (§11).
- **The restore-drill decrypts end-to-end**, so a missing/wrong/un-custodied key fails
  *loudly on day 1* during `task backup:verify` — not silently, mid-recovery.

**Forward-compatibility:** the only FWK85 seam is *how the key is fetched*. When
secrets-backing lands, the backup script reads the identity from the secrets store
instead of a bare file; the dump/restore/retention/drill logic is untouched. Interim
custody is therefore **not throwaway**.

## 6. Battery-awareness — the declared data surface

**Backups are core, not a battery** — base Postgres is always present, so its
dump/restore/drill ships in the base scaffold (`infra/backup/`) unconditionally.
Battery-awareness is only about the **optional data-persistence batteries** that add
stores/extensions *on top* (mongodb, age, pgvector, timescaledb, redis).

Mirror the existing `BatterySpec.obs` / `test_obs_completeness.py` pattern. Add a
`data` disposition to `BatterySpec` (`src/framework_cli/batteries.py`): every *optional*
battery that introduces durable state declares its **store + dump/restore method +
restore-drill image**, or an explicit **`rebuildable`** with a reason. Default `none`
(stateless); the gate (§7) catches under-declaration regardless of the default, since it
derives statefulness from the *rendered volumes* — and it holds the base Postgres volume
to the core backup, every battery volume to that battery's declared disposition.

Per-store handling (the sharp edges battery-awareness exists to catch):

| Store / battery | Method | Sharp edge handled |
|---|---|---|
| **Postgres (base)** | `pg_dump -Fc` / `pg_restore` | baseline |
| **Apache AGE** (`age`) | pg_dump incl. `ag_catalog` + graph schemas; restore does `CREATE EXTENSION age` / `LOAD` **before** data | naive dump restores broken graphs |
| **TimescaleDB** (`timescaledb`) | `timescaledb_pre_restore()` / `post_restore()` dance | vanilla pg_restore mangles hypertables |
| **pgvector** (`pgvector`) | standard pg_dump; **restore image must have the extension** | vanilla `postgres:17` restore fails |
| **MongoDB** (`mongodb`) | `mongodump` / `mongorestore` (separate path) | Postgres backup touches none of it |
| **Redis** (`redis`) | **`rebuildable`** — broker/cache, declared + reasoned | excluded *loudly*, not silently |
| **Loki / Prometheus** (obs) | **`rebuildable`** — retention-bounded telemetry | not SoT |
| **Grafana** (obs) | **`config-provisioned`** — dashboards live in repo | restore = re-provision |

The restore-drill **must** spin its throwaway instance from the **battery-correct
image** (the extension-loaded `infra/docker/postgres.Dockerfile`, a real mongo image) —
a drill against the wrong image is the same false-confidence trap one level down.

## 7. The completeness gate (two layers)

The mechanism that makes "thinking it's handled when it isn't" impossible, and the
**mandatory registration test** for any new data-persistence battery.

1. **Static registration gate (fast tier)** — `tests/test_backup_completeness.py`
   (mirrors `test_obs_completeness.py`): render the project, scrape every **named
   volume + datastore service** from the rendered compose overlays, and assert each maps
   to a battery's declared `data` disposition (a backup method, or an explicit
   `rebuildable`/`config-provisioned` reason). **A battery that introduces a volume with
   no declared backup handling fails the build.** Statefulness is derived from the
   rendered artifact, so it cannot be forgotten.
2. **Execution gate (full/acceptance tier)** — the restore-drill round-trips each
   store's data in a render that includes it (the all-batteries render exercises every
   store at once), against battery-correct images. Proves the declared method *works*.

## 8. File layout

- `src/framework_cli/batteries.py` — `BatterySpec.data` field + dispositions for the
  *optional* data-persistence batteries (mongodb/age/pgvector/timescaledb/redis). Base
  Postgres backup is core (no battery entry) — it lives in `infra/backup/` and always
  renders.
- `src/framework_cli/template/infra/backup/` — `backup.sh`, `restore.sh`,
  `restore_drill.sh` (or task-internal), the systemd `*.service`/`*.timer` templates,
  and `README.md` runbook (key-custody prereq, `/mnt/<gdrive>` wiring, RPO/RTO, restore
  procedure).
- `src/framework_cli/template/Taskfile.yml.jinja` — the `backup*` / `restore` targets.
- `src/framework_cli/template/.env.example.jinja` — the `BACKUP_*` config keys.
- `tests/test_backup_completeness.py` — the static registration gate.
- Restore-drill exercised in the acceptance tier (full tier; docker-gated).

## 9. Testing

Per the template-payload TDD loop ([[template-payload-tdd-loop]]): render → exercise in
the generated project. The static completeness gate runs in the **fast tier** (cheap,
render + scrape). The restore-drill is a **full-tier** (docker) acceptance test against
the generated project's own ephemeral stores. `.env.example.jinja` /
`Taskfile.yml.jinja` are eval-fixture-anchored template files, so edits also run
`tests/review/test_evals.py` ([[eval-fixtures-coupled-to-template]]).

## 10. RPO / RTO

Declared in the runbook: **RPO ≈ 24h** (nightly timer), **RTO ≈ minutes** (manual
`task restore` from the latest decrypted dump). Suitable for single-user dev SoT;
revisit if a real prod instance appears.

## 11. Follow-ups (captured, not in scope)

- **FWK85 (secrets-backing)** — now has a **third driver**: the backup-encryption key
  custody (alongside Meridian's per-tenant DSNs and multitenant session secrets). Record
  the driver on its row; pull it up as the next design cycle after backups.
- **Encryption-at-rest** (new row, linked FWK85) — protects the *live* data in the
  volume/disk (distinct from backup-leaving-box). Splits into disk/filesystem-level
  (LUKS/BitLocker — arguably infra/OS) vs app/column-level (pgcrypto; overlaps FWK85's
  field-encryption / crypto-shred). Not urgent.
- **Container log rotation** (new small row) — `logging:` driver `max-size`/`max-file`
  across services + confirm obs-store retention bounds. Low urgency (single user).

## 12. Decisions resolved (brainstorm record)

- Execution model: ship task targets + retention + drill + a disabled-by-default systemd
  timer recipe; scheduler operator-wired (option **C**).
- Encryption: **on from day 1**, age, interim key custody forward-linked to FWK85.
- Sequencing: **backups now** on interim custody; FWK85 next (interim custody is
  non-throwaway).
- Scope: **battery-aware across all durable stores**, not Postgres-first — enforced by a
  registration gate so a new data-persistence battery cannot ship without backup
  handling.
- Backup style: nightly logical dumps (`pg_dump -Fc` / `mongodump`), not PITR.
- **Backups are a base scaffold capability, not a `--with` battery** — Postgres ships
  base, so recovery ships base. "Battery-aware" = the core backup adapts to the optional
  data-persistence batteries layered on top.
