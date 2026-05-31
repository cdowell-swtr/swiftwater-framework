# Audit report

## Cost (subagent-dispatched, ~$0)

| Agent | Calls | In tok | Out tok |
|---|---|---|---|
| review-application-logic | 1 | 0 | 0 |
| review-architecture | 1 | 0 | 0 |
| review-dependency | 1 | 0 | 0 |
| review-documentation | 1 | 0 | 0 |
| review-security | 1 | 0 | 0 |
| review-test-quality | 1 | 0 | 0 |

## Findings
### review-application-logic
- `.claude/workflows/reviewers-audit.js:132` **medium** — Behavior regression on empty items: the old code threw 'reviewers-audit: args.work_items must be a non-empty array' so an empty audit was loud and visible. The new code silently returns `{results: [], meta: ARGS.meta || {}}` when `index.items` is empty. If `audit-prepare` accidentally produces zero work items (e.g., agent filtering bug, target detection mishap), the workflow no longer surfaces the problem — finalize then receives an empty result set and the operator gets a green run that did nothing. The recovery path (early return) doesn't actually recover; it hides the failure.
- `.claude/workflows/reviewers-audit.js:130` **low** — The guard `!Array.isArray(items)` from the old code was dropped. Only `items.length === 0` is checked. If the index-load subagent returns a malformed payload that slips the JSON-Schema validator (e.g., `items` set to a non-array via an unexpected coercion), `items.length` may be undefined and the downstream `items.map(...)` will throw a less informative TypeError instead of the previous descriptive Error.
- `src/framework_cli/cli.py:268` **low** — `if split_dir.exists(): shutil.rmtree(split_dir)` will raise NotADirectoryError if a stale FILE happens to be at `split_to` (e.g., a user passed a path that collides with an existing non-directory). `shutil.rmtree` only handles directories. The split-manifest setup will then crash mid-`_emit_audit_prep`, leaving `audit-prepare` in a broken state. The doc claims 'Idempotent: an existing DIR is cleared first' but doesn't handle the non-dir case.

### review-architecture
_(no findings)_

### review-dependency
_(no findings)_

### review-documentation
- `src/framework_cli/cli.py:666` **low** — The `audit-prepare` command docstring states 'Output is JSON on stdout; consumed by /reviewers:audit.' but with the new `--split-to` flag the command now also writes an `index.json` + `items/item-NNNN.json` tree to disk. The docstring is slightly stale — consider a one-line note describing the side-effect when `--split-to` is set.
- `src/framework_cli/cli.py:1052` **info** — `_emit_audit_prep` gained a new `split_to` parameter but has no function-level docstring. An inline comment block explains the split-manifest write, which is helpful, but a short docstring on the helper would make its dual-output contract (stdout manifest + optional on-disk split layout) explicit to readers.

### review-security
- `src/framework_cli/cli.py:268` **low** — Predictable path in /tmp combined with exists()->rmtree->mkdir is a small TOCTOU/symlink attack window on multi-user systems. A local attacker could replace /tmp/reviewers-audit-prep-split with a symlink between the exists() check and the rmtree/mkdir; shutil.rmtree refuses to follow a top-level symlink but the slash command's preceding `rm -rf /tmp/reviewers-audit-prep-split 2>/dev/null` (audit.md line ~26) does follow symlinks and could be coerced into removing arbitrary attacker-pointed paths the invoking user can write. Per-item files carry the full diff (potentially sensitive), so the temp tree is a confidentiality boundary.
- `src/framework_cli/cli.py:271` **low** — items_dir.mkdir(parents=True, exist_ok=True) creates the directory tree using the process umask (commonly 0o022 → 0o755) and only afterwards chmods to 0o700. Between mkdir and chmod, another user on the host can list the directory and read per-item filenames (the file contents themselves get 0o600 only after write, so there is also a tiny window where they are world-readable on a permissive umask).

### review-test-quality
- `tests/test_cli.py:549` **medium** — The new test does not assert the file permissions (0o700 on split_dir/items_dir, 0o600 on index.json/item-NNNN.json) that the production code in _emit_audit_prep explicitly sets. The accompanying code path and PR description emphasize these tight perms because per-item files carry the full diff payload (sensitive), so a regression that drops the chmod calls would silently slip past this test. Add asserts on stat().st_mode & 0o777 for split_dir, items_dir, index.json, and the per-item file.
- `tests/test_cli.py:511` **medium** — The --split-to behavior is documented as idempotent ('an existing DIR is cleared first' — implemented via shutil.rmtree before mkdir), but the test only exercises the fresh-dir path. A regression that removed the rmtree call (leaving stale items from a prior run) would not be caught. Add a second invocation against a pre-populated split_dir and assert stale files are gone.
- `tests/test_cli.py:540` **low** — The test only exercises a single agent (`--agent security`), so index ordering, the i-indexed item filename padding (`item-NNNN.json` for i>=10), and multi-item dispatch are not covered. A bug in the `enumerate` loop or `f"item-{i:04d}.json"` formatter for multi-digit indices would not be caught.

## Drift check
_(no drift detected)_

