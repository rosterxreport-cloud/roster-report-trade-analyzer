# Recovered NBA optimizer replay — rerun 2026-11-14 PT

These are reruns of the recovered Python research optimizer, not backtests of the new JavaScript server optimizer. Restricted salary pools and incomplete pre-lock evidence prevent verified cash-rate or ROI claims.

| Slate | Matched salary rows | Standard GPP DK | Home Run GPP DK | Published top-20% reference |
|---|---:|---:|---:|---:|
| 2026-11-02 | 24 | 209.75 | 221.0 | 308.25 |
| 2026-11-04 | 26 | 248.75 | 220.25 | 270.5 |
| 2026-11-05 | 17 | 174.5 | 174.5 | 246.25 |
| 2026-11-06 | 18 | 168.75 | 150.25 | 302.5 |
| 2026-11-07 | 112 | 244.0 | 266.25 | 293.0 |
| 2026-11-08 | 13 | 227.0 | 227.0 | Unavailable |

The five dates with published comparison thresholds reproduce the archived means: standard GPP 209.15; Home Run 206.45. Neither clears any of the five references. The latest research bundle now permits scoring Nov 8 at 227.0 for both strategies, but no corresponding published threshold is available. This sixth date does not establish a cash result.

The 10,000-draw adapter separately ran 145 players from the Nov 14 model snapshot. Source publishApproved=false is preserved. Recovered model tests: 84 pass; recovered optimizer tests: 7 pass. No forecast weights or private research files were published.

## Current saved NBA forecast audit

A fresh read-only audit of the recovered bundle separates model policies, verifies each saved forecast timestamp precedes its game start, and checks the minutes/per-minute error identity. For `shared-preseason25-v1`, the archive contains 2,833 paired played player-games across 140 games and 18 dates (October 26–November 13): Yahoo MAE 7.781; DraftKings MAE 7.756; minutes MAE 5.046. Signed bias is +0.271 Yahoo points, +0.241 DraftKings points and −0.412 minutes. This is the saved archive's cohort, not a current live slate.

Mean absolute minute-error contribution is 4.743 Yahoo points; mean absolute per-minute production-error contribution is 5.629. These absolute contributions do not add to total MAE because signed contributions can offset. Both parts need attention; a blanket minutes multiplier is not supported by this audit. The policy has not met the existing 200-game review threshold, despite spanning more than 14 dates. DNP/participation accuracy is not established. No model weights changed and the source publication gate remains closed.

Reproduce with `python scripts/pro/audit-nba.py --model-dir /private/roster-basketball-model --output /private/release-audit.json`. Source audit SHA256: 61251135347dbf659e425633985b5a41a0f71e5c681116ed8ba6ddbd564694c3.

The recovered November 7 salary excerpt uses `research-*` identifiers rather than official DraftKings player IDs. The new live-slate importer intentionally rejects those identifiers. The old restricted-pool replay cannot be treated as an export-ready full-slate backtest.

### Historical shooting paired check — November 15, 2026

Added `scripts/pro/audit-shooting.py`, which invokes the recovered proprietary
historical-shooting policy without changing the private source or saved forecasts.
It deduplicates observed appearances, rejects conflicting shooting counts, filters
history strictly before each target date, and leaves minutes, shot/FT volumes,
other counting stats and the existing preseason weighting unchanged. Completed
archive seasons without period origins are eligible only after July 1 of that
season year; current-season rows use the recorded period origins. Input hashes
are included in the private output for reproducibility.

For `shared-preseason25-v1`, 2,811 paired played forecasts have incumbent Yahoo
MAE **7.773684** versus historical-only shooting **7.771280** (change −0.002404).
Another **22** forecasts lack required shooting history and are excluded, with no
generic fallback. For the older frozen policy, 135 paired rows change from
8.924636 to 8.911397; one is excluded. These are retrospective sensitivity checks
on recovered observations, not prospective accuracy gains or release approval.

DraftKings challenger scoring is intentionally omitted: its double-double bonus
probabilities must be recomputed consistently after shooting changes. Reusing the
incumbent expected bonus would give an unsupported comparison. Publication stays
blocked pending a frozen prospective historical-only challenger, missing-history
handling, consistent simulations and the remaining source/data release checks.

Reproduce with `python scripts/pro/audit-shooting.py --model-dir PRIVATE_MODEL_DIR
--output PRIVATE_OUTPUT.json`. The standard-library tests in
`scripts/pro/test-audit-shooting.py` verify target-day/future exclusion and completed
archive boundaries without accessing proprietary data.
