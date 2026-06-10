# Bringing a fresh WSL machine to dev parity (for the reviewer / Plan 21 work)

Captures the exact steps used to stand up a second machine (laptop) to run the
`framework` reviewer eval/audit work — e.g. running a Plan 21 phase overnight. Distilled
from doing it on a clean laptop on 2026-06-10.

## What you actually need (and don't)

The reviewer work (`framework eval` / `framework audit` / the Plan 21 audit workflow) needs
only: **`git` + `uv` + Claude Code (authenticated) + the repo.** `uv` brings its own Python
3.12, so the Ubuntu version is irrelevant.

You do **not** need docker / buildx / node / shellcheck — those are for the docker-acceptance
tier and CI-action tests, which the reviewer eval/audit path never touches. (Add them later
only if you want to run the full test suite; see `CLAUDE.md` "Env parity (this box)".)

## 1. Windows — install WSL2 (one-time)

PowerShell as Administrator:
```powershell
wsl --install        # WSL2 + Ubuntu; reboot when prompted
```
Create your Ubuntu user/password on first launch.

**For unattended overnight runs:** set Windows power to **never sleep while plugged in**
(Settings → System → Power), or the run dies when the laptop suspends.

## 2. Ubuntu (WSL) — toolchain

```bash
sudo apt update && sudo apt install -y git curl gh

# uv (fetches its own Python 3.12 — no system Python needed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Claude Code — native installer. MUST be piped to `bash`, NOT `sh`:
# Ubuntu's /bin/sh is dash, which throws a bash syntax error (~line 9) on the installer.
curl -fsSL https://claude.ai/install.sh | bash
```

## 3. PATH that headless/cron shells honour (NOT just ~/.bashrc)

Both `uv` and `claude` install to `~/.local/bin`. **Do not rely on `~/.bashrc`** — bash only
sources it for *interactive* shells, so cron / headless Claude sessions skip it and won't find
the tools. Make them resolvable independent of rc files:

```bash
# symlink into a system PATH dir (resolves in essentially every shell type):
sudo ln -sf "$HOME/.local/bin/uv" /usr/local/bin/uv
sudo ln -sf "$HOME/.local/bin/claude" /usr/local/bin/claude

# and add to ~/.profile (login shells — the profile Claude Code snapshots), plus .bashrc:
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.profile
```

Verify (the `env -i` line mimics a clean/headless shell — it must still find both):
```bash
bash -lc 'command -v uv claude'
env -i /bin/bash -c 'command -v uv claude'
```

## 4. Authenticate (two separate logins)

```bash
gh auth login        # GitHub.com → HTTPS → browser; sign in as the repo owner (private repo)
claude               # complete the browser login with your Pro/Max account
claude --version     # expect 2.1.x
```

## 5. Clone + sync + smoke

The canonical checkout path mirrors the primary box — **note the space in "Claude Code"**, so
quote it:
```bash
mkdir -p ~/"Claude Code/Projects"
cd ~/"Claude Code/Projects"
gh repo clone cdowell-swtr/swiftwater-framework
cd swiftwater-framework
git checkout plan-21-reviewer-tuning
uv sync                                  # fetches Python 3.12.13 + deps

# parity smoke (free subagent backend end-to-end):
TMPDIR=/var/tmp uv run framework eval security --repeat 1 --backend subagent
#   expect:  review-security    recall 1.00  fp 0.00    PASS
```

`PASS` ⇒ the machine is at functional parity for the reviewer work. Use `TMPDIR=/var/tmp`
for anything that renders (the `framework eval` fixtures) — `/tmp` may be a small RAM tmpfs.

## 6. Unattended overnight runs across quota windows

The free `claude -p` backend (and the Plan 21 audit workflow) run on the Claude subscription's
rolling 5-hour windows. A large phase will exhaust a window mid-run. Key facts that shape the
resume design:

- **When the window is exhausted, the orchestrating Claude session is out too** (same
  subscription) — so it cannot react to exhaustion and schedule the next wake.
- **`ScheduleWakeup` is the wrong tool**: it's capped at 1 hour and must be re-armed each hop,
  but re-arming has to happen *during* the dead window — impossible. The chain snaps.
- **Use a standing cron (`CronCreate`), armed once while quota is available.** It fires on a
  fixed schedule independent of session state; firings during an outage are harmless no-ops;
  the first firing after each reset resumes from on-disk + in-git progress (the file-backed
  audit artifacts under `.framework/plan21/` and the pushed stage commits), skipping completed
  work. It deletes itself when done.
- The cron command uses **absolute paths** (`/usr/local/bin/uv run framework …`) and `cd`s into
  the quoted checkout path, so it's rc-independent (§3).
- Requires: laptop awake (§1) + Claude Code session alive + the standing cron.

The backend now degrades gracefully on a session-limit 429 (`BackendExhausted`, exit 4, findings
preserved) rather than crashing — see `src/framework_cli/review/backend.py::_exhaustion_error`.
