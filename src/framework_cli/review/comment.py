from __future__ import annotations

import json
import os
import subprocess

from framework_cli.review.aggregate import SUMMARY_MARKER


def find_sticky_comment(comments: list[dict]) -> int | None:
    """The id of the existing review-summary comment (carrying the marker), if any."""
    for c in comments:
        if SUMMARY_MARKER in c.get("body", ""):
            return int(c["id"])
    return None


def _gh_api(args: list[str], *, token: str, stdin: str | None = None) -> str:
    """Run `gh api <args>`; return stdout. Raises on non-zero (callers swallow)."""
    result = subprocess.run(
        ["gh", "api", *args],
        input=stdin,
        text=True,
        check=True,
        capture_output=True,
        env={**os.environ, "GH_TOKEN": token},
    )
    return result.stdout


def post_sticky_comment(markdown: str, *, repo: str, pr: str, token: str) -> None:
    """Create or update the single review-summary comment on the PR. Never raises."""
    try:
        listed = _gh_api(
            [f"repos/{repo}/issues/{pr}/comments", "--paginate"], token=token
        )
        comments = json.loads(listed) if listed.strip() else []
        existing = find_sticky_comment(comments)
        body = json.dumps({"body": markdown})
        if existing is not None:
            _gh_api(
                [
                    f"repos/{repo}/issues/comments/{existing}",
                    "--method",
                    "PATCH",
                    "--input",
                    "-",
                ],
                token=token,
                stdin=body,
            )
        else:
            _gh_api(
                [
                    f"repos/{repo}/issues/{pr}/comments",
                    "--method",
                    "POST",
                    "--input",
                    "-",
                ],
                token=token,
                stdin=body,
            )
    except Exception:  # noqa: BLE001 - posting failure must not fail the CI job
        pass
