from framework_cli.integrity.sections import section_content, section_sha256, section_span

_DOC = "\n".join(
    [
        "# Title",
        "<!-- FRAMEWORK:BEGIN -->",
        "managed line one",
        "managed line two",
        "<!-- FRAMEWORK:END -->",
        "## Builder notes",
        "builder text",
    ]
)


def test_section_content_is_text_between_markers():
    assert section_content(_DOC) == "managed line one\nmanaged line two"


def test_section_span_is_inclusive_of_marker_lines():
    assert section_span(_DOC) == (1, 4)


def test_section_sha256_is_stable_and_ignores_outside_edits():
    edited = _DOC.replace("builder text", "DIFFERENT builder text")
    assert section_sha256(edited) == section_sha256(_DOC)


def test_section_sha256_changes_when_inside_edited():
    edited = _DOC.replace("managed line one", "managed line ONE")
    assert section_sha256(edited) != section_sha256(_DOC)


def test_missing_markers_return_none():
    assert section_content("no markers here") is None
    assert section_span("no markers here") is None
    assert section_sha256("no markers here") is None


def test_unbalanced_or_out_of_order_markers_return_none():
    only_begin = "<!-- FRAMEWORK:BEGIN -->\nx\n"
    assert section_content(only_begin) is None
    reversed_markers = "# FRAMEWORK:END\nx\n# FRAMEWORK:BEGIN\n"
    assert section_span(reversed_markers) is None
    two_begins = "# FRAMEWORK:BEGIN\na\n# FRAMEWORK:BEGIN\nb\n# FRAMEWORK:END\n"
    assert section_content(two_begins) is None
