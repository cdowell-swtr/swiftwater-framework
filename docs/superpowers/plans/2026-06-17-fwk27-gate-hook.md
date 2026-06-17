# FWK27 — Generated-project `.claude` review-gate hook — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:executing-plans`. Read the shared
> policy first: `docs/superpowers/plans/2026-06-17-coverage-batch-execution-policy.md` (branch
> `fwk-coverage-batch`, commit cadence + skip-marker gate, real-bug rule, **no release**,
> laptop/`TMPDIR=/var/tmp`, non-vacuity). This is item **#6** of the batch and lands **after FWK24,
> FWK23, FWK26, FWK25, FWK19**. Steps use `- [ ]`.

**Goal:** Close M15 — exercise `reviewers-gate-check.sh` (the generated project's `.claude`
PreToolUse review-gate hook) by piping a real PreToolUse JSON payload and asserting the two
critical code paths: (1) a `git commit` Bash payload + a FAIL verdict → the hook exits 2; (2) a
`git commit` payload + a PASS verdict → the hook exits 0; (3) a non-commit Bash payload → the hook
exits 0 (grep guard short-circuit). Mirrors the existing `_run_hook` driver for `lint_changed.py`
at `tests/acceptance/test_rendered_project.py:824`.

**Architecture:** This is a **shell hook** (not docker). The test renders the project, writes a
fake `framework` binary to a temp `bin/` directory on `PATH`, pre-populates
`.framework/audit/marker.json`, and invokes `bash .claude/hooks/reviewers-gate-check.sh` via
`subprocess.run(..., input=<payload_json>, ...)`. No compose, no API key, no live gate run.

**Why the stub is required:** In a freshly rendered project with no `.framework/review.toml`, `uv
run framework gate` is skip-neutral and always exits 0 (writes a PASS marker, exits 0 — see
`cli.py:779`). The hook's FAIL path (`exit 2`) is only reached when `uv run framework gate` exits
non-zero. To exercise that path without a real backend, we place a fake `framework` shell script
(which exits 1 for the FAIL case, exits 0 for the PASS case) at the front of `PATH` for the
subprocess call. The FAIL-case stub also pre-populates `.framework/audit/marker.json` (so the
hook's `python3 -c "...json.load(open('.framework/audit/marker.json'))..."` summary-read succeeds
rather than printing an empty fallback).

**Hook anatomy (verbatim from the `.jinja` source, lines 1–16):**

```
#!/usr/bin/env bash
# PreToolUse hook: on `git commit`, run the in-process review gate ...
set -euo pipefail
grep -Eq '(^|[^[:alnum:]_])git[[:space:]]+([^[:space:]].*[[:space:]]+)?commit([^[:alnum:]_]|$)' || exit 0
root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
cd "$root"
if ! uv run framework gate >/dev/null 2>&1; then
  summary=$(python3 -c "import json;print(json.load(open('.framework/audit/marker.json')).get('summary',''))" 2>/dev/null || true)
  echo "Pre-commit gate FAILED ..." >&2
  exit 2
fi
exit 0
```

Key mechanics:
- **Line 8:** `grep -Eq '...'` reads the PreToolUse JSON from **stdin** (no file arg); the regex
  matches `git commit` with word-boundary guards on both sides. If no match → `exit 0`
  (skip-neutral). The pattern passes for `"git commit -m '...'"` and rejects `"ls"`,
  `"git log"`, `"git status"`.
- **Line 9:** `git rev-parse --show-toplevel` requires the rendered project to have a `git init`
  (a freshly rendered project does — `git init` + initial commit happen at the end of `copier
  copy`). The `|| exit 0` guard makes non-git directories skip cleanly.
- **Lines 11–15:** `uv run framework gate` is the FAIL/PASS branch. If it exits non-zero → read
  `.framework/audit/marker.json` + exit 2. If it exits 0 → line 16 exits 0.
- **Marker path:** `.framework/audit/marker.json` relative to the git root (i.e., the rendered
  project root). Shape: `{"verdict": "FAIL"|"PASS", "summary": "...", ...}`.

**PreToolUse payload shape** (the hook reads stdin as raw JSON; `grep -Eq` scans the serialized
string for the git-commit pattern):

```json
{"tool_name": "Bash", "tool_input": {"command": "git commit -m 'test commit'"}}
```

A non-commit payload example:

```json
{"tool_name": "Bash", "tool_input": {"command": "ls -la"}}
```

The hook's `grep` sees the raw JSON string — `"command": "git commit -m ..."` — which matches the
regex because `git` and `commit` appear with whitespace between them and the required
word-boundary tokens.

**Tech Stack:** Python, pytest, `subprocess`, `bash` (always available), `uv` (already a
skip-condition for the sibling lint-hook tests), no docker.

---

## File Structure

- **Modify** `tests/acceptance/test_rendered_project.py` — add one shared helper
  `_run_gate_hook` + three gate-hook tests (`test_rendered_gate_hook_blocks_on_fail_marker`,
  `test_rendered_gate_hook_passes_on_pass_marker`, `test_rendered_gate_hook_skips_non_commit`).
  Place immediately after the existing `test_lint_hook_ignores_non_python` block (~line 875).
- **Modify** `tests/runtime_coverage/registry.py` — flip `hook:.claude:reviewers-gate-check.sh`
  from `_KG` to `_EX`, naming `test_rendered_gate_hook_blocks_on_fail_marker`.
- **Modify** `PLAN.md` + `ACTION_LOG.md` (per the shared policy).

**No template change is expected.** The hook source is correct; this plan exercises it. If a test
goes red, follow the shared real-bug policy.

---

## Task 1: `_run_gate_hook` helper + three tests

**Files:** Modify `tests/acceptance/test_rendered_project.py` (after line 874,
`test_lint_hook_ignores_non_python`).

- [ ] **Step 1: Write `_run_gate_hook` and the three tests.**

```python
def _run_gate_hook(
    dest: Path,
    payload: dict,
    *,
    stub_exit_code: int,
    marker_verdict: str | None = None,
) -> "subprocess.CompletedProcess[str]":
    """Invoke .claude/hooks/reviewers-gate-check.sh with a synthetic PreToolUse payload.

    Places a fake `framework` binary at the front of PATH that exits `stub_exit_code` so the
    hook never touches a real backend. If `marker_verdict` is given, pre-writes
    .framework/audit/marker.json with that verdict so the hook's summary-readback succeeds.
    The rendered project already has a `git init` + initial commit (copier does this), so
    `git rev-parse --show-toplevel` resolves cleanly.
    """
    import os
    import stat

    # Build a fake `framework` binary that exits stub_exit_code.
    fake_bin = dest / ".fwk27-bin"
    fake_bin.mkdir(exist_ok=True)
    fake_framework = fake_bin / "framework"
    fake_framework.write_text(f"#!/usr/bin/env bash\nexit {stub_exit_code}\n")
    fake_framework.chmod(fake_framework.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    # Pre-write the marker.json if the FAIL branch will try to read it.
    if marker_verdict is not None:
        marker_dir = dest / ".framework" / "audit"
        marker_dir.mkdir(parents=True, exist_ok=True)
        (marker_dir / "marker.json").write_text(
            json.dumps({"verdict": marker_verdict, "summary": "FWK27 test finding"})
        )

    # Prepend the fake bin dir to PATH so `uv run framework gate` calls our stub, not the
    # real CLI.  uv itself is still found at its normal location.
    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}"}

    return subprocess.run(
        ["bash", ".claude/hooks/reviewers-gate-check.sh"],
        cwd=dest,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.mark.skipif(
    shutil.which("uv") is None or shutil.which("bash") is None,
    reason="uv + bash required: renders the project and invokes the gate hook shell script",
)
def test_rendered_gate_hook_blocks_on_fail_marker(tmp_path: Path):
    # M15/FWK27: the hook's FAIL path (exit 2) is never exercised — only render-text-checked.
    # Pipe a `git commit` PreToolUse payload; the fake `framework` binary exits 1 (gate FAIL);
    # the hook reads .framework/audit/marker.json and exits 2.
    dest = tmp_path / "demo"
    render_project(dest, DATA)
    # uv sync not required: we don't call the rendered project's venv — only bash + the fake stub.

    payload = {"tool_name": "Bash", "tool_input": {"command": "git commit -m 'test commit'"}}
    result = _run_gate_hook(dest, payload, stub_exit_code=1, marker_verdict="FAIL")
    assert result.returncode == 2, (
        "gate hook did not exit 2 on a FAIL verdict — FAIL->exit-2 translation broken\n"
        + result.stdout + result.stderr
    )
    assert "FAILED" in result.stderr, (
        "expected 'FAILED' in hook stderr on a FAIL verdict\n" + result.stderr
    )


@pytest.mark.skipif(
    shutil.which("uv") is None or shutil.which("bash") is None,
    reason="uv + bash required: renders the project and invokes the gate hook shell script",
)
def test_rendered_gate_hook_passes_on_pass_marker(tmp_path: Path):
    # M15/FWK27: the hook's PASS path (exit 0 after framework gate succeeds) must also be
    # asserted — the fake `framework` binary exits 0 (gate PASS); the hook exits 0.
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    payload = {"tool_name": "Bash", "tool_input": {"command": "git commit -m 'test commit'"}}
    result = _run_gate_hook(dest, payload, stub_exit_code=0, marker_verdict="PASS")
    assert result.returncode == 0, (
        "gate hook did not exit 0 on a PASS verdict\n" + result.stdout + result.stderr
    )


@pytest.mark.skipif(
    shutil.which("uv") is None or shutil.which("bash") is None,
    reason="uv + bash required: renders the project and invokes the gate hook shell script",
)
def test_rendered_gate_hook_skips_non_commit(tmp_path: Path):
    # M15/FWK27: the grep guard (line 8 of the hook) must exit 0 for non-commit Bash payloads
    # without reaching the `framework gate` call at all. Use stub_exit_code=1 so if the grep
    # guard breaks and the hook proceeds, it would exit 2 — making the skip a detectable failure.
    dest = tmp_path / "demo"
    render_project(dest, DATA)

    payload = {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}
    result = _run_gate_hook(dest, payload, stub_exit_code=1)
    assert result.returncode == 0, (
        "gate hook did not skip (exit 0) on a non-commit Bash payload — grep guard broken\n"
        + result.stdout + result.stderr
    )
```

- [ ] **Step 2: Lint** — `uv run ruff check tests/acceptance/test_rendered_project.py && uv run ruff format --check tests/acceptance/test_rendered_project.py`.

- [ ] **Step 3: Run the three tests — expect GREEN.**

  ```bash
  uv run pytest tests/acceptance/test_rendered_project.py::test_rendered_gate_hook_blocks_on_fail_marker tests/acceptance/test_rendered_project.py::test_rendered_gate_hook_passes_on_pass_marker tests/acceptance/test_rendered_project.py::test_rendered_gate_hook_skips_non_commit -q
  ```

  First run renders each time (~10s each); all three should be fast (no docker, no uv sync). If
  `test_rendered_gate_hook_blocks_on_fail_marker` exits 0 instead of 2, that is the primary
  anticipated real bug — see the Self-Review.

- [ ] **Step 4: Bite-proof — assert the FAIL case exits 0 → RED.**

  In `test_rendered_gate_hook_blocks_on_fail_marker`, temporarily change:
  ```python
  assert result.returncode == 2,
  ```
  to:
  ```python
  assert result.returncode == 0,
  ```
  Run the single test → expect **RED** (`AssertionError` because the hook genuinely exits 2 on a
  FAIL marker). Revert. This proves the test is not vacuously passing. Optionally, bite-prove the
  skip test by temporarily changing its final assertion to `assert result.returncode == 2` → RED
  (the `ls` payload genuinely skips and exits 0, so the `== 2` assertion fails). Revert.

  Commit (PLAN/ACTION_LOG staged + `git add` then `git commit` as SEPARATE calls per
  [[commit-gate-hook-timing]]).

---

## Task 2: Flip the FWK27 registry entry

**Files:** Modify `tests/runtime_coverage/registry.py`.

- [ ] **Step 1: Flip `hook:.claude:reviewers-gate-check.sh` from `_KG` to `_EX`.**

  Current entry (registry.py:71–78):

  ```python
  SurfaceClass(
      "hook:.claude:reviewers-gate-check.sh",
      ".claude/hooks/reviewers-gate-check.sh",
      _KG,
      # M15: only render-text-checked; no test pipes a PreToolUse git-commit payload and
      # asserts FAIL->exit 2 (unlike lint_changed.py which IS driven).
      "FWK27 reviewers-gate-check.sh PreToolUse hook only render-checked, never invoked with a payload",
  ),
  ```

  Replace with:

  ```python
  SurfaceClass(
      "hook:.claude:reviewers-gate-check.sh",
      ".claude/hooks/reviewers-gate-check.sh",
      _EX,
      # FWK27/M15: driven via _run_gate_hook with a PreToolUse Bash/git-commit payload;
      # stub gate exits 1 → asserts FAIL->exit 2; PASS->exit 0; non-commit->exit 0 (grep guard).
      "test_rendered_gate_hook_blocks_on_fail_marker",
  ),
  ```

- [ ] **Step 2: Run the completeness suite.**

  ```bash
  uv run pytest tests/runtime_coverage/ -q
  ```

  Expect all pass:
  - `test_exercised_entries_name_an_existing_test` — `test_rendered_gate_hook_blocks_on_fail_marker`
    must exist in `tests/` (Task 1 lands first; the scan is `grep -r "^def (test_\w+)"` over all
    `test_*.py`).
  - `test_known_gap_entries_link_a_task` — the flipped entry no longer has a `_KG` status, so the
    old `FWK27 ...` evidence string is gone and no new `_KG` entry is added.
  - `test_no_stale_registry_entries` / `test_every_surface_is_classified` — unaffected (the key
    `hook:.claude:reviewers-gate-check.sh` still appears in the maximal render; it is only the
    status + evidence that changes).

  Commit.

---

## Task 3: Close-out

- [ ] **Step 1: Lint/format gate.** `uv run ruff check tests/ && uv run ruff format --check
  tests/acceptance/test_rendered_project.py tests/runtime_coverage/registry.py` — clean. Run
  `ruff format` (not just `check`) per [[ruff-format-check-after-inline-edits]].

- [ ] **Step 2: Full FWK27 run.**
  ```bash
  uv run pytest tests/acceptance/test_rendered_project.py -k "gate_hook" -q
  uv run pytest tests/runtime_coverage/ -q
  ```
  Three gate-hook tests + all completeness tests pass. These are fast (no docker/compose).

- [ ] **Step 3: State + commit.** Per the shared policy, this is ONE item on `fwk-coverage-batch`;
  defer the whole-branch Opus review to the end of the batch. Tick FWK27 in `PLAN.md` (or move to
  Done when the batch closes), append `ACTION_LOG.md` entries (per `pi-convention.md`), final commit
  with the skip-marker (`git add` then `git commit` as SEPARATE calls).

- [ ] **Step 4: Morning-report line.** Record: FWK27 green / or xfail + bug FWK id + ACTION_LOG ref.

---

## Self-Review

- **Spec coverage:** M15 (pipe PreToolUse git-commit payload; FAIL marker → exit 2; PASS → 0;
  non-commit → 0 grep-guard) → Tasks 1–2. ✓
- **Mirrors `_run_hook`:** `_run_gate_hook` follows the same `subprocess.run(..., input=payload,
  capture_output=True, text=True)` pattern as `_run_hook` (test_rendered_project.py:824–834), but
  invokes `bash .claude/hooks/reviewers-gate-check.sh` rather than `uv run python
  .claude/hooks/lint_changed.py`. The `json.dumps(payload)` / `input=` shape is identical. ✓
- **No docker, no API key, no uv sync:** the hook is a shell script; it only needs `bash`, `uv`
  (for the `uv run framework` shim — replaced by our stub), and `git` (for
  `git rev-parse --show-toplevel`). The rendered project's `copier copy` runs `git init` + an
  initial commit, so `git rev-parse` resolves. ✓
- **Non-vacuity (bite-proven):** Task 1 Step 4: flip FAIL case to assert `== 0` → RED (the hook
  genuinely exits 2); flip skip case to assert `== 2` → RED (the `ls` payload genuinely skips).
  Both prove the test detects the regression it claims to detect. ✓
- **Registry correctness:** exactly the ONE enumerated FWK27 `_KG` entry flips, naming a test
  Task 1 creates. `test_exercised_entries_name_an_existing_test` enforces the test exists before the
  flip is merged. No new keys invented. ✓
- **Payload shape:** `{"tool_name": "Bash", "tool_input": {"command": "git commit -m '...'"}}` —
  the hook's `grep -Eq '...'` reads the raw serialized JSON on stdin; the regex matches
  `git commit` when those tokens appear with at most one intervening token (the optional
  `([^[:space:]].*[[:space:]]+)?` group) and with word-boundary guards on both sides. The exact
  payload format is confirmed by reading the hook's grep pattern and the settings.json
  `PreToolUse` Bash matcher. ✓
- **`uv run framework` stub is PATH-isolated:** the fake `framework` binary is written to
  `dest/.fwk27-bin/framework` (inside the `tmp_path`); PATH is modified only in the `env=` dict
  passed to `subprocess.run`, not in the test process itself. No global state contamination. ✓
- **`set -euo pipefail` compatibility:** the hook uses `set -euo pipefail`; the `grep ... || exit
  0` on line 8 uses explicit `|| exit 0` to handle non-match (grep exits 1 on no-match, which
  `set -e` would otherwise treat as a fatal error). This is already correct in the template; the
  test exercises this path for the non-commit case. ✓

### Genuine design forks for the human (could not be fully resolved from code alone)

1. **PATH stub vs. full `uv sync` + real gate.** The plan stubs `framework` via PATH injection
   to avoid a real `uv sync` (which adds ~30s per test render). An alternative is to `uv sync` the
   rendered project and call the real `framework gate` after pre-populating a FAIL marker in
   `.framework/audit/latest/findings/` — but the skip-neutral logic in `cli.py:779` writes a PASS
   marker even when findings exist (because it short-circuits before `_finalize_gate`). The only
   way to reliably produce a non-zero exit from `framework gate` without a real AI backend is to
   configure a backend that fails, which requires a real API key. The PATH stub is the cleanest
   solution. **If the team later wants to exercise the real gate CLI path end-to-end, that is a
   separate plan.** This plan's scope is the hook's FAIL→exit-2 translation, not the gate engine
   itself.

2. **Bite-proof form.** The plan uses the cheapest bite-proof (flip the asserted returncode in the
   test itself). An alternative is to write a version of the hook with the exit codes swapped, but
   that touches the template — out of scope for a test-only plan. The returncode flip is sufficient
   and reversible.

### Anticipated real bugs these tests may surface (per the shared real-bug policy)

- **Broken `git commit` grep guard (line 8 of the hook).** The regex
  `(^|[^[:alnum:]_])git[[:space:]]+([^[:space:]].*[[:space:]]+)?commit([^[:alnum:]_]|$)` must
  match `"git commit"` embedded in a JSON string
  (`{"tool_name":"Bash","tool_input":{"command":"git commit -m '...'"}}`) when `grep -Eq` reads it
  from stdin. If the word-boundary guards incorrectly exclude the JSON-embedded form (e.g., the `"`
  before `git` fails the `[^[:alnum:]_]` lookbehind — but `"` satisfies `[^[:alnum:]_]`), the
  non-commit skip case exits 0 but the git-commit case also exits 0. Test 1 would go RED on this.
  **Most likely genuine candidate** — it has never been run against real JSON-embedded input.
- **FAIL verdict not translating to exit 2.** If `uv run framework gate` exits 1 but the `if !
  uv run framework gate` conditional is inverted or the `set -e` on the surrounding script absorbs
  the non-zero before the `if`, the hook exits 0 or crashes instead of exiting 2. Test 1
  (`test_rendered_gate_hook_blocks_on_fail_marker`) catches this.
- **Marker path mismatch.** The hook reads `.framework/audit/marker.json` relative to the git
  root (`cd "$root"` on line 10). If the `_run_gate_hook` helper writes the marker relative to
  `dest` (the rendered project root) but the hook resolves the git root to a different directory,
  the `python3 -c ...json.load(open('.framework/audit/marker.json'))...` fails silently (`||
  true`), the summary is empty, but the hook still exits 2. This is only a summary-readback bug,
  not a functional bug; Test 1 still passes. However, if `git rev-parse --show-toplevel` resolves
  to a PARENT of `dest` (because `tmp_path` is inside the framework repo's git tree), the `cd
  "$root"` would change to the framework repo root, not `dest`, and the marker path would be wrong
  — but the hook would still exit 2 (the `summary` readback uses `|| true`). Mitigation: confirm
  on the first run that `dest` is a git root (Copier inits a git repo at `dest`, so
  `git rev-parse --show-toplevel` from `dest` returns `dest`). If it somehow returns the framework
  repo root, the test still exits 2 (FAIL path), but the marker is not read. The non-commit test
  (exit 0) would still pass. Not a blocking concern, but worth noting.
