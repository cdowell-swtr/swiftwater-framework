# Unified Configurable Wizard (8f-w) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a guided `framework new` wizard (questionary, interactive-or-declarative) that resolves data-needs to db-paradigm batteries and configures alert channels (Slack/email/PagerDuty/webhook), with a hard "no silent no-op" deliverability guarantee.

**Architecture:** A generic, registry-driven wizard module in the CLI sources answers (interactive prompts on a TTY with no relevant flag; flags or non-TTY → defaults), then feeds them through the *unchanged* `render_project(data=…)` path. A new framework-owned `alert_channels` answer drives conditionally-rendered LOCKED `alertmanager.yml` receivers + `.env.example` managed-section secrets (byte-identical for the `["webhook"]` default). A deploy precondition hard-fails if a configured channel's secret is empty; an advisory deploy smoke reads Alertmanager's own failure metric; an always-on meta-alert surfaces steady-state delivery breakage.

**Tech Stack:** Python 3.12, Typer, Copier, `questionary` (promoted transitive→direct), Jinja2 templating, Alertmanager (`*_file` secrets), bash deploy scripts, pytest.

**Spec:** `docs/superpowers/specs/2026-05-27-unified-wizard-design.md`

---

## File Structure

**CLI (framework source):**
- `src/framework_cli/wizard.py` *(create)* — needs→battery map, channel parse/validate, and the interactive/fallback runner. Pure-logic functions + thin questionary seams.
- `src/framework_cli/cli.py` *(modify)* — `new` invokes the wizard + gains `--alerts`; `upskill` gains `--alerts`.
- `src/framework_cli/source.py` *(modify)* — `read_alert_channels` / `record_alert_channels` (mirror the batteries pair).
- `src/framework_cli/upskill.py` *(modify)* — `upskill_project(…, alert_channels=…)`.
- `src/framework_cli/integrity/classes.py` *(modify)* — register the new always-on LOCKED files.
- `pyproject.toml` / `uv.lock` *(modify)* — `questionary` as a direct dependency.

**Template payload (rendered into projects):**
- `src/framework_cli/template/copier.yml` *(modify)* — declare the `alert_channels` answer.
- `src/framework_cli/template/infra/observability/alertmanager/alertmanager.yml` → `…/alertmanager.yml.jinja` *(rename+modify)* — conditional receiver blocks.
- `src/framework_cli/template/.env.example.jinja` *(modify)* — per-channel managed-section secret vars.
- `src/framework_cli/template/infra/observability/prometheus/alerts/alertmanager_alerts.yml` *(create, always-on)* — `AlertmanagerNotificationsFailing`.
- `src/framework_cli/template/infra/deploy/check_alert_secrets.sh.jinja` *(create, always-on)* — #1 precondition.
- `src/framework_cli/template/infra/deploy/alert_smoke.sh` *(create, always-on)* — #3 smoke.
- `src/framework_cli/template/infra/deploy/strategy.sh` *(modify)* — call the precondition in `deploy()`; add an `alert-smoke` operation.
- `src/framework_cli/template/.github/workflows/deploy-staging.yml` + `deploy-prod.yml` *(modify)* — advisory smoke step.

**Tests:** `tests/test_wizard.py` *(create)*, additions to `tests/test_copier_runner.py`, `tests/test_cli.py`, `tests/test_source.py` (create if absent), `tests/test_upskill.py` (or existing), `tests/acceptance/test_rendered_project.py`.

> **Baseline manifest shift (expected, precedented by OBS-PROD/SVC-PROD):** the always-on additions — the `check_alert_secrets.sh` + `alert_smoke.sh` scripts, the `alertmanager_alerts.yml` rule, the `strategy.sh` precondition call, and the workflow smoke steps — change the rendered bytes for *every* project (including the default). The *receiver content* of `alertmanager.yml`/`observability.yml`/`.env.example` stays byte-identical for the `["webhook"]` default; the shift comes from the new always-on files/wiring. Existing projects pick it up on `framework upskill`.

---

## Task 1: Declare the `alert_channels` answer + record/read helpers

**Files:**
- Modify: `src/framework_cli/template/copier.yml`
- Modify: `src/framework_cli/source.py`
- Test: `tests/test_source.py` (create if absent)

- [ ] **Step 1: Write the failing test**

Create/append `tests/test_source.py`:

```python
from pathlib import Path

from framework_cli.source import read_alert_channels, record_alert_channels


def _answers(tmp_path: Path, body: str) -> Path:
    p = tmp_path / ".copier-answers.yml"
    p.write_text(body)
    return tmp_path


def test_read_alert_channels_defaults_to_webhook_when_absent(tmp_path: Path):
    _answers(tmp_path, "_commit: v0.1.0\n")
    assert read_alert_channels(tmp_path) == ["webhook"]


def test_read_alert_channels_reads_recorded_list(tmp_path: Path):
    _answers(tmp_path, "alert_channels:\n- slack\n- email\n")
    assert read_alert_channels(tmp_path) == ["slack", "email"]


def test_record_alert_channels_replaces_existing_block(tmp_path: Path):
    project = _answers(tmp_path, "alert_channels:\n- webhook\nproject_name: Demo\n")
    record_alert_channels(project, ["slack", "pagerduty"])
    text = (project / ".copier-answers.yml").read_text()
    assert "project_name: Demo" in text
    assert "alert_channels:\n- slack\n- pagerduty\n" in text
    assert "- webhook" not in text


def test_record_alert_channels_empty_writes_default(tmp_path: Path):
    project = _answers(tmp_path, "alert_channels:\n- slack\n")
    record_alert_channels(project, [])
    assert "alert_channels:\n- webhook\n" in (project / ".copier-answers.yml").read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_source.py -q`
Expected: FAIL — `ImportError: cannot import name 'read_alert_channels'`.

- [ ] **Step 3: Add the helpers to `source.py`**

Add after `record_batteries` in `src/framework_cli/source.py`:

```python
def read_alert_channels(project: Path) -> list[str]:
    """The alert channels recorded in .copier-answers.yml (['webhook'] if none/absent)."""
    import yaml

    answers = project / _ANSWERS_REL
    if not answers.is_file():
        return ["webhook"]
    data = yaml.safe_load(answers.read_text()) or {}
    value = data.get("alert_channels")
    if isinstance(value, list) and value:
        return [str(c) for c in value]
    return ["webhook"]


def record_alert_channels(project: Path, channels: list[str]) -> None:
    """Write the alert-channel set into .copier-answers.yml (framework-owned, like batteries).

    Empty input records the ['webhook'] default so a project always has a channel.
    """
    effective = channels or ["webhook"]
    answers = project / _ANSWERS_REL
    out: list[str] = []
    skipping = False
    for line in answers.read_text().splitlines():
        if line.startswith("alert_channels:"):
            skipping = True
            continue
        if skipping and line.startswith("- "):
            continue
        skipping = False
        out.append(line)
    out.append("alert_channels:")
    out.extend(f"- {c}" for c in effective)
    answers.write_text("\n".join(out) + "\n")
```

- [ ] **Step 4: Declare the answer in `copier.yml`**

In `src/framework_cli/template/copier.yml`, add after the `batteries:` block (before `uses_postgres_extension:`):

```yaml
alert_channels:
  type: yaml
  help: Active alert channels (set via the wizard / --alerts); not prompted.
  default: ["webhook"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_source.py -q && uv run pytest tests/test_copier_runner.py -q`
Expected: PASS (existing render tests still pass — `alert_channels` defaults to `["webhook"]`).

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/source.py src/framework_cli/template/copier.yml tests/test_source.py
git commit -m "feat(wizard): declare alert_channels answer + read/record helpers"
```

---

## Task 2: Wizard pure logic — needs→battery map + channel parse/validate

**Files:**
- Create: `src/framework_cli/wizard.py`
- Test: `tests/test_wizard.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_wizard.py`:

```python
import pytest

from framework_cli.wizard import (
    KNOWN_CHANNELS,
    NEED_TO_BATTERY,
    parse_channels,
    resolve_needs,
)


def test_need_to_battery_covers_the_five_paradigms():
    assert NEED_TO_BATTERY == {
        "document": "mongodb",
        "vector": "pgvector",
        "timeseries": "timescaledb",
        "graph": "age",
        "cache": "redis",
    }


def test_resolve_needs_maps_and_dedups():
    assert resolve_needs(["vector", "cache", "vector"]) == ["pgvector", "redis"]


def test_resolve_needs_empty_is_empty():
    assert resolve_needs([]) == []


def test_resolve_needs_unknown_raises():
    with pytest.raises(ValueError, match="unknown data need: 'blob'"):
        resolve_needs(["blob"])


def test_parse_channels_validates_dedups_and_orders():
    # canonical order, deduped
    assert parse_channels(["email", "webhook", "email"]) == ["webhook", "email"]


def test_parse_channels_rejects_empty():
    with pytest.raises(ValueError, match="select at least one alert channel"):
        parse_channels([])


def test_parse_channels_rejects_unknown():
    with pytest.raises(ValueError, match="unknown alert channel: 'sms'"):
        parse_channels(["sms"])


def test_known_channels_order():
    assert KNOWN_CHANNELS == ("webhook", "slack", "email", "pagerduty")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_wizard.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'framework_cli.wizard'`.

- [ ] **Step 3: Write the module (pure logic only for now)**

Create `src/framework_cli/wizard.py`:

```python
"""The `framework new` wizard: needs→battery resolution, alert-channel parsing, and an
interactive/non-interactive runner. Sources answers only — rendering is unchanged."""

from __future__ import annotations

# Needs-language → atomic battery (the db-paradigm half). Relational is always-on (not listed).
NEED_TO_BATTERY: dict[str, str] = {
    "document": "mongodb",
    "vector": "pgvector",
    "timeseries": "timescaledb",
    "graph": "age",
    "cache": "redis",
}

# Alert channels, in canonical render order. `webhook` is the always-available default.
KNOWN_CHANNELS: tuple[str, ...] = ("webhook", "slack", "email", "pagerduty")


def resolve_needs(needs: list[str]) -> list[str]:
    """Map data-need keys to batteries (deduped, input order preserved). Unknown → ValueError."""
    out: list[str] = []
    for need in needs:
        if need not in NEED_TO_BATTERY:
            raise ValueError(f"unknown data need: {need!r}")
        battery = NEED_TO_BATTERY[need]
        if battery not in out:
            out.append(battery)
    return out


def parse_channels(channels: list[str]) -> list[str]:
    """Validate + dedup an alert-channel selection, returned in canonical order.

    Empty → ValueError (a project must have at least one channel; the silent no-op is what
    this whole feature exists to kill). Unknown channel → ValueError.
    """
    selected = set()
    for c in channels:
        if c not in KNOWN_CHANNELS:
            raise ValueError(f"unknown alert channel: {c!r} (known: {', '.join(KNOWN_CHANNELS)})")
        selected.add(c)
    if not selected:
        raise ValueError("select at least one alert channel")
    return [c for c in KNOWN_CHANNELS if c in selected]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_wizard.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/wizard.py tests/test_wizard.py
git commit -m "feat(wizard): needs->battery map + alert-channel parse/validate"
```

---

## Task 3: Wizard interactive/non-interactive runner

**Files:**
- Modify: `src/framework_cli/wizard.py`
- Test: `tests/test_wizard.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_wizard.py`:

```python
from framework_cli import wizard as wiz


def test_run_wizard_non_interactive_no_flags_uses_defaults():
    out = wiz.run_wizard(with_=[], alerts=None, interactive=False)
    assert out == {"batteries": [], "alert_channels": ["webhook"]}


def test_run_wizard_with_flag_skips_needs_prompt(monkeypatch):
    # interactive, but --with passed → the needs prompt must NOT run
    monkeypatch.setattr(wiz, "_prompt_needs", lambda: (_ for _ in ()).throw(AssertionError("prompted")))
    monkeypatch.setattr(wiz, "_prompt_channels", lambda: ["webhook"])
    out = wiz.run_wizard(with_=["graphql"], alerts=None, interactive=True)
    assert out["batteries"] == ["graphql"]


def test_run_wizard_alerts_flag_skips_channel_prompt(monkeypatch):
    monkeypatch.setattr(wiz, "_prompt_needs", lambda: [])
    monkeypatch.setattr(wiz, "_prompt_channels", lambda: (_ for _ in ()).throw(AssertionError("prompted")))
    out = wiz.run_wizard(with_=[], alerts="slack,email", interactive=True)
    assert out["alert_channels"] == ["slack", "email"]


def test_run_wizard_interactive_prompts_both(monkeypatch):
    monkeypatch.setattr(wiz, "_prompt_needs", lambda: ["vector"])
    monkeypatch.setattr(wiz, "_prompt_channels", lambda: ["webhook", "slack"])
    out = wiz.run_wizard(with_=[], alerts=None, interactive=True)
    assert out == {"batteries": ["pgvector"], "alert_channels": ["webhook", "slack"]}


def test_run_wizard_parses_comma_separated_alerts_flag():
    out = wiz.run_wizard(with_=[], alerts="webhook, pagerduty", interactive=False)
    assert out["alert_channels"] == ["webhook", "pagerduty"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_wizard.py -q`
Expected: FAIL — `AttributeError: module 'framework_cli.wizard' has no attribute 'run_wizard'`.

- [ ] **Step 3: Add the runner + questionary seams**

Append to `src/framework_cli/wizard.py`:

```python
_NEED_CHOICES = [
    ("Document store", "document"),
    ("Vector / similarity search", "vector"),
    ("Time-series", "timeseries"),
    ("Graph (Cypher)", "graph"),
    ("Cache / key-value", "cache"),
]


def _prompt_needs() -> list[str]:  # pragma: no cover - thin questionary wrapper, mocked in tests
    import questionary

    answer = questionary.checkbox(
        "What kind of data does it store? (relational is always on)",
        choices=[questionary.Choice(title=label, value=value) for label, value in _NEED_CHOICES],
    ).ask()
    return list(answer or [])


def _prompt_channels() -> list[str]:  # pragma: no cover - thin questionary wrapper, mocked in tests
    import questionary

    answer = questionary.checkbox(
        "Where should alerts go?",
        choices=[
            questionary.Choice(title=c, value=c, checked=(c == "webhook"))
            for c in KNOWN_CHANNELS
        ],
    ).ask()
    return list(answer or [])


def _split_alerts(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def run_wizard(*, with_: list[str], alerts: str | None, interactive: bool) -> dict[str, list[str]]:
    """Source the wizard answers. Flags win and skip their prompt; on a TTY with no flag we
    prompt; otherwise we fall back to defaults (batteries=[], channels=['webhook']).

    Returns the *pre-resolution* battery names (the caller runs resolve()) and the validated
    alert-channel list.
    """
    if with_:
        batteries = list(with_)
    elif interactive:
        batteries = resolve_needs(_prompt_needs())
    else:
        batteries = []

    if alerts is not None:
        channels = parse_channels(_split_alerts(alerts))
    elif interactive:
        channels = parse_channels(_prompt_channels())
    else:
        channels = ["webhook"]

    return {"batteries": batteries, "alert_channels": channels}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_wizard.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/wizard.py tests/test_wizard.py
git commit -m "feat(wizard): interactive/non-interactive runner with flag-skip"
```

---

## Task 4: Wire the wizard into `framework new` (+ `--alerts`)

**Files:**
- Modify: `src/framework_cli/cli.py:38-75` (the `new` command)
- Modify: `pyproject.toml` (promote `questionary`)
- Test: `tests/test_cli.py`, `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py` (use the existing `CliRunner`/`app` imports in that file):

```python
def test_new_records_alert_channels_default(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from framework_cli.cli import app

    monkeypatch.chdir(tmp_path)
    # non-TTY in tests → no prompts, defaults
    result = CliRunner().invoke(app, ["new", "Demo"])
    assert result.exit_code == 0, result.output
    answers = (tmp_path / "demo" / ".copier-answers.yml").read_text()
    assert "alert_channels:" in answers and "- webhook" in answers


def test_new_alerts_flag_sets_channels(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from framework_cli.cli import app

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["new", "Demo", "--alerts", "slack,pagerduty"])
    assert result.exit_code == 0, result.output
    answers = (tmp_path / "demo" / ".copier-answers.yml").read_text()
    assert "- slack" in answers and "- pagerduty" in answers
    assert "- webhook" not in answers


def test_new_with_flag_still_resolves_batteries(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from framework_cli.cli import app

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["new", "Demo", "--with", "graphql"])
    assert result.exit_code == 0, result.output
    answers = (tmp_path / "demo" / ".copier-answers.yml").read_text()
    assert "- graphql" in answers


def test_new_bad_alert_channel_errors(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from framework_cli.cli import app

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["new", "Demo", "--alerts", "sms"])
    assert result.exit_code == 1
    assert "unknown alert channel" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -k "alert or with_flag or alert_channels" -q`
Expected: FAIL — `--alerts` is an unknown option / `alert_channels` not recorded.

- [ ] **Step 3: Update the `new` command**

In `src/framework_cli/cli.py`, add `import sys` near the top imports, then replace the `new` command body. New signature + body:

```python
@app.command()
def new(
    name: str = typer.Argument(..., help="Human-readable project name"),
    python_version: str = typer.Option("3.12", help="Python version to target"),
    with_: list[str] = typer.Option(
        [], "--with", help="Activate a battery (repeatable), e.g. --with websockets."
    ),
    alerts: str = typer.Option(
        None, "--alerts", help="Alert channels, comma-separated: webhook,slack,email,pagerduty."
    ),
) -> None:
    """Scaffold a new project from the framework template."""
    from framework_cli.wizard import run_wizard

    names = derive_names(name)
    dest = Path.cwd() / names.project_slug

    if dest.exists():
        typer.echo(f"Error: {dest} already exists", err=True)
        raise typer.Exit(code=1)

    try:
        answers = run_wizard(with_=with_, alerts=alerts, interactive=sys.stdin.isatty())
        batteries = resolve_batteries(answers["batteries"])
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    render_project(
        dest,
        {
            "project_name": names.project_name,
            "project_slug": names.project_slug,
            "package_name": names.package_name,
            "python_version": python_version,
            "batteries": batteries,
            "alert_channels": answers["alert_channels"],
        },
    )
    write_manifest(dest, installed_framework_version())
    record_portable_source(dest, installed_framework_version())
    msg = f"Created '{names.project_slug}' at {dest}"
    if batteries:
        msg += f" (batteries: {', '.join(batteries)})"
    if answers["alert_channels"] != ["webhook"]:
        msg += f" (alerts: {', '.join(answers['alert_channels'])})"
    typer.echo(msg)
```

- [ ] **Step 4: Promote `questionary` to a direct dependency**

In `pyproject.toml`, add `"questionary>=2.0"` to the `dependencies` array (after `pyyaml>=6.0`). Then relock:

Run: `uv lock && uv sync`
Expected: lock resolves with no new transitive surface (questionary was already present via copier).

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -q && uv run pytest tests/test_copier_runner.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/cli.py pyproject.toml uv.lock tests/test_cli.py
git commit -m "feat(wizard): wire wizard + --alerts into framework new; questionary direct dep"
```

---

## Task 5: Conditional `alertmanager.yml` receivers (byte-identical default)

**Files:**
- Rename+modify: `src/framework_cli/template/infra/observability/alertmanager/alertmanager.yml` → `alertmanager.yml.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_copier_runner.py`:

```python
ALERTMANAGER_DEFAULT = """\
route:
  receiver: "default"
  group_by: ["alertname"]
  group_wait: 10s
  group_interval: 1m
  repeat_interval: 1h

receivers:
  - name: "default"
    webhook_configs:
      # The URL is read from a mounted file (the APP_ALERT_WEBHOOK_URL secret, materialized on
      # deploy at /etc/alertmanager/webhook_url). When the file is absent (e.g. local dev),
      # alertmanager still loads this config; notifications simply no-op until it exists.
      - url_file: /etc/alertmanager/webhook_url
        send_resolved: true
"""


def test_alertmanager_byte_identical_for_default_webhook(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})  # alert_channels defaults to ["webhook"]
    rendered = (dest / "infra/observability/alertmanager/alertmanager.yml").read_text()
    assert rendered == ALERTMANAGER_DEFAULT


def test_alertmanager_renders_slack_and_pagerduty(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "alert_channels": ["slack", "pagerduty"]})
    text = (dest / "infra/observability/alertmanager/alertmanager.yml").read_text()
    assert "slack_configs:" in text and "api_url_file: /etc/alertmanager/slack_api_url" in text
    assert "pagerduty_configs:" in text and "routing_key_file: /etc/alertmanager/pagerduty_routing_key" in text
    assert "webhook_configs:" not in text  # webhook not selected
    parsed = yaml.safe_load(text)
    assert parsed["receivers"][0]["name"] == "default"


def test_alertmanager_renders_email(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "alert_channels": ["email"]})
    text = (dest / "infra/observability/alertmanager/alertmanager.yml").read_text()
    assert "email_configs:" in text
    assert "auth_password_file: /etc/alertmanager/smtp_auth_password" in text
    assert yaml.safe_load(text)["receivers"][0]["name"] == "default"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py -k alertmanager -q`
Expected: FAIL — slack/email/pagerduty blocks absent (the file is still static webhook-only).

- [ ] **Step 3: Rename the file and add the Jinja**

```bash
git mv src/framework_cli/template/infra/observability/alertmanager/alertmanager.yml \
       src/framework_cli/template/infra/observability/alertmanager/alertmanager.yml.jinja
```

Replace its contents with (whitespace control is load-bearing — the default must be byte-identical to `ALERTMANAGER_DEFAULT`):

```jinja
route:
  receiver: "default"
  group_by: ["alertname"]
  group_wait: 10s
  group_interval: 1m
  repeat_interval: 1h

receivers:
  - name: "default"
{%- if "webhook" in alert_channels %}
    webhook_configs:
      # The URL is read from a mounted file (the APP_ALERT_WEBHOOK_URL secret, materialized on
      # deploy at /etc/alertmanager/webhook_url). When the file is absent (e.g. local dev),
      # alertmanager still loads this config; notifications simply no-op until it exists.
      - url_file: /etc/alertmanager/webhook_url
        send_resolved: true
{%- endif %}
{%- if "slack" in alert_channels %}
    slack_configs:
      # api_url read from the mounted APP_ALERT_SLACK_API_URL secret (see infra/deploy/README.md).
      - api_url_file: /etc/alertmanager/slack_api_url
        channel: "#alerts"
        send_resolved: true
{%- endif %}
{%- if "email" in alert_channels %}
    email_configs:
      # SMTP config from the .env managed section; password from the mounted secret file.
      - to: "${APP_ALERT_SMTP_TO}"
        from: "${APP_ALERT_SMTP_FROM}"
        smarthost: "${APP_ALERT_SMTP_SMARTHOST}"
        auth_username: "${APP_ALERT_SMTP_AUTH_USERNAME}"
        auth_password_file: /etc/alertmanager/smtp_auth_password
        send_resolved: true
{%- endif %}
{%- if "pagerduty" in alert_channels %}
    pagerduty_configs:
      # routing_key read from the mounted APP_ALERT_PAGERDUTY_ROUTING_KEY secret.
      - routing_key_file: /etc/alertmanager/pagerduty_routing_key
        send_resolved: true
{%- endif %}
```

> **Note on byte-identity:** `{%- if … %}` strips the preceding newline, so after `- name: "default"` the webhook block begins on its own line exactly as in the original. After rendering the default, run `diff` against the captured string in the test; if a trailing-newline mismatch appears, adjust the final `{%- endif %}` to `{% endif %}` (no leading dash) so the file ends with a single `\n`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_copier_runner.py -k alertmanager -q`
Expected: PASS (including the byte-identical default).

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/infra/observability/alertmanager/ tests/test_copier_runner.py
git commit -m "feat(wizard): conditional alertmanager receivers per alert channel"
```

---

## Task 6: Per-channel secret vars in `.env.example`

**Files:**
- Modify: `src/framework_cli/template/.env.example.jinja`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_copier_runner.py`:

```python
def test_env_example_default_has_only_webhook_secret(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    env = (dest / ".env.example").read_text()
    assert "APP_ALERT_WEBHOOK_URL=" in env
    assert "APP_ALERT_SLACK_API_URL" not in env
    assert "APP_ALERT_PAGERDUTY_ROUTING_KEY" not in env
    assert "APP_ALERT_SMTP_" not in env


def test_env_example_adds_selected_channel_secrets(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "alert_channels": ["slack", "email", "pagerduty"]})
    env = (dest / ".env.example").read_text()
    assert "APP_ALERT_SLACK_API_URL=" in env
    assert "APP_ALERT_PAGERDUTY_ROUTING_KEY=" in env
    for v in ("SMARTHOST", "FROM", "TO", "AUTH_USERNAME", "AUTH_PASSWORD"):
        assert f"APP_ALERT_SMTP_{v}=" in env
    # webhook not selected → its var absent
    assert "APP_ALERT_WEBHOOK_URL=" not in env
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py -k env_example -q`
Expected: FAIL — slack/email/pagerduty vars not rendered.

- [ ] **Step 3: Update `.env.example.jinja`**

In `src/framework_cli/template/.env.example.jinja`, replace the observability block (the lines around `GRAFANA_ADMIN_PASSWORD` / `APP_ALERT_WEBHOOK_URL`) with channel-gated vars:

```jinja
# Observability (the stack runs in all environments). Grafana admin password (prod/staging);
# alert-channel secrets — Alertmanager delivers SLO breaches here (each materialized as a mounted
# file on deploy). Configured channels: {{ alert_channels | join(", ") }}.
GRAFANA_ADMIN_PASSWORD=
{% if "webhook" in alert_channels %}APP_ALERT_WEBHOOK_URL=
{% endif %}{% if "slack" in alert_channels %}APP_ALERT_SLACK_API_URL=
{% endif %}{% if "pagerduty" in alert_channels %}APP_ALERT_PAGERDUTY_ROUTING_KEY=
{% endif %}{% if "email" in alert_channels %}APP_ALERT_SMTP_SMARTHOST=
APP_ALERT_SMTP_FROM=
APP_ALERT_SMTP_TO=
APP_ALERT_SMTP_AUTH_USERNAME=
APP_ALERT_SMTP_AUTH_PASSWORD=
{% endif %}# FRAMEWORK:END
```

> The `.env.example` is a HYBRID integrity file; its section checksum is already answer-dependent (8b), so the manifest naturally records the per-channel variant. The default `["webhook"]` keeps exactly `APP_ALERT_WEBHOOK_URL=` (verify byte-equivalence of the managed section in step 4).

- [ ] **Step 4: Run tests + verify the default managed section is unchanged**

Run: `uv run pytest tests/test_copier_runner.py -k env_example -q`
Expected: PASS.

Also confirm the existing `.env.example` render test (if it asserts on the managed section) still passes:
Run: `uv run pytest tests/test_copier_runner.py -k env -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/framework_cli/template/.env.example.jinja tests/test_copier_runner.py
git commit -m "feat(wizard): per-channel alert secrets in .env.example managed section"
```

---

## Task 7: #1 secrets-present deploy precondition

**Files:**
- Create: `src/framework_cli/template/infra/deploy/check_alert_secrets.sh.jinja`
- Modify: `src/framework_cli/template/infra/deploy/strategy.sh`
- Modify: `src/framework_cli/integrity/classes.py`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_copier_runner.py`:

```python
import subprocess


def _run_precondition(dest: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(dest / "infra/deploy/check_alert_secrets.sh")],
        env={"PATH": os.environ["PATH"], **env},
        capture_output=True,
        text=True,
    )


def test_alert_precondition_fails_when_secret_missing(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "alert_channels": ["slack"]})
    result = _run_precondition(dest, {})  # APP_ALERT_SLACK_API_URL unset
    assert result.returncode == 1
    assert "APP_ALERT_SLACK_API_URL" in result.stderr


def test_alert_precondition_passes_when_secret_present(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA, "alert_channels": ["slack"]})
    result = _run_precondition(dest, {"APP_ALERT_SLACK_API_URL": "https://hooks.example/x"})
    assert result.returncode == 0, result.stderr


def test_alert_precondition_default_checks_webhook(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    assert _run_precondition(dest, {}).returncode == 1  # webhook url missing
    assert _run_precondition(dest, {"APP_ALERT_WEBHOOK_URL": "https://x"}).returncode == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py -k alert_precondition -q`
Expected: FAIL — the script does not exist.

- [ ] **Step 3: Create the precondition script (templated)**

Create `src/framework_cli/template/infra/deploy/check_alert_secrets.sh.jinja`:

```jinja
#!/usr/bin/env bash
# Alert-secrets precondition (framework spec §8 / 8f-w). FAILS the deploy if any configured alert
# channel is missing its connection secret(s) — killing the silent no-op where Alertmanager loads
# fine but never delivers. Configured channels: {{ alert_channels | join(", ") }}.
# Called by infra/deploy/strategy.sh before placing the image.
set -euo pipefail

_missing=0
require_nonempty() {
  if [ -z "${!1:-}" ]; then
    echo "::error::alert secret '${1}' is empty — a configured channel cannot deliver." >&2
    _missing=1
  fi
}

{% if "webhook" in alert_channels %}require_nonempty APP_ALERT_WEBHOOK_URL
{% endif %}{% if "slack" in alert_channels %}require_nonempty APP_ALERT_SLACK_API_URL
{% endif %}{% if "pagerduty" in alert_channels %}require_nonempty APP_ALERT_PAGERDUTY_ROUTING_KEY
{% endif %}{% if "email" in alert_channels %}require_nonempty APP_ALERT_SMTP_SMARTHOST
require_nonempty APP_ALERT_SMTP_FROM
require_nonempty APP_ALERT_SMTP_TO
require_nonempty APP_ALERT_SMTP_AUTH_PASSWORD
{% endif %}
if [ "${_missing}" -ne 0 ]; then
  echo "::error::alert-secrets precondition failed — set the secrets above (.env.example / infra/deploy/README.md)." >&2
  exit 1
fi
echo "alert-secrets: all configured channels have their secrets."
```

- [ ] **Step 4: Call it from `strategy.sh` `deploy()`**

In `src/framework_cli/template/infra/deploy/strategy.sh`, add the precondition as the first line of `deploy()` (after `require_var DEPLOY_ENV`):

```bash
deploy() {
  require_var APP_IMAGE
  require_var DEPLOY_ENV
  # Kill the silent no-op: refuse to deploy if a configured alert channel lacks its secret.
  bash "$(dirname "$0")/check_alert_secrets.sh"
  # Record BEFORE placing so a rollback target is tracked even if this deploy fails midway.
  local rev
  rev="$(repo_head_revision)"
  __target_record_release "${APP_IMAGE}" "${rev}"
  # shellcheck disable=SC2317  # reached once __target_record_release is implemented (not the _todo stub)
  __target_place_image   # the image entrypoint runs `alembic upgrade head` on start
}
```

- [ ] **Step 5: Register the new LOCKED file**

In `src/framework_cli/integrity/classes.py`, add to `LOCKED_TRACKED` (after `"infra/deploy/strategy.sh"`):

```python
    "infra/deploy/check_alert_secrets.sh",
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_copier_runner.py -k alert_precondition -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/framework_cli/template/infra/deploy/check_alert_secrets.sh.jinja \
        src/framework_cli/template/infra/deploy/strategy.sh \
        src/framework_cli/integrity/classes.py tests/test_copier_runner.py
git commit -m "feat(wizard): #1 secrets-present deploy precondition (kills the silent no-op)"
```

---

## Task 8: Always-on `AlertmanagerNotificationsFailing` meta-alert

**Files:**
- Create: `src/framework_cli/template/infra/observability/prometheus/alerts/alertmanager_alerts.yml`
- Modify: `src/framework_cli/integrity/classes.py`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_copier_runner.py`:

```python
def test_alertmanager_meta_alert_present_always(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})  # no batteries, default channels
    rule = dest / "infra/observability/prometheus/alerts/alertmanager_alerts.yml"
    assert rule.is_file()
    parsed = yaml.safe_load(rule.read_text())
    names = {r["alert"] for g in parsed["groups"] for r in g["rules"]}
    assert "AlertmanagerNotificationsFailing" in names
    assert "alertmanager_notifications_failed_total" in rule.read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py -k meta_alert -q`
Expected: FAIL — file missing.

- [ ] **Step 3: Create the alert rule (static, always-on)**

Create `src/framework_cli/template/infra/observability/prometheus/alerts/alertmanager_alerts.yml`:

```yaml
groups:
  - name: alertmanager
    rules:
      # Meta-monitoring: Alertmanager itself is failing to deliver notifications to a receiver.
      # This is the steady-state guard against the silent no-op — if delivery breaks, this fires
      # (visible in Grafana even if the broken channel is the one that would have paged you).
      - alert: AlertmanagerNotificationsFailing
        expr: rate(alertmanager_notifications_failed_total[5m]) > 0
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Alertmanager failing to deliver notifications"
          description: "Integration {{ $labels.integration }} has failed deliveries over the last 10m — alerts may be silently lost."
```

> This file is plain YAML (no Jinja). The `{{ $labels.integration }}` is Prometheus templating, not Jinja — but because Copier only templates `*.jinja` files, this static `.yml` is copied verbatim and the braces are safe.

- [ ] **Step 4: Register the new LOCKED file**

In `src/framework_cli/integrity/classes.py`, add to `LOCKED_TRACKED` (after `"infra/observability/prometheus/alerts/postgres_alerts.yml"`):

```python
    "infra/observability/prometheus/alerts/alertmanager_alerts.yml",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_copier_runner.py -k meta_alert -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/template/infra/observability/prometheus/alerts/alertmanager_alerts.yml \
        src/framework_cli/integrity/classes.py tests/test_copier_runner.py
git commit -m "feat(wizard): always-on AlertmanagerNotificationsFailing meta-alert"
```

---

## Task 9: #3 advisory delivery smoke at deploy

**Files:**
- Create: `src/framework_cli/template/infra/deploy/alert_smoke.sh`
- Modify: `src/framework_cli/template/infra/deploy/strategy.sh`
- Modify: `src/framework_cli/template/.github/workflows/deploy-staging.yml`, `deploy-prod.yml`
- Modify: `src/framework_cli/integrity/classes.py`
- Test: `tests/test_copier_runner.py`

- [ ] **Step 1: Write the failing test (run the rendered script against a fake Alertmanager)**

Append to `tests/test_copier_runner.py`:

```python
import http.server
import threading


class _FakeAM(http.server.BaseHTTPRequestHandler):
    failed_total = 0.0  # class-level, set per test

    def log_message(self, *a):  # silence
        pass

    def do_POST(self):  # /api/v2/alerts
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self.send_response(200)
        self.end_headers()

    def do_GET(self):  # /metrics
        body = (
            'alertmanager_notifications_failed_total{integration="webhook"} '
            f"{self.failed_total}\n"
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(body)


def _serve_fake_am(failed_total: float):
    _FakeAM.failed_total = failed_total
    srv = http.server.HTTPServer(("127.0.0.1", 0), _FakeAM)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _run_smoke(dest: Path, am_url: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(dest / "infra/deploy/alert_smoke.sh")],
        env={"PATH": os.environ["PATH"], "ALERTMANAGER_URL": am_url, "SMOKE_WAIT": "1"},
        capture_output=True,
        text=True,
    )


def test_alert_smoke_reports_failure_but_exits_zero(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    srv = _serve_fake_am(failed_total=3.0)  # non-zero failures present
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        result = _run_smoke(dest, url)
    finally:
        srv.shutdown()
    assert result.returncode == 0  # advisory — never fails the deploy
    assert "delivery" in (result.stdout + result.stderr).lower()


def test_alert_smoke_clean_when_no_failures(tmp_path: Path):
    dest = tmp_path / "demo"
    render_project(dest, {**DATA})
    srv = _serve_fake_am(failed_total=0.0)
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        result = _run_smoke(dest, url)
    finally:
        srv.shutdown()
    assert result.returncode == 0
    assert "ok" in (result.stdout + result.stderr).lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_copier_runner.py -k alert_smoke -q`
Expected: FAIL — script missing.

- [ ] **Step 3: Create the smoke script (static, advisory)**

Create `src/framework_cli/template/infra/deploy/alert_smoke.sh`:

```bash
#!/usr/bin/env bash
# Alert delivery smoke (8f-w / #3). Fires a synthetic, auto-resolved test alert into Alertmanager,
# then checks Alertmanager's own notification-failure counter. ADVISORY: it ALWAYS exits 0 — a
# third-party blip must never fail your deploy or trigger a rollback. Point ALERTMANAGER_URL at
# your deploy's Alertmanager (default localhost:9093). Called from the CD workflows (advisory step).
set -uo pipefail

AM_URL="${ALERTMANAGER_URL:-http://localhost:9093}"
WAIT="${SMOKE_WAIT:-5}"

failed_total() {
  curl -fsS "${AM_URL}/metrics" 2>/dev/null \
    | awk '/^alertmanager_notifications_failed_total/ {s+=$NF} END {printf "%d", s+0}'
}

before="$(failed_total)"

# Fire a synthetic, clearly-labeled alert that ends 2s out (auto-resolves; never pages).
end="$(date -u -d '+2 seconds' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)"
curl -fsS -X POST "${AM_URL}/api/v2/alerts" -H 'Content-Type: application/json' \
  --data "[{\"labels\":{\"alertname\":\"DeploySmokeTest\",\"severity\":\"info\"},\"endsAt\":\"${end}\"}]" \
  >/dev/null 2>&1 || { echo "[alert-smoke] could not reach Alertmanager at ${AM_URL} — skipping (advisory)."; exit 0; }

sleep "${WAIT}"
after="$(failed_total)"

if [ "${after}" -gt "${before}" ]; then
  echo "::warning::[alert-smoke] Alertmanager notification failures increased (${before}->${after}) — a configured channel may be misconfigured. Advisory only." >&2
else
  echo "[alert-smoke] ok — no new notification failures (${before}->${after})."
fi
exit 0
```

- [ ] **Step 4: Add the `alert-smoke` operation to `strategy.sh`**

In `src/framework_cli/template/infra/deploy/strategy.sh`, add a case to the `operation` switch (before the `*)` default):

```bash
  alert-smoke)     bash "$(dirname "$0")/alert_smoke.sh" ;;
```

And add `alert-smoke` to the "Valid:" usage line in the `*)` branch.

- [ ] **Step 5: Wire an advisory smoke step into the CD workflows**

In `src/framework_cli/template/.github/workflows/deploy-staging.yml`, add after the "await healthy" step (before Phase 1):

```yaml
      - name: alert delivery smoke (advisory)
        continue-on-error: true
        run: bash infra/deploy/strategy.sh alert-smoke
```

Do the same in `deploy-prod.yml` after its await-healthy / before its smoke phase.

- [ ] **Step 6: Register the new LOCKED file**

In `src/framework_cli/integrity/classes.py`, add to `LOCKED_TRACKED` (after the `check_alert_secrets.sh` entry):

```python
    "infra/deploy/alert_smoke.sh",
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_copier_runner.py -k alert_smoke -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/framework_cli/template/infra/deploy/alert_smoke.sh \
        src/framework_cli/template/infra/deploy/strategy.sh \
        src/framework_cli/template/.github/workflows/deploy-staging.yml \
        src/framework_cli/template/.github/workflows/deploy-prod.yml \
        src/framework_cli/integrity/classes.py tests/test_copier_runner.py
git commit -m "feat(wizard): #3 advisory alert delivery smoke at deploy"
```

---

## Task 10: `framework upskill --alerts` reconfigure

**Files:**
- Modify: `src/framework_cli/upskill.py:37-66`
- Modify: `src/framework_cli/cli.py` (the `upskill` command, ~127-163)
- Test: `tests/test_upskill.py` (or the file holding upskill tests)

- [ ] **Step 1: Write the failing test**

Append to the upskill test module (find it with `grep -rl upskill_project tests/`; if none, create `tests/test_upskill.py`):

```python
from pathlib import Path

from framework_cli import upskill as up


def test_upskill_records_alert_channels(monkeypatch, tmp_path: Path):
    project = tmp_path / "demo"
    project.mkdir()
    (project / ".copier-answers.yml").write_text(
        "_src_path: gh:x\n_commit: v0.1.0\nbatteries: []\nalert_channels:\n- webhook\n"
    )
    calls = {}

    monkeypatch.setattr(up, "_is_git_tracked", lambda p: True)
    monkeypatch.setattr(up, "run_update", lambda *a, **k: calls.update(data=k.get("data")))
    monkeypatch.setattr(
        up.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0})()
    )

    up.upskill_project(project, alert_channels=["slack", "email"])

    assert calls["data"]["alert_channels"] == ["slack", "email"]
    answers = (project / ".copier-answers.yml").read_text()
    assert "alert_channels:\n- slack\n- email\n" in answers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_upskill.py -q`
Expected: FAIL — `upskill_project()` has no `alert_channels` parameter.

- [ ] **Step 3: Thread `alert_channels` through `upskill_project`**

In `src/framework_cli/upskill.py`, update the signature + body:

```python
def upskill_project(
    project: Path,
    vcs_ref: str | None = None,
    with_batteries: list[str] | None = None,
    alert_channels: list[str] | None = None,
) -> bool:
    from framework_cli.source import (
        read_alert_channels,
        read_batteries,
        record_alert_channels,
        record_batteries,
    )

    if not _is_git_tracked(project):
        raise UpskillError(
            "upskill requires a git-tracked project (run `git init` and commit first)"
        )
    effective = (
        with_batteries if with_batteries is not None else read_batteries(project)
    )
    channels = (
        alert_channels if alert_channels is not None else read_alert_channels(project)
    )
    from framework_cli.migrations import migration_context

    run_update(
        str(project),
        defaults=True,
        overwrite=True,
        quiet=True,
        vcs_ref=vcs_ref,
        data={
            "batteries": effective,
            "alert_channels": channels,
            **migration_context(effective),
        },
    )
    record_batteries(project, effective)
    record_alert_channels(project, channels)
    if (project / ".framework" / "integrity.lock").is_file():
        write_manifest(project, installed_framework_version())
    try:
        test = subprocess.run(["task", "test"], cwd=project, check=False)
    except FileNotFoundError as exc:
        raise UpskillError(
            "`task` (go-task) not found on PATH — install it to run the project's tests"
        ) from exc
    return test.returncode == 0
```

- [ ] **Step 4: Add `--alerts` to the CLI `upskill` command**

In `src/framework_cli/cli.py`, update the `upskill` command. Add the option and parse it via the wizard's `parse_channels`/`_split_alerts`:

```python
@app.command()
def upskill(
    name: str = typer.Argument(..., help="Path to the project to upskill."),
    with_: list[str] = typer.Option(
        [], "--with", help="Add a battery to the project (repeatable)."
    ),
    alerts: str = typer.Option(
        None, "--alerts", help="Reconfigure alert channels (comma-separated; replaces the set)."
    ),
) -> None:
    """Update a project to a newer framework version, then run its tests."""
    from framework_cli.source import read_batteries
    from framework_cli.wizard import _split_alerts, parse_channels

    project = Path(name)
    if not project.is_dir():
        typer.echo(f"Error: {name} is not a directory", err=True)
        raise typer.Exit(1)

    with_batteries = None
    if with_:
        try:
            with_batteries = resolve_batteries([*read_batteries(project), *with_])
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc

    channels = None
    if alerts is not None:
        try:
            channels = parse_channels(_split_alerts(alerts))
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(1) from exc

    try:
        green = upskill_project(
            project, with_batteries=with_batteries, alert_channels=channels
        )
    except UpskillError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    if green:
        typer.echo(f"Upskilled {name}; tests pass.")
    else:
        typer.echo(
            f"Upskilled {name}, but `task test` failed — resolve any Copier conflict markers "
            "and fix failures before committing.",
            err=True,
        )
        raise typer.Exit(1)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_upskill.py tests/test_cli.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/framework_cli/upskill.py src/framework_cli/cli.py tests/test_upskill.py
git commit -m "feat(wizard): framework upskill --alerts reconfigure (set-replacement)"
```

---

## Task 11: Integrity across channel combos + acceptance + docs/state

**Files:**
- Test: `tests/test_copier_runner.py` (integrity combos), `tests/acceptance/test_rendered_project.py` (amtool config-valid)
- Modify: `src/framework_cli/template/infra/deploy/README.md` (document the channels + secrets + smoke)
- Modify: `CLAUDE.md` (Current State), `docs/superpowers/plans/2026-05-20-meta-plan.md` (status row)

- [ ] **Step 1: Write the integrity-combo test**

Append to `tests/test_copier_runner.py` (mirror the existing `framework integrity --ci` combo tests; adapt the helper name to whatever that file uses — search for `integrity` there):

```python
def test_integrity_green_across_alert_channel_combos(tmp_path: Path):
    from framework_cli.integrity.checker import check
    from framework_cli.integrity.generate import write_manifest

    for i, channels in enumerate(
        [["webhook"], ["slack"], ["email", "pagerduty"], ["webhook", "slack", "email", "pagerduty"]]
    ):
        dest = tmp_path / f"demo{i}"
        render_project(dest, {**DATA, "alert_channels": channels})
        write_manifest(dest, "0.1.0")
        findings = check(dest, ci=True)
        assert not [f for f in findings if f.fatal], (channels, findings)
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/test_copier_runner.py -k alert_channel_combos -q`
Expected: PASS (the manifest is generated from each render, so each variant self-verifies).

- [ ] **Step 3: Add an acceptance config-validity check**

In `tests/acceptance/test_rendered_project.py`, add a Docker-gated test that validates the rendered `alertmanager.yml` with `amtool` for a multi-channel render (follow the file's existing `_docker_available()` skip + render helpers):

```python
def test_alertmanager_config_valid_multichannel(tmp_path):
    # renders slack+email+pagerduty and validates with amtool inside the alertmanager image
    dest = _render(tmp_path, {**_BASE_DATA, "alert_channels": ["slack", "email", "pagerduty"]})
    cfg = dest / "infra/observability/alertmanager/alertmanager.yml"
    result = subprocess.run(
        [
            "docker", "run", "--rm", "-v", f"{cfg}:/cfg.yml:ro",
            "--entrypoint", "amtool", "prom/alertmanager:v0.27.0",
            "check-config", "/cfg.yml",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
```

> Adapt `_render` / `_BASE_DATA` to the helpers already in that file. If `amtool check-config` rejects the `${VAR}` placeholders in `email_configs`, set dummy values via a rendered env or assert on `docker compose config` instead — note this in the task if encountered.

- [ ] **Step 4: Run the quality gate (no Docker tier)**

Run: `uv run pytest -q --ignore=tests/acceptance && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv lock --check`
Expected: all green. (Run the acceptance tier separately if Docker is available; clean `/tmp/pytest-of-*` afterward.)

- [ ] **Step 5: Document the channels in the deploy README**

In `src/framework_cli/template/infra/deploy/README.md`, add a short "Alert channels" subsection: the configured channels come from `framework new`/`upskill --alerts`; each needs its `APP_ALERT_*` secret materialized as a mounted file at `/etc/alertmanager/<name>` (`webhook_url`, `slack_api_url`, `smtp_auth_password`, `pagerduty_routing_key`); the `deploy` op runs `check_alert_secrets.sh` (hard-fail if missing); the CD workflow runs `alert-smoke` (advisory).

- [ ] **Step 6: Update state pointers**

Update `CLAUDE.md` Current State (set "Last updated" to today with tz; mark 8f-w merged-pending) and the meta-plan's 8f-w row to ✅. Stage `CLAUDE.md` before committing (the commit-gate hook requires it).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(wizard): integrity combos + amtool acceptance + deploy README + state"
```

---

## Self-Review Notes

- **Spec coverage:** engine (T2–T4), db-paradigm half (T2/T4), alert recording (T1), receiver model (T5), secrets (T6), #1 precondition (T7), meta-alert (T8), #3 smoke (T9), lifecycle new+upskill (T4/T10), integrity (T11), testing strategy (every task is TDD; acceptance in T11). All spec sections map to a task.
- **Baseline manifest shift** is explicit and intended (T7–T9 add always-on LOCKED files + wiring) — call it out in the final review and the state pointer, precedented by OBS-PROD/SVC-PROD.
- **Type/name consistency:** `run_wizard(with_=, alerts=, interactive=)`, `resolve_needs`, `parse_channels`, `_split_alerts`, `NEED_TO_BATTERY`, `KNOWN_CHANNELS`, `read_alert_channels`/`record_alert_channels`, `upskill_project(…, alert_channels=)` are used identically across tasks.
- **Watch items for the implementer:** (a) the alertmanager `.jinja` whitespace control must reproduce the byte-identical default — verify with the captured string in T5; (b) `amtool check-config` may dislike `${VAR}` in email config (T11 note); (c) `date -u -d '+2 seconds'` is GNU-specific — the script falls back to plain `date -u` on BSD/macos runners.
```
