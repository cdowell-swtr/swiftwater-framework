# Slice D — Eval Scoring + Threshold Tuning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the eval harness to consume rendered-project fixtures, give every agent scoreable rendered fixtures (the 7 agentic agents fresh + Opus-4-8), then run the first real-key scorecard, calibrate `thresholds.yaml`, and confirm the review CI green on GHA.

**Architecture:** A hermetic **build** (Tasks 1–4: model changes → agentic fixtures → harness migration to a lazy loader + per-combo render cache → retire `.diff`) followed by a key-gated **scoring** tail (Task 5). The build needs no API key; scoring sources `~/.swiftwater-framework-keys.env`.

**Tech Stack:** Python 3.12, Copier render, `git apply`/`git diff`, the Anthropic SDK (real calls only in Task 5), `pytest`. Run tooling via `uv run`.

**Spec:** `docs/superpowers/specs/2026-05-29-slice-d-eval-scoring-design.md`

**Ordering note:** author the agentic fixtures (Task 3) and keep the legacy `.diff` BEFORE flipping the loader to the directory format (Task 4) — so the coverage gate never sees an agent with zero fixtures.

---

## File Structure
- `src/framework_cli/review/registry.py` (modify) — `AGENTIC_MODEL = "claude-opus-4-8"`; set it on the 7 agentic agents.
- `src/framework_cli/review/context.py` (modify) — budget-map Opus entries.
- `tests/eval/fixtures/<7 agentic agents>/{bad,good}/<case>/…` (create) — rendered fixtures.
- `tests/eval/fixtures/observability{,-infra,-db}/good/<case>/…` (create) — enriched good fixtures.
- `src/framework_cli/review/evals.py` (modify) — `Fixture` reshape, lazy `load_fixtures`, `realize_cached`.
- `src/framework_cli/cli.py` (modify) — the `eval` loop realizes via the cache.
- `tests/review/test_evals.py` + `tests/test_cli.py` (modify) — gate tests adapted to the directory format.
- `docs/superpowers/eval-scorecards/2026-05-…md` (create, Task 5) — the committed scorecard.
- `CLAUDE.md` (modify) — model IDs + state.

---

## Task 1: Model changes (Opus 4.8 on the agentic tier + budget map)

**Files:** Modify `src/framework_cli/review/registry.py`, `src/framework_cli/review/context.py`; Test `tests/review/test_context.py`, a registry test.

- [ ] **Step 1: Write the failing tests**

Append to `tests/review/test_context.py`:
```python
def test_budget_opus_has_1m_window():
    # Opus 4.7/4.8 serve a 1M-token context window (per the model migration guide).
    assert context_budget_chars("claude-opus-4-8") == (1_000_000 - 4096 - 8_000) * 4
    assert context_budget_chars("claude-opus-4-7") == (1_000_000 - 4096 - 8_000) * 4
```
Create `tests/review/test_agentic_model.py`:
```python
from framework_cli.review.registry import get_agent

_AGENTIC = (
    "architecture", "data-lineage", "privacy", "api-design",
    "observability-infra", "observability-db", "contracts",
)


def test_agentic_agents_use_opus_4_8():
    for name in _AGENTIC:
        assert get_agent(name).model == "claude-opus-4-8", name


def test_bundle_agents_stay_on_sonnet():
    for name in ("security", "observability", "documentation"):
        assert get_agent(name).model == "claude-sonnet-4-6", name
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/review/test_context.py::test_budget_opus_has_1m_window tests/review/test_agentic_model.py -v`
Expected: FAIL (budget map has opus at 200k; agentic agents are on DEFAULT_MODEL=sonnet).

- [ ] **Step 3: Fix the budget map** in `src/framework_cli/review/context.py` — update `_MODEL_CONTEXT_TOKENS`:
```python
_MODEL_CONTEXT_TOKENS: dict[str, int] = {
    "claude-sonnet-4-6": 200_000,
    "claude-opus-4-7": 1_000_000,
    "claude-opus-4-8": 1_000_000,
    "claude-haiku-4-5-20251001": 200_000,
}
```

- [ ] **Step 4: Set Opus 4.8 on the 7 agentic agents** in `registry.py`. Add a constant near `DEFAULT_MODEL`:
```python
AGENTIC_MODEL = "claude-opus-4-8"  # the agentic tier explores multi-turn; use the most capable model
```
Then change the `model` arg of each of the 7 agentic agents (architecture, data-lineage, privacy, api-design, observability-infra, observability-db, contracts) from `DEFAULT_MODEL` to `AGENTIC_MODEL`. (They already carry `context=ContextPolicy("agentic")` from Slice B — change only the model.)

- [ ] **Step 5: Run to verify pass + gate**

Run: `uv run pytest tests/review/test_context.py tests/review/test_agentic_model.py -q` → pass; then `uv run pytest -q --ignore=tests/acceptance` → green; `uv run ruff check . && uv run ruff format --check . && uv run mypy src` → clean.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/review/registry.py src/framework_cli/review/context.py tests/review/test_context.py tests/review/test_agentic_model.py
git commit -m "feat(review): Opus 4.8 on the agentic tier + 1M Opus budget window"
```

---

## Task 2: Refresh CLAUDE.md model IDs

**Files:** Modify `CLAUDE.md`.

- [ ] **Step 1:** In the environment/model note, update the model-ID facts to: latest Opus = `claude-opus-4-8`; latest Sonnet = `claude-sonnet-4-6` (the bundle agents' model); `claude-haiku-4-5-20251001`. Note the agentic review tier now runs `claude-opus-4-8`.
- [ ] **Step 2: Commit** (`git add CLAUDE.md` then commit `docs: refresh model IDs (Opus 4.8 latest; agentic tier on it)`).

---

## Task 3: Author rendered fixtures for the 7 agentic agents (+ enrich obs good)

Each agentic agent gets **2 bad + 1 good** rendered-project fixtures in the directory format:
```
tests/eval/fixtures/<agent>/bad/<case>/fixture.yaml   # {batteries: [...]}
tests/eval/fixtures/<agent>/bad/<case>/change.patch   # seeds a CROSS-FILE defect
tests/eval/fixtures/<agent>/bad/<case>/expect.json    # {"file": "<new-side seeded path>"}
tests/eval/fixtures/<agent>/good/<case>/{fixture.yaml,change.patch}
```
Do these one agent per commit. For each: render a project (`--with` the battery in the table), read the real files, craft a patch whose defect **spans files** (so agentic exploration is exercised), and point `expect.json` at the changed file. Validate each fixture realizes + the diff names the seeded file:
```bash
uv run python -c "from framework_cli.review.evals import realize_fixture; from pathlib import Path; import tempfile,yaml; \
c=Path('tests/eval/fixtures/<agent>/bad/<case>'); b=(yaml.safe_load((c/'fixture.yaml').read_text()) or {}).get('batteries',[]); \
r,d=realize_fixture(Path(tempfile.mkdtemp()), batteries=b, patch=(c/'change.patch').read_text()); print('<seeded path>' in d)"
```

**Per-agent guidance (battery + cross-file defect):**

| agent | fixture batteries | bad-fixture cross-file defect sketch |
|---|---|---|
| architecture | `[]` | a route importing a `db/` internal directly (layering violation that only shows when you read both the route and the db module) |
| data-lineage | `[]` | a field read from the request and written to the DB without the transform/validation that the model/repo elsewhere assumes |
| privacy | `[]` | a PII field (email) logged in one module while the model marks it sensitive in another |
| api-design | `[graphql]` | a GraphQL field whose resolver shape diverges from how the REST `Item` contract / client uses it (both-ends mismatch) |
| observability-infra | `[]` | a new `infra/` scrape target with no matching alert rule / dashboard (spans `prometheus.yml` + alerts dir) |
| observability-db | `[]` | a slow/unindexed query in the repo with no DB metric or span where the obs package establishes the pattern |
| contracts | `[consumers]` | a consumer client call whose shape the committed provider pact doesn't cover (both-ends) |

(The good fixture for each: the same area done correctly. Keep patches minimal + valid for `git apply`.)

**Also enrich the obs good fixtures** — add a second good case to `observability`, `observability-infra`, `observability-db` exercising the health-signal + correlation-id criteria (e.g. a repo fn that logs errors *with* the correlation id; a client *with* a `/health` ping), so precision is measured against all criteria, not just the metric/span true-negative.

- [ ] **Per agent (×7) + obs enrichment:** create the fixtures, validate each realizes + applies, commit per agent: `git add tests/eval/fixtures/<agent> && git commit -m "test(eval): rendered fixtures for <agent> (cross-file defects)"`. (The legacy `.diff` fixtures stay for now; the loader still reads them, so the gate stays green.)

---

## Task 4: Harness migration — lazy loader + per-combo cache; retire `.diff`

**Files:** Modify `src/framework_cli/review/evals.py`, `src/framework_cli/cli.py`, `tests/review/test_evals.py`, `tests/test_cli.py`; delete the legacy `*.diff`/`*.expect.json`.

- [ ] **Step 1: Write the failing test** — append to `tests/review/test_evals.py`:
```python
def test_load_fixtures_discovers_rendered_directory_format(tmp_path):
    from framework_cli.review.evals import load_fixtures

    case = tmp_path / "security" / "bad" / "hardcoded"
    case.mkdir(parents=True)
    (case / "fixture.yaml").write_text("batteries: []\n")
    (case / "change.patch").write_text("--- a/x\n+++ b/x\n")
    (case / "expect.json").write_text('{"file": "src/demo/x.py"}')
    fx = load_fixtures(tmp_path)
    assert len(fx) == 1
    assert fx[0].agent == "security" and fx[0].kind == "bad"
    assert fx[0].batteries == () and fx[0].seeded_file == "src/demo/x.py"
    assert "change.patch" not in fx[0].patch and fx[0].patch.startswith("--- a/x")
```

- [ ] **Step 2: Run to verify fail** — `uv run pytest tests/review/test_evals.py::test_load_fixtures_discovers_rendered_directory_format -v` → FAIL (loader reads `*.diff`, the `Fixture` has no `batteries`/`patch`).

- [ ] **Step 3: Reshape `Fixture` + rewrite `load_fixtures` + add `realize_cached`** in `evals.py`. Replace the `Fixture` dataclass:
```python
@dataclass(frozen=True)
class Fixture:
    agent: str
    kind: Literal["bad", "good"]
    name: str
    batteries: tuple[str, ...]
    patch: str
    seeded_file: str | None  # the new-side path the detection rule matches; set for bad
```
Replace `load_fixtures`:
```python
def load_fixtures(root: Path) -> list[Fixture]:
    """Discover rendered-project fixtures (lazy — no render here):
    `<root>/<agent>/{bad,good}/<case>/{fixture.yaml,change.patch[,expect.json]}`.
    A bad case missing a valid `expect.json` (naming the seeded `file`) is skipped."""
    import yaml

    fixtures: list[Fixture] = []
    for agent_dir in sorted(p for p in root.glob("*") if p.is_dir()):
        agent = agent_dir.name
        for kind in ("bad", "good"):
            for case in sorted(p for p in (agent_dir / kind).glob("*") if p.is_dir()):
                patch_f, spec_f = case / "change.patch", case / "fixture.yaml"
                if not (patch_f.is_file() and spec_f.is_file()):
                    continue
                batteries = tuple(
                    (yaml.safe_load(spec_f.read_text()) or {}).get("batteries", [])
                )
                seeded_file: str | None = None
                if kind == "bad":
                    try:
                        seeded_file = str(
                            json.loads((case / "expect.json").read_text())["file"]
                        )
                    except (OSError, json.JSONDecodeError, KeyError, TypeError):
                        continue
                fixtures.append(
                    Fixture(agent, kind, case.name, batteries, patch_f.read_text(), seeded_file)
                )
    return fixtures
```
Add a per-battery-combo realize cache (renders the committed base once per combo, copies + patches per fixture):
```python
import shutil


def realize_cached(
    fx: Fixture, cache: dict[tuple[str, ...], Path], base_dir: Path
) -> tuple[Path, str]:
    """Realize `fx` reusing a per-combo rendered+committed base. `base_dir` is a
    caller-owned tempdir; `cache` maps battery-combo → the committed base path."""
    if fx.batteries not in cache:
        base = base_dir / ("base-" + ("-".join(fx.batteries) or "none")) / "demo"
        render_project(base, {**_FIXTURE_ANSWERS, "batteries": list(fx.batteries)})
        subprocess.run(["git", "init", "-q"], cwd=base, check=True)
        subprocess.run(["git", "add", "-A"], cwd=base, check=True)
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base"],
            cwd=base, check=True,
        )
        cache[fx.batteries] = base
    work = base_dir / f"fx-{fx.agent}-{fx.kind}-{fx.name}"
    shutil.copytree(cache[fx.batteries], work)
    subprocess.run(["git", "apply", "-"], cwd=work, input=fx.patch, text=True, check=True)
    diff = subprocess.run(
        ["git", "diff"], cwd=work, capture_output=True, text=True, check=True
    ).stdout
    return work, diff
```

- [ ] **Step 4: Wire the `eval` loop** in `cli.py`. The fixture loop (`for fx in fx_list:`) realizes once per fixture (outside the `--repeat` loop) via the cache, then runs the agent `repeat` times on the realized `(root, diff)`. At the top of `eval_agents` after `root = Path(fixtures)` add:
```python
    import tempfile
    from framework_cli.review.evals import realize_cached

    _base_dir = Path(tempfile.mkdtemp(prefix="evalbase-"))
    _combo_cache: dict = {}
```
and change the per-fixture body so it does `rroot, rdiff = realize_cached(fx, _combo_cache, _base_dir)` once, then the `for _ in range(repeat):` loop calls `_eval_run(rdiff, rroot, spec)` (replacing `_eval_run(fx.diff, …)`). The `flags(found, spec, file=fx.seeded_file)` call is unchanged (seeded_file is still on `Fixture`).

- [ ] **Step 5: Adapt the gate tests.** In `tests/review/test_evals.py`:
  - `test_every_registered_agent_has_fixtures`: change the assertion to `bad >= 1` (bundle agents deliberately keep 1 rendered bad; spec §Resolved-decisions) and `good >= 1`.
  - `test_fixtures_are_wellformed`: validate structurally on the directory format — each bad case has a non-empty `change.patch` + an `expect.json` with a `file`; each good case has a non-empty `change.patch`. (No eager render.)
  - `test_contracts_has_full_fixture_set` / the legacy `*.diff` loader tests (`test_load_fixtures_discovers_bad_and_good`, `test_load_fixtures_skips_bad_without_valid_sidecar`): rewrite to the directory format (or remove the `.diff`-specific ones, since `.diff` is retired).
  In `tests/test_cli.py`: any test building `.diff` fixtures via `_make_fixture` → update that helper to write the directory format (`<case>/fixture.yaml`+`change.patch`+`expect.json`), and the eval tests that monkeypatch `_eval_run` keep working (the loop still calls it).

- [ ] **Step 6: Retire the legacy fixtures** — delete every `tests/eval/fixtures/*/{bad,good}/*.diff` and `*.expect.json` (the sidecars next to the old `.diff`, NOT the new `<case>/expect.json`):
```bash
find tests/eval/fixtures -maxdepth 3 -name '*.diff' -delete
find tests/eval/fixtures -maxdepth 3 -type f -name '*.expect.json' -delete   # only the flat sidecars; case-dir expect.json is at depth 4
```
(Verify `git status` shows only the flat `.diff`/`.expect.json` deletions, not the `<case>/expect.json` files.)

- [ ] **Step 7: Run + verify** — `uv run pytest tests/review tests/test_cli.py -q` → pass; `uv run pytest -q --ignore=tests/acceptance` → green; ruff/format/mypy clean. Smoke the loader over the real fixtures: `uv run python -c "from framework_cli.review.evals import load_fixtures; from pathlib import Path; fx=load_fixtures(Path('tests/eval/fixtures')); import collections; c=collections.Counter((f.agent,f.kind) for f in fx); print(len(fx),'fixtures'); print(sorted({f.agent for f in fx}))"` → 18 agents present, each with ≥1 bad + ≥1 good.

- [ ] **Step 8: Commit**

```bash
git add src/framework_cli/review/evals.py src/framework_cli/cli.py tests/review/test_evals.py tests/test_cli.py tests/eval/fixtures
git commit -m "feat(eval): migrate harness to rendered-project fixtures (lazy loader + per-combo cache); retire .diff"
```

---

## Task 5: Scoring + threshold calibration + scorecard + GHA (KEY-GATED)

> Requires the keys. Source them per-command: `set -a; . ~/.swiftwater-framework-keys.env; set +a; …`. This task spends real API budget — start small.

- [ ] **Step 1: Smoke one agent (cheap)** — confirm the real path works end to end on one bundle agent, `--repeat 1`:
```bash
set -a; . ~/.swiftwater-framework-keys.env; set +a; uv run framework eval security --repeat 1 --fixtures tests/eval/fixtures
```
Expected: prints `review-security  recall X.XX  fp X.XX  PASS|FAIL` (a real score, not "skipped"). If "skipped", the EVAL key isn't loaded — fix the source path.

- [ ] **Step 2: Smoke one agentic agent** — confirm the Opus-4-8 agentic loop scores:
```bash
set -a; . ~/.swiftwater-framework-keys.env; set +a; uv run framework eval architecture --repeat 1 --fixtures tests/eval/fixtures
```
Expected: a real score; the agentic loop runs (may take longer / multiple turns).

- [ ] **Step 3: Full scorecard run** — all agents, `--repeat 4` (rates averaged for stability):
```bash
set -a; . ~/.swiftwater-framework-keys.env; set +a; uv run framework eval --repeat 4 --fixtures tests/eval/fixtures | tee /tmp/scorecard.txt
```

- [ ] **Step 4: Calibrate `tests/eval/fixtures/thresholds.yaml`** — for each agent whose healthy recall/fp doesn't fit the `0.67`/`0.34` defaults, add an entry with a **safety margin**: `recall_min` a notch below the observed recall, `fp_max` a notch above the observed fp (so run-to-run variance doesn't flip PASS↔FAIL). Re-run the full eval; iterate until every agent PASSes with margin (or note any agent whose prompt genuinely underperforms as a follow-up rather than loosening the threshold to meaninglessness).

- [ ] **Step 5: Commit the scorecard + thresholds** — write `docs/superpowers/eval-scorecards/2026-05-<dd>-first-real-scorecard.md` (the per-agent recall/fp table from the run + the model each agent used + the date + `--repeat` value), and the tuned `thresholds.yaml`:
```bash
git add docs/superpowers/eval-scorecards/ tests/eval/fixtures/thresholds.yaml
git commit -m "test(eval): first real-key scorecard + calibrated thresholds"
```

- [ ] **Step 6: GHA confirmation** — add a `workflow_dispatch` trigger to `.github/workflows/agent-evals.yml`; with the `ANTHROPIC_FRAMEWORK_CI_EVAL` secret set, dispatch the workflow and confirm green. Push a trivial framework PR (or the branch) and confirm `review.yml` runs green (the agents actually review, not skip-neutral). Commit the `workflow_dispatch` addition.

- [ ] **Step 7: Retire the caveats** — in CLAUDE.md "Known follow-ups", remove/resolve the "⚠ review agents never real-key scored / provisional thresholds" entry (now done); note the scorecard path. `git add CLAUDE.md` + commit.

---

## Self-review notes
- **Spec coverage:** §2 harness migration → Task 4; §3 fixtures (7 agentic × 2 bad+1 good + obs good enrichment) → Task 3; §4 model changes (budget map, opus-4-8, CLAUDE.md IDs) → Tasks 1–2; §5 scoring/calibration/scorecard/GHA → Task 5; §6 testing → the hermetic tests in Tasks 1/4 + the Task 5 smokes.
- **Ordering:** fixtures (T3) before the loader flip + `.diff` retirement (T4) so the coverage gate never sees a zero-fixture agent; model changes (T1) are independent and first.
- **Placeholder scan:** the per-agent fixture *content* is guided by a table (defect sketch + battery) rather than 21 literal patches — they must be authored against real rendered files, the established pattern from Slice A Task 8; each is validated by the realize one-liner.
- **Type consistency:** `Fixture(agent, kind, name, batteries: tuple, patch: str, seeded_file)`, `realize_cached(fx, cache, base_dir) -> (root, diff)`, `realize_fixture(dest, *, batteries, patch)` (unchanged), `AGENTIC_MODEL`, the 7 agentic agent names used consistently.
- **Cost guard:** Task 5 starts with single-agent `--repeat 1` smokes before the full `--repeat 4 × 18` run (7 on Opus 4.8) — bounded, and the user authorized the spend.
