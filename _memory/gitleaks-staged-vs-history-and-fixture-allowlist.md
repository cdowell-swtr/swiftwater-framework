---
name: gitleaks-staged-vs-history-and-fixture-allowlist
description: "The gitleaks pre-commit hook scans STAGED diffs only; the authoritative scan is CI `gitleaks detect` over full history (fetch-depth 0). It flags the intentional fake secrets in security eval fixtures → allowlist them in .gitleaks.toml using the SINGULAR [allowlist] table (the doubled-bracket plural form silently no-ops in v8.21.2)."
scope: project
metadata:
  type: project
---

The framework's own repo wired gitleaks in Plan 26 (a `security` job in `ci.yml` plus a root `.pre-commit-config.yaml`). The **local hook and the CI scan are NOT equivalent**:

- The **pre-commit `gitleaks` hook** runs in `protect`/`--staged` mode — it only scans the **staged diff** of a commit. `pre-commit run gitleaks --all-files` does essentially nothing (nothing staged), so it passes trivially and gives false confidence. It does NOT scan the working tree or history.
- **CI `gitleaks detect --source . --redact --no-banner`** with `actions/checkout@v5` `fetch-depth: 0` scans the **entire git history** (every commit ever). This is the authoritative backstop and the right thing for a PUBLIC repo — history is public, so a secret ever committed is exposed even after it's removed from HEAD.

**The false-positive that bit on the first CI run:** `gitleaks detect` flagged 2 "leaks" in `tests/eval/fixtures/security/bad/hardcoded-secret.diff` — the intentional fake AWS key that the `security` review agent is built to detect, not a real credential. Eval fixtures under `tests/eval/fixtures/security/` deliberately contain secret-shaped payloads.

**Fix — allowlist the fixtures in a root `.gitleaks.toml`:**
```toml
[extend]
useDefault = true
[allowlist]
description = "intentional fake secrets in security eval fixtures"
paths = ['''tests/eval/fixtures/security/.*''']
```

**Gotcha (cost 2 iterations):** gitleaks' **plural** allowlist form (the array-of-tables written with doubled square brackets) **silently no-ops** in **v8.21.2** (the scan still reports the leaks). Use the **singular** `[allowlist]` table — it works. gitleaks auto-discovers `.gitleaks.toml` at the source root (no `--config` needed). Verify locally with the real binary over full history (`gitleaks detect --source .`), NOT the pre-commit hook, since the hook won't reproduce the history scan.

Related: the commit-gate hook's own regex documents a `[[:space:]]` POSIX class that naive wiki-link checkers false-positive on — see [[commit-gate-hook-false-matches-git-commit-substring]].
