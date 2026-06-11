# Mini-project brief — Time-of-day cache/latency/cost probe

> Standalone experiment (decoupled from Plan 21). Goal: quantify how the `claude -p`
> subscription backend behaves across the 24-hour clock. Born from a 2026-06-11 observation
> that off-hours sweeps run much faster and bill far fewer effective tokens than during US
> business hours (cache stays warm when calls are tightly spaced). See
> [[reviewer-eval-throughput-time-of-day]].

## Objective
Empirically map how the `claude -p` backend's **prompt-cache effectiveness, latency, and
effective token cost vary by hour-of-day** — to confirm and quantify the "slower + more
expensive during US business hours" effect. Deliverable: a 24-hour coverage curve.

## Sampling design — *why 5h × 5 days*
Fire a fixed probe **every 5 hours**. Because `gcd(5, 24) = 1`, the firing times **precess
through all 24 clock-hours** over 24 firings ≈ **5 days** — even 24h coverage from a cheap,
sparse probe. The whole trick is the 5h interval; don't "round" it to 6 or 4 (those alias onto
a handful of hours forever).

## Why synthetic (not the review agents)
A single **fixed** synthetic prompt removes agent/fixture confounding — identical input every
firing, so any variation is **time-of-day / backend load**, not content. Also fully decoupled
from Plan 21, so it can run independently for days.

## The probe (per firing)
- **Prompt:** a large **fixed** cacheable prefix (~15–30k tokens of stable filler/doc) + a tiny
  rotating suffix (`answer Q{n}`) to force a small real completion.
- **Burst of 3 back-to-back calls** via `claude -p --output-format json`:
  - call 1 → establishes cache (expect `cache_creation`),
  - calls 2–3 → should hit the warm server cache (expect `cache_read`) *if* within the 5-min TTL
    and the backend isn't evicting under load.
- **Capture per call:** latency, `cache_creation`/`cache_read`/`input`/`output` tokens, stop_reason.
- **Derive per firing:** warm-hit ratio (calls 2–3 with `cc==0`), token-weighted cache-read %,
  effective input cost (`cc + input + 0.1×cr`), latency p50/p90.

## Wiring — *the gotcha lives here*
- ❌ **Don't use `0 */5 * * *`** — cron resets daily, so it fires the *same 5 hours* every day →
  never precesses → only 5 hours ever sampled.
- ✅ **Recommended:** a frequent **heartbeat cron** (e.g. `*/20 * * * *`) + a **"due if ≥5h since
  last run" gate** via a timestamp file. Precesses correctly, self-catches missed firings, and
  reuses the static cron that already works on this box.
  - `*/20 * * * * /path/probe-gate.sh` → gate checks `now - last_run ≥ 5h`; if due, run the probe
    + stamp `last_run`.
- Alternatives: a self-re-arming `at` chain (needs `atd`), or a `systemd --user` timer with
  `OnUnitActiveSec=5h` (WSL user-systemd is finicky — lower confidence).
- **WSL caveats (learned the hard way this session):** the cron daemon must actually be running
  (`service cron status` — WSL doesn't auto-start it); keep Windows/WSL awake; `crontab`
  introspection needs sandbox-off under Claude Code. See `docs/maintenance/laptop-dev-parity.md`.

## Recording + analysis
- Append one row per **call** to a durable JSONL/TSV (`ts, hour, call_idx, latency_s, cc, cr,
  inp, out`) — keep it in a git-tracked or rsync'd path so a reboot doesn't lose it.
- After ~5 days: `analyze.py` aggregates by **hour-of-day** → latency p50/p90, warm-hit %,
  cache-read %, cost-saved % vs hour. Congestion signature = latency p90 climbing **and**
  cache-read % / warm-hit % dropping across US business hours.

## Deliverables / milestones
1. `probe.sh` — build prompt, fire the 3-call burst, parse JSON usage, append rows.
2. `probe-gate.sh` + one crontab line — the 5h-precessing scheduler.
3. results schema + `analyze.py` — aggregate by hour.
4. 5-day run → short findings writeup (the hour-of-day curve + cost implication).

## Open decisions / risks
- **Backend:** `claude -p` (matches the path you actually use; free; caching implicit) **vs** the
  Anthropic API with explicit `cache_control` breakpoints (precise control + exact usage, but
  costs API $). *Recommend `claude -p`* unless you want controlled cache-breakpoint experiments.
- **Quota:** negligible (~3 small calls / 5h) but it shares the subscription's rolling window —
  keep the prefix modest.
- **TTL timing:** the 3-call burst must complete inside the ~5-min cache TTL; tune prefix size
  accordingly.
- **Scheduler choice — `/schedule` vs OS-cron:** Claude Code's own `/schedule` (cloud routines)
  could drive this too, but it runs in the cloud — wrong path if you want to measure *this box's*
  `claude -p` behavior across the day. Use OS-cron (this machine) to characterize the local
  subscription path; use `/schedule` only if you instead want to probe the cloud path.

## Appendix — the observation that motivated this (2026-06-11, ~04:1x–08:0x PDT)
From the Plan 21 Phase-3 re-sweep findings (`.framework/plan21/final-findings/`), bucketed by clock time:

| bucket | n | latency med | latency p90 | cache-read % (token-wt) | eff. input saved | pure warm-hit rate |
|---|---|---|---|---|---|---|
| night (04–05h) | 105 | 35.7s | 73.3s | 79.5% | ~70% | 30% |
| morning (07h+) | 12 | 28.7s | 56.8s | 80.4% | ~70% | 17% |

Caveats at capture time: the morning bucket was tiny (12 calls, one agent) and pre-peak
(~10:5x ET), so no congestion penalty was visible yet — token-weighted cache-read % held ~80%
(~70% effective saving) in both. The only early wrinkle was the *pure* warm-hit rate (30%→17%),
likely sample/agent noise. A dedicated controlled probe (this brief) replaces the confounded
opportunistic read with a clean hour-of-day curve.
