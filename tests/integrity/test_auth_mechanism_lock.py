"""The multitenantauth MECHANISM tree ships integrity-LOCKED (the de-fork colonization guard);
the authz POLICY files (permissions.py, roles.py) ship consumer-editable (unlocked).

This is the framework's deliberate exception to FWK7's builder-owned-`src/` rule: the auth
*mechanism* is framework-owned security infrastructure that happens to live under `src/`. The
completeness test below is the fail-safe net — a new mechanism file under the tree that is NOT
enumerated in `BATTERY_LOCKED_SRC` fails here, so a forgotten lock is caught (it does not silently
ship unlocked). Mirrors the FWK7 reverse-coverage idiom for infra files.
"""

from pathlib import Path

from framework_cli.copier_runner import render_project
from framework_cli.integrity.checker import check
from framework_cli.integrity.generate import build_manifest, write_manifest
from framework_cli.integrity.manifest import installed_framework_version
from framework_cli.integrity.restore import restore_file
from framework_cli.source import record_portable_source

_PKG = "demo"
_MECHANISM_TREES = (
    f"src/{_PKG}/multitenantauth",
    f"src/{_PKG}/db/control",
    "migrations_control",
)
# The two POLICY files within the tree that ship UNLOCKED (the consumer-editable RBAC catalog).
_POLICY_UNLOCKED = {
    f"src/{_PKG}/multitenantauth/authz/permissions.py",
    f"src/{_PKG}/multitenantauth/authz/roles.py",
}


def _render(tmp_path: Path) -> Path:
    dest = tmp_path / "demo"
    render_project(
        dest,
        {
            "project_name": "Demo",
            "project_slug": "demo",
            "package_name": _PKG,
            "python_version": "3.12",
            "batteries": ["multitenantauth"],
        },
    )
    return dest


def _walk_tree_files(project: Path) -> set[str]:
    """Every source file (.py/.mako) under the mechanism trees, project-relative."""
    found: set[str] = set()
    for tree in _MECHANISM_TREES:
        for f in (project / tree).rglob("*"):
            if (
                f.is_file()
                and f.suffix in {".py", ".mako"}
                and "__pycache__" not in f.parts
            ):
                found.add(f.relative_to(project).as_posix())
    return found


def test_every_mechanism_file_is_locked_except_policy(tmp_path: Path):
    proj = _render(tmp_path)
    manifest = build_manifest(proj, installed_framework_version())
    locked = {
        e.path for e in manifest.entries if e.cls == "locked" and e.tier == "tracked"
    }

    tree_files = _walk_tree_files(proj)
    assert tree_files, "render produced no mechanism-tree files — render/paths changed?"

    # Fail-SAFE completeness: every mechanism file except the policy files must be locked.
    missing = sorted((tree_files - _POLICY_UNLOCKED) - locked)
    assert not missing, (
        "multitenantauth mechanism files are NOT integrity-locked (enumerate them in "
        f"BATTERY_LOCKED_SRC in integrity/classes.py): {missing}"
    )

    # The POLICY files must NOT be locked — they ship consumer-editable.
    wrongly_locked = sorted(_POLICY_UNLOCKED & locked)
    assert not wrongly_locked, (
        f"authz POLICY files must ship UNLOCKED but are locked: {wrongly_locked}"
    )


def test_alembic_control_ini_is_locked(tmp_path: Path):
    proj = _render(tmp_path)
    manifest = build_manifest(proj, installed_framework_version())
    locked = {e.path for e in manifest.entries if e.cls == "locked"}
    assert "alembic_control.ini" in locked


def test_no_mechanism_lock_without_the_battery(tmp_path: Path):
    """A baseline (no multitenantauth) render locks none of the auth tree."""
    dest = tmp_path / "base"
    render_project(
        dest,
        {
            "project_name": "Base",
            "project_slug": "base",
            "package_name": "base",
            "python_version": "3.12",
        },
    )
    manifest = build_manifest(dest, installed_framework_version())
    assert not [e for e in manifest.entries if "multitenantauth" in e.path]
    assert not [e for e in manifest.entries if e.path == "alembic_control.ini"]


def _new_auth_project(tmp_path: Path) -> Path:
    """Render a multitenantauth project with the manifest written and `_commit` recorded — the
    realistic `framework new` state so restore's FWK34 version-sync guard sees an in-sync project.
    """
    proj = _render(tmp_path)
    write_manifest(proj, installed_framework_version())
    record_portable_source(proj, installed_framework_version())
    return proj


def test_tampering_a_mechanism_file_is_caught_and_restorable(tmp_path: Path):
    proj = _new_auth_project(tmp_path)
    rel = f"src/{_PKG}/multitenantauth/authz/expr.py"  # the permission evaluator (mechanism)
    target = proj / rel
    canonical = target.read_text()

    # A fresh render verifies clean ...
    assert check(proj, ci=True) == []
    # ... tampering the locked evaluator is a fatal finding ...
    target.write_text(canonical + "\n# sneaky edit\n")
    assert any(f.path == rel and f.fatal for f in check(proj))
    # ... and restore returns it to canonical, clean again.
    restore_file(proj, rel)
    assert target.read_text() == canonical
    assert check(proj, ci=True) == []


def test_editing_a_policy_file_is_not_flagged(tmp_path: Path):
    """The authz POLICY catalog ships UNLOCKED — editing it must NOT trip integrity."""
    proj = _new_auth_project(tmp_path)
    rel = f"src/{_PKG}/multitenantauth/authz/permissions.py"
    (proj / rel).write_text(
        (proj / rel).read_text() + "\n# consumer adds a permission\n"
    )
    assert not any(f.path == rel for f in check(proj))
    assert check(proj, ci=True) == []
