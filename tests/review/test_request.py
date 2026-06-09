from pathlib import Path
from framework_cli.review.context import Bundle
from framework_cli.review.registry import get_agent
from framework_cli.review.request import build_review_request


def test_bundle_request_system_blocks_order_and_cache():
    bundle = Bundle(diff="DIFF", context_files=(("a.py", "CONTENT"),))
    spec = get_agent("security")
    req = build_review_request(bundle, spec, root=Path("/x"))
    assert req.system[0]["text"].startswith("Review this unified diff:")
    assert "DIFF" in req.system[0]["text"]
    assert req.system[0]["cache_control"] == {"type": "ephemeral"}
    assert "CONTENT" in req.system[1]["text"]
    assert req.system[-1]["text"] == spec.prompt
    assert req.user_message == "Return your findings as a JSON array only."
    assert req.tools is None
    assert req.max_turns == 1
