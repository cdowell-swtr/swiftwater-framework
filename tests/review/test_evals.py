import json
from pathlib import Path


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_load_fixtures_discovers_bad_and_good(tmp_path):
    from framework_cli.review.evals import load_fixtures

    _write(tmp_path / "security" / "bad" / "sqli.diff", "+++ b/app.py\n")
    _write(tmp_path / "security" / "bad" / "sqli.expect.json", json.dumps({"file": "app.py"}))
    _write(tmp_path / "security" / "good" / "ok.diff", "+++ b/app.py\n")

    fx = load_fixtures(tmp_path)
    assert [(f.agent, f.kind, f.name, f.seeded_file) for f in fx] == [
        ("security", "bad", "sqli", "app.py"),
        ("security", "good", "ok", None),
    ]


def test_load_fixtures_skips_bad_without_valid_sidecar(tmp_path):
    from framework_cli.review.evals import load_fixtures

    _write(tmp_path / "security" / "bad" / "no-sidecar.diff", "+++ b/app.py\n")  # no .expect.json
    _write(tmp_path / "security" / "bad" / "bad-json.diff", "+++ b/app.py\n")
    _write(tmp_path / "security" / "bad" / "bad-json.expect.json", "{ not json")

    assert load_fixtures(tmp_path) == []  # both bad fixtures skipped, no good fixtures


def test_load_fixtures_ignores_non_dir_entries(tmp_path):
    from framework_cli.review.evals import load_fixtures

    _write(tmp_path / "thresholds.yaml", "security: {recall_min: 0.5, fp_max: 0.5}\n")
    assert load_fixtures(tmp_path) == []
