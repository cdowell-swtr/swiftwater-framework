from pathlib import Path

from framework_cli.review.agentic import _run_tool, run_agent_agentic
from framework_cli.review.decisions import Decision
from framework_cli.review.findings import Finding
from framework_cli.review.registry import get_agent


def _tree(root: Path) -> None:
    (root / "pkg").mkdir()
    (root / "pkg" / "a.py").write_text("import os\nSECRET = 'x'\n")
    (root / "pkg" / "b.py").write_text("from pkg.a import SECRET\n")
    (root / "README.md").write_text("# Demo\n")


def test_read_file_returns_contents(tmp_path):
    _tree(tmp_path)
    out = _run_tool("read_file", {"path": "pkg/a.py"}, tmp_path)
    assert "SECRET = 'x'" in out


def test_read_file_rejects_escape(tmp_path):
    _tree(tmp_path)
    assert "error" in _run_tool("read_file", {"path": "../secrets"}, tmp_path).lower()
    assert "error" in _run_tool("read_file", {"path": "/etc/passwd"}, tmp_path).lower()


def test_read_file_truncates_large_file(tmp_path):
    _tree(tmp_path)
    (tmp_path / "big.py").write_text("x = 1\n" * 20000)  # > 50k chars
    out = _run_tool("read_file", {"path": "big.py"}, tmp_path)
    assert "[truncated]" in out
    assert len(out) < 60_000


def test_grep_finds_matches_with_location(tmp_path):
    _tree(tmp_path)
    out = _run_tool("grep", {"pattern": "SECRET"}, tmp_path)
    assert "pkg/a.py:2:" in out
    assert "pkg/b.py:1:" in out


def test_grep_bad_regex_returns_error(tmp_path):
    _tree(tmp_path)
    assert "error" in _run_tool("grep", {"pattern": "["}, tmp_path).lower()


def test_glob_lists_paths(tmp_path):
    _tree(tmp_path)
    out = _run_tool("glob", {"pattern": "pkg/*.py"}, tmp_path)
    assert "pkg/a.py" in out
    assert "pkg/b.py" in out
    assert "README.md" not in out


def test_unknown_tool_and_missing_arg_return_error(tmp_path):
    assert "error" in _run_tool("nope", {}, tmp_path).lower()
    assert "error" in _run_tool("read_file", {}, tmp_path).lower()  # missing 'path'


def test_glob_does_not_escape_root(tmp_path):
    # A sibling file outside the project root must never be surfaced.
    root = tmp_path / "proj"
    root.mkdir()
    (root / "inside.py").write_text("x = 1\n")
    (tmp_path / "outside-secret.txt").write_text("TOP SECRET\n")
    out = _run_tool("glob", {"pattern": "../*"}, root)
    assert "outside-secret" not in out
    assert "TOP SECRET" not in out
    # An absolute / non-relative pattern is rejected with an error, not a crash.
    assert "error" in _run_tool("glob", {"pattern": "/etc/*"}, root).lower()


def test_grep_does_not_escape_root_via_path_glob(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "inside.py").write_text("hello = 1\n")
    (tmp_path / "outside-secret.txt").write_text("TOP SECRET CREDENTIALS\n")
    out = _run_tool(
        "grep", {"pattern": "SECRET|CREDENTIALS", "path_glob": "../*"}, root
    )
    assert "TOP SECRET" not in out
    assert "outside-secret" not in out


def test_tools_work_on_a_real_rendered_project(tmp_path):
    from framework_cli.copier_runner import render_project

    root = tmp_path / "demo"
    render_project(
        root,
        {
            "project_name": "Demo",
            "project_slug": "demo",
            "package_name": "demo",
            "python_version": "3.12",
            "batteries": [],
        },
    )
    # Plant a .git dir like realize_fixture / a checked-out repo would have, so the
    # skip behavior is exercised against a real tree.
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("[core]\n")

    listing = _run_tool("glob", {"pattern": "src/demo/routes/*.py"}, root)
    assert "src/demo/routes/items.py" in listing
    contents = _run_tool("read_file", {"path": "src/demo/routes/items.py"}, root)
    assert "router" in contents.lower()
    matches = _run_tool(
        "grep", {"pattern": "APIRouter", "path_glob": "src/demo/**/*.py"}, root
    )
    assert "items.py" in matches
    # The .git directory and its contents are skipped — assert on path COMPONENTS, not a
    # substring (a sibling like .gitignore contains ".git" but must NOT be skipped).
    all_paths = _run_tool("glob", {"pattern": "**/*"}, root).splitlines()
    assert not any(p == ".git" or p.startswith(".git/") for p in all_paths)
    # And grep does not surface the planted .git/config contents.
    assert ".git/config" not in _run_tool("grep", {"pattern": "core"}, root)


class _ToolUse:
    type = "tool_use"

    def __init__(self, id, name, input):
        self.id, self.name, self.input = id, name, input


class _TextBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Resp:
    def __init__(self, content):
        self.content = content


class _ScriptedClient:
    """Returns the queued responses in order; records each create() kwargs."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


def test_agentic_loop_runs_tools_then_returns_findings(tmp_path):
    (tmp_path / "x.py").write_text("BAD = 1\n")
    client = _ScriptedClient(
        [
            _Resp([_ToolUse("t1", "glob", {"pattern": "*.py"})]),
            _Resp([_ToolUse("t2", "read_file", {"path": "x.py"})]),
            _Resp(
                [
                    _TextBlock(
                        '[{"path": "x.py", "line": 1, "severity": "high", "message": "bad"}]'
                    )
                ]
            ),
        ]
    )
    findings = run_agent_agentic(
        "--- a/x.py\n+++ b/x.py\n",
        tmp_path,
        get_agent("architecture"),
        client,
        max_turns=12,
    )
    assert findings == [Finding("x.py", 1, "high", "bad")]
    assert len(client.calls) == 3
    assert client.calls[0]["system"][0]["text"].startswith("Review this unified diff:")
    assert client.calls[0]["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert [t["name"] for t in client.calls[0]["tools"]] == [
        "read_file",
        "grep",
        "glob",
    ]
    assert any(
        msg["role"] == "user"
        and isinstance(msg["content"], list)
        and any(
            isinstance(b, dict) and b.get("type") == "tool_result"
            for b in msg["content"]
        )
        for msg in client.calls[2]["messages"]
    )


class _AlwaysToolClient:
    """Always asks for a tool, until create() is called without a `tools` kwarg (the
    finalize call), at which point it returns findings."""

    def __init__(self):
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if "tools" not in kwargs:  # the finalize call
            return _Resp(
                [
                    _TextBlock(
                        '[{"path": "x.py", "line": 1, "severity": "high", "message": "late"}]'
                    )
                ]
            )
        return _Resp([_ToolUse(f"t{len(self.calls)}", "glob", {"pattern": "*"})])


def test_agentic_loop_finalizes_at_turn_cap(tmp_path):
    (tmp_path / "x.py").write_text("Y = 1\n")
    client = _AlwaysToolClient()
    findings = run_agent_agentic(
        "--- a/x.py\n+++ b/x.py\n",
        tmp_path,
        get_agent("architecture"),
        client,
        max_turns=3,
    )
    # 3 tool rounds (each WITH tools) + 1 finalize (WITHOUT tools) = 4 calls.
    assert len(client.calls) == 4
    assert all("tools" in c for c in client.calls[:3])
    assert "tools" not in client.calls[3]
    # Still returns a (partial) findings list, never hangs or raises.
    assert findings == [Finding("x.py", 1, "high", "late")]


def _make_decision() -> Decision:
    return Decision(
        id="DEC-1",
        status="accepted",
        agents=("architecture",),
        concern="c",
        premise="p",
        body="b",
        source="DEC-1.md",
    )


def test_agentic_decisions_block_inserted_before_prompt(tmp_path):
    """A non-empty decisions tuple injects a decisions block immediately before the prompt."""
    client = _ScriptedClient(
        [
            _Resp([_TextBlock("[]")]),
        ]
    )
    run_agent_agentic(
        "--- a/x.py\n+++ b/x.py\n",
        tmp_path,
        get_agent("architecture"),
        client,
        max_turns=12,
        decisions=(_make_decision(),),
    )
    system = client.calls[0]["system"]
    # diff block + decisions block + prompt block = 3
    assert len(system) == 3
    decisions_block = system[1]
    assert "DEC-1" in decisions_block["text"]
    assert "acknowledged:" in decisions_block["text"]
    assert decisions_block["cache_control"] == {"type": "ephemeral"}
    # Prompt must remain the last block
    assert system[2]["text"] == get_agent("architecture").prompt


def test_agentic_no_decisions_block_when_empty(tmp_path):
    """An empty decisions tuple leaves the system blocks byte-identical to the no-decisions path."""
    client = _ScriptedClient(
        [
            _Resp([_TextBlock("[]")]),
        ]
    )
    run_agent_agentic(
        "--- a/x.py\n+++ b/x.py\n",
        tmp_path,
        get_agent("architecture"),
        client,
        max_turns=12,
    )
    system = client.calls[0]["system"]
    # Must be exactly diff + prompt — no extra block
    assert len(system) == 2
    assert system[0]["text"].startswith("Review this unified diff:")
    assert system[1]["text"] == get_agent("architecture").prompt


def test_cli_dispatches_agentic_strategy(monkeypatch, tmp_path):
    import framework_cli.cli as cli_mod

    called = {}

    def fake_agentic(diff, root, spec, client, *, max_turns, decisions=()):
        called["root"] = root
        called["max_turns"] = max_turns
        return []

    monkeypatch.setattr("framework_cli.review.agentic.run_agent_agentic", fake_agentic)
    monkeypatch.setattr(cli_mod, "default_client", lambda env: object())
    monkeypatch.chdir(tmp_path)
    cli_mod._review_run("--- a/x\n+++ b/x\n", get_agent("architecture"))
    assert called["root"] == tmp_path
    assert (
        called["max_turns"] == 12
    )  # DEFAULT_MAX_TURNS (architecture sets no override)
