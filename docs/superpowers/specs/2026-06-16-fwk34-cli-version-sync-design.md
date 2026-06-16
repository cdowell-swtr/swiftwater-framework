# FWK34 — CLI/project version-sync (+ `framework --version`) Design Spec

**Status:** Approved (brainstormed 2026-06-16).
**Ships:** a framework release (CLI behaviour; **not** template payload). Target **v0.2.12**.

## Problem

`framework restore` and `framework integrity` render the "canonical" copy of a managed
file from the **bundled** Copier template — i.e. the template packaged inside the
*currently installed* `framework` CLI (`copier_runner.render_project` → `template_path()` =
`files("framework_cli")/"template"`). They never consult the project's recorded
`_commit` version.

`framework upgrade`, by contrast, renders from the **git tag** (`upskill._apply_update`
→ Copier `run_update(vcs_ref=target)`, with `_src_path = gh:cdowell-swtr/swiftwater-framework`).

So the two paths use **different template sources**, and they only agree when the
installed CLI version equals the project's `_commit`. When they diverge, `restore`/
`integrity` render a canonical for the wrong framework version:

- **CLI behind project** (installed `<` `_commit`): the project was upgraded past the
  CLI (upgrade pulls from the tag). `restore` renders a *stale* canonical that can never
  match the lock written by the upgrade.
- **CLI ahead of project** (installed `>` `_commit`): a dev bumped their global CLI but
  left an older project pinned. `restore` silently renders a *newer* canonical and
  rewrites the lock entry — partially advancing one locked file past the project's pin —
  and `integrity` reports bogus drift.

**Worked example (the trigger).** Meridian's CLI is `v0.2.8`; the project was
`framework upgrade`d to `v0.2.11`. The git-in-Dockerfile fix shipped in `v0.2.10`, so the
upgrade (tag-sourced) wrote the *git* Dockerfile and lock hash `856fec`, but `restore`
(bundled `v0.2.8`, pre-fix) renders the *no-git* Dockerfile `bc8d37` — they can never
reconcile. The original report read as "Dockerfile lacks git" / "restore is
battery-unaware"; both are wrong. `_answers` carries `batteries` through and the render is
battery-aware (verified: rendering with `claudesubscriptioncli` produces the git
Dockerfile and the restore-equivalent render reproduces it byte-for-byte). The actual
defect is the **bundled-vs-tag source skew**.

## The invariant

> `restore`/`integrity` are correct only when **`version_tag(installed_CLI) == project `_commit`**.

Generated-project **CI already upholds this** — `ci.yml` installs the CLI pinned to the
project: `ref="$(awk '/^_commit:/ {print $2}' .copier-answers.yml)"; uv tool install
"git+…@${ref}"`. The gap is the **manual developer** paths (`upgrade`, `restore`,
`integrity` run from a global CLI). This item brings those paths in line with the
invariant CI already enforces.

## Design

Four changes; framework source only (`src/framework_cli/`), no template payload.

### 1. `framework --version`

Add an eager `--version` option on the Typer app callback (`cli.py` `@app.callback()`).
Prints `installed_framework_version()` (already defined in `integrity/manifest.py`, wraps
`importlib.metadata.version("framework-cli")`) and exits 0. Pure papercut; `framework
check` already surfaces the version but `--version` is the obvious thing to reach for.

### 2. Shared skew helper (new module `framework_cli/version_sync.py`)

A single pure function comparing the installed CLI version to the project's `_commit`:

```
class VersionSkew(enum.Enum):
    IN_SYNC = "in_sync"
    CLI_BEHIND = "cli_behind"   # installed < _commit  (project upgraded past the CLI)
    CLI_AHEAD = "cli_ahead"     # installed > _commit  (CLI newer than the project pin)

def project_version_skew(project: Path) -> tuple[VersionSkew, str, str]:
    """Return (skew, installed_tag, commit_tag) for `project`."""
```

- `installed_tag = version_tag(installed_framework_version())` (`source.version_tag`,
  `manifest.installed_framework_version`).
- `commit_tag = read_commit(project)` (`source.read_commit`). If `_commit` is absent,
  treat as a hard error (cannot determine the project version) with the existing
  "_commit missing" message family.
- Comparison is on the parsed `vX.Y.Z` tuple (reuse the `vX.Y.Z` parse already in
  `source._TAG_RE`/`latest_release`).

Pure and side-effect-free → unit-tested as a truth table. This is the single source of
truth consumed by changes 3 and 4.

### 3. B — skew guard in `restore` and `integrity`

Both call `project_version_skew(project)` **before** rendering the bundled canonical and
raise a typed `VersionSkewError` (surfaced as a non-zero `typer` exit) on a non-`IN_SYNC`
result. No auto-bump here — an ahead-skew would require silently *downgrading* the global
CLI, which we never do; the developer chooses bump-CLI vs upgrade-project.

- `CLI_BEHIND`: *"This project is pinned `<commit_tag>` but your framework CLI is
  `<installed_tag>`. `restore`/`integrity` would render the wrong version. Upgrade the CLI:
  `uv tool install git+https://github.com/cdowell-swtr/swiftwater-framework@<commit_tag>`,
  then retry."*
- `CLI_AHEAD`: *"This project is pinned `<commit_tag>` but your framework CLI is
  `<installed_tag>`. Either upgrade the project (`framework upgrade`), or pin a matching CLI
  (`uv tool install …@<commit_tag>`)."*

Call sites: `integrity/restore.py::restore_file` (before the `render_project` at the
canonical-render step) and the `integrity` command in `cli.py` (before it renders/compares).
`downskill` also renders via `render_project`, but it operates within a single CLI
invocation that owns the version and is not a skew vector — left unchanged.

### 4. C — assisted CLI self-bump on `upgrade`

In the `upgrade` command, once the `target` tag is resolved (default: `latest_release()`):

```
if target > installed:
    if not _is_uv_tool_install():
        -> refuse with the exact `uv tool install …@<target>` command (B's message)
    if interactive_tty or --bump-cli:
        run `uv tool install git+…@<target>`            # injectable seam
        os.execvp("framework", original_argv)            # re-exec; injectable seam
    else:                                                # non-interactive, no flag
        -> refuse with the exact command
# target <= installed: proceed unchanged
```

After the bump the new CLI is `target`, so the re-exec'd `framework upgrade` sees
`IN_SYNC` and runs the real upgrade (renders from the tag, writes the lock) — no re-exec
loop. The interactive prompt (default **Y**) is: *"Your framework CLI is `<installed>`;
the target is `<target>`. Bump the CLI and continue the upgrade? [Y/n]"*.

`--bump-cli` forces the bump non-interactively (still requires a `uv tool` install; else
the refuse path). The `target <= installed` case is unchanged (a `--to <older>` downgrade
is rare and out of scope — the resulting ahead-skew is caught later by change 3).

### Install-method detection & re-exec (the riskiest details)

- **Only a `uv tool` install is safe to self-replace.** `_is_uv_tool_install()` resolves
  the running console-script path and checks it lives under `uv tool dir` (query
  `uv tool dir` once; compare against `Path(sys.argv[0]).resolve()` /
  `shutil.which("framework")`). Editable/dev/pipx/venv installs → not detected → refuse
  with guidance, never mutate. (Implementation detail to finalise in the plan: prefer the
  `uv tool dir` containment check; fall back to refusing if detection is inconclusive —
  fail safe, never bump on uncertainty.)
- **Re-exec** with `os.execvp` so the *target* version's code performs the upgrade. The
  three side-effecting operations — the `uv tool install` subprocess, the `os.execvp`, and
  the TTY check — sit behind **injectable seams** (module-level functions) so the decision
  logic is unit-tested without mutating the environment or actually re-exec'ing.

## Error handling

- `VersionSkewError` (new, in `version_sync.py`) → caught at the `cli.py` boundary and
  rendered as a clear message + non-zero exit, consistent with the existing
  `UpgradeError`/`ValueError` handling.
- A failed `uv tool install` during C (bad tag, network) aborts **before** the re-exec and
  reports the failure — the environment is left as-is (uv tool install is atomic per tool).
- Missing `_commit` → the existing "cannot determine template version" error family.

## Testing

Framework-source pytest (runs in the framework venv; standard `gate`-tier):

- `--version`: invoke the CLI with `--version`; assert it prints
  `installed_framework_version()` and exits 0.
- Skew helper: truth table over (installed, `_commit`) → `IN_SYNC`/`CLI_BEHIND`/
  `CLI_AHEAD`, including equal, behind, ahead, and missing-`_commit`. Monkeypatch
  `installed_framework_version` + a fixture `.copier-answers.yml`.
- B: `restore_file` and the `integrity` command raise `VersionSkewError` with the correct
  directional message when skewed, and proceed (reach the render) when `IN_SYNC`.
  Monkeypatch the installed version and the project `_commit`.
- C: the *decision* function (inputs: installed, target, is-uv-tool, is-tty, `--bump-cli`
  → outcome `bump` | `refuse` | `proceed`) as a truth table, with the installer/exec/TTY
  seams mocked. No real `uv tool install`, no real `os.execvp`, no environment mutation.

## Scope / non-goals

- **Rejected alternative — A (render the canonical at `_commit`).** Make `restore`/
  `integrity` fetch+render the template at the project's recorded `_commit` (like
  `upgrade`), instead of the bundled template. Considered and **rejected**: it trades
  "bundled, **offline**, must-match-version" for "version-faithful but **needs network** to
  clone the tag," and `integrity` plausibly runs in pre-commit — a per-check clone is a real
  regression. A mostly *moves* the coupling (to network + tag availability) rather than
  removing it, for the narrow benefit of "restore works with a deliberately-lagging CLI."
  C + B close the practical gap while keeping `restore`/`integrity` offline.
- No change to the generated project's CI (already pins `…@${_commit}` — correct).
- No change to `upgrade`'s tag-fetch render (correct).
- `framework upgrade --to <older-than-CLI>` downgrade self-handling — out (rare); the
  resulting ahead-skew is caught by change 3.

## Release

Framework CLI behaviour → ships in **v0.2.12** per the release-cut procedure (fold the bump
into this PR). Consumers receive the guard once they are on `>= v0.2.12`. Meridian's
*current* skew is resolved manually (bump the CLI to v0.2.11, then reconcile) — this item
prevents the *recurrence* class.

## Self-review (during spec authoring)

- **Placeholders:** none. The one deferred specific — the exact `_is_uv_tool_install()`
  mechanism — is flagged as a plan-time decision with a fail-safe default (refuse on
  uncertainty), not an unfilled requirement.
- **Consistency:** the skew directions, messages, and the `installed`/`target`/`_commit`
  vocabulary are used identically across changes 2–4. C handles `target > installed`; B
  handles both directions at restore/integrity time — non-overlapping.
- **Scope:** single implementation plan; A is the only considered-and-rejected branch and is
  recorded with rationale.
