---
name: hybrid-region-marker-token-in-prose
description: "Never write the literal FRAMEWORK:BEGIN/END token in a hybrid file's own comment prose — section_span counts every line containing the token, so a named marker reads as a duplicate and the file parses as unmarked."
scope: project
metadata: 
  node_type: memory
  type: project
  originSessionId: 1db7758b-781f-48fb-8307-2870e1d8f397
---

In the integrity **hybrid** tier (`src/framework_cli/integrity/sections.py`), `section_span` finds the managed region by counting **every line that *contains*** the literal `FRAMEWORK:BEGIN` / `FRAMEWORK:END` token, then requires **exactly one** of each, in order. So if you mention the token in the region's own explanatory comment prose (e.g. a `# FRAMEWORK:BEGIN` block whose text says "add hooks below the FRAMEWORK:END marker"), that counts as a **second** marker → `len(ends) != 1` → `section_span` returns `None` → the file is treated as **unmarked**. Every hybrid render then fails with `AuthoringError: <file> is a hybrid file but has no FRAMEWORK:BEGIN/END markers`.

**Why:** this cost a **38-test red** while making `.pre-commit-config.yaml` hybrid (PR #10, v0.2.2). The fix is to never name the opposite token in prose — say **"the closing marker"** instead. This is exactly why the template `Taskfile.yml.jinja` BEGIN comment reads "Add your own tasks below the closing marker."

**How to apply:** when adding a file to `HYBRID_TRACKED` or editing a hybrid file's marker comments, keep the literal `FRAMEWORK:BEGIN` and `FRAMEWORK:END` tokens each on **exactly one line** (the real marker lines). In guidance text refer to "the closing/opening marker," never the token. The guard that catches this fast is `tests/integrity/test_classes.py::test_every_hybrid_path_renders_with_markers` (iterates `HYBRID_TRACKED`). Related: [[template-payload-tdd-loop]], [[eval-fixtures-coupled-to-template]].
