import json

from framework_cli.review import comment
from framework_cli.review.aggregate import SUMMARY_MARKER


def test_find_sticky_comment_matches_marker():
    comments = [{"id": 1, "body": "hello"}, {"id": 9, "body": f"x {SUMMARY_MARKER} y"}]
    assert comment.find_sticky_comment(comments) == 9


def test_find_sticky_comment_returns_none_when_absent():
    assert comment.find_sticky_comment([{"id": 1, "body": "nope"}]) is None


def test_post_sticky_updates_existing(monkeypatch):
    calls = []

    def fake_gh(args, *, token, stdin=None):
        calls.append(args)
        if "--method" not in args:  # the list call
            return json.dumps([{"id": 7, "body": SUMMARY_MARKER}])
        return ""

    monkeypatch.setattr(comment, "_gh_api", fake_gh)
    comment.post_sticky_comment("md", repo="o/r", pr="3", token="t")
    assert any("--method" in a and "PATCH" in a and "comments/7" in a[0] for a in calls)
    list_call = next(a for a in calls if "--method" not in a)
    assert "--paginate" in list_call


def test_post_sticky_creates_when_absent(monkeypatch):
    calls = []

    def fake_gh(args, *, token, stdin=None):
        calls.append(args)
        if "--method" not in args:
            return json.dumps([])
        return ""

    monkeypatch.setattr(comment, "_gh_api", fake_gh)
    comment.post_sticky_comment("md", repo="o/r", pr="3", token="t")
    assert any(
        "--method" in a and "POST" in a and a[0] == "repos/o/r/issues/3/comments"
        for a in calls
    )
    list_call = next(a for a in calls if "--method" not in a)
    assert "--paginate" in list_call


def test_post_sticky_handles_empty_list_response(monkeypatch):
    calls = []

    def fake_gh(args, *, token, stdin=None):
        calls.append(args)
        if "--method" not in args:
            return ""  # gh returned nothing for the list call
        return ""

    monkeypatch.setattr(comment, "_gh_api", fake_gh)
    comment.post_sticky_comment("md", repo="o/r", pr="3", token="t")
    # empty list → no existing sticky → a POST (create) is issued
    assert any("--method" in a and "POST" in a for a in calls)


def test_post_sticky_never_raises(monkeypatch):
    def boom(args, *, token, stdin=None):
        raise RuntimeError("gh down")

    monkeypatch.setattr(comment, "_gh_api", boom)
    comment.post_sticky_comment("md", repo="o/r", pr="3", token="t")  # must not raise
