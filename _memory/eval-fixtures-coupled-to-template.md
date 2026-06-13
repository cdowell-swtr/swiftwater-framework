---
name: eval-fixtures-coupled-to-template
description: "Editing template files that eval-fixture change.patch files anchor on breaks them; re-anchor via render+patch--fuzz+git diff. And scan fixtures with each fixture's OWN batteries, not the all-default."
scope: project
metadata: 
  node_type: memory
  type: reference
  originSessionId: 49f13a1d-7e1e-4c24-8e52-b50a128128c4
---

The reviewer eval fixtures (`tests/eval/fixtures/<agent>/{bad,good}/<case>/change.patch`) are **hand-authored unified diffs anchored to specific lines** of the rendered template. Editing a template file those patches touch (e.g. `routes/items.py`, `db/repository.py`, `prometheus.yml`, `config/settings.py`) **shifts the context and breaks `git apply`**. This recurred all session: the pagination slice broke **20** fixtures (items.py/db reshaped), obs-infra broke **2** (the new otel-collector job displaced the prometheus→postgres gap they inserted into), the data-store/hygiene/DLQ slices broke **0** (touched files no fixture anchored on, or battery-gated changes invisible to `batteries:[]` fixtures).

**Always re-scan after a template edit:** for every `change.patch`, render with **that fixture's own `fixture.yaml` `batteries`** and `git apply --check`. CRITICAL: render with the fixture's exact batteries (empty list → `--batteries ""`), **NOT** `template-render`'s default (which is ALL batteries). Rendering empty-battery fixtures with the all-default produced a false "7 fixtures broken" measurement artifact once (battery-dependent files like the pyproject deps array / compose overlays looked mismatched) — the real count was 1.

**To re-anchor a broken fixture** (preserve the seeded issue, just move the anchor):
1. render the fixture's battery set to a temp git repo (template-render git-inits + commits);
2. `patch -p1 --fuzz=3 --no-backup-if-mismatch -d <repo> < change.patch` (fuzz tolerates the line shift; for hunks that genuinely overlap the edit, scripted intent-reapplication onto the new baseline + `git diff` instead);
3. `git -C <repo> add -A && git -C <repo> diff --cached` → the regenerated patch;
4. verify `git apply --check` against a fresh render; write it back; commit `test(eval): re-anchor …`.

Note: battery-gated template changes (inside `{% if X in batteries %}`) don't affect fixtures rendered with `batteries:[]`, so they often break 0 fixtures. There is also a per-battery obs guard (`[[obs-completeness-guard-already-exists]]`). Cross-ref `[[never-batch-dependent-pipeline-steps]]`.
