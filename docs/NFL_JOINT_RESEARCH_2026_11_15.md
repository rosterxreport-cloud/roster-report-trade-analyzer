# NFL offensive-player / DST joint research

Implemented a combined event-consistent research engine, two retrospective candidate runs, saved-draw verification, and 11 new regression tests. All 38 Python research checks pass locally. Existing free forecasts, production, sign-in and billing settings are unchanged.

## What is connected

The engine samples entire strictly prior historical games, weighted by the frozen RR team opportunity/yardage/TD context. The sampled plays are reassigned using RR passing, rushing, reception and target shares. Offensive players and both DSTs share the same outcomes within a game; different scheduled games are independent. This is a coarse whole-game replay, not a possession or field-position simulator. It does not guarantee each player's marginal mean equals the original RR projection and never overwrites those projections.

Checked per draw: passing yards equal receiving yards; passing TDs equal receiving TDs; quarterback interceptions equal opposing-DST interceptions; sacks taken equal opposing-DST sacks; fumbles lost plus explicit unmodeled team fumbles equal opposing-DST recoveries; receptions, targets, attempts and TDs are consistent; and offensive/special-team scoring reconstructs opposing-DST points allowed. Extra points, field goals and conversion scoring are retained separately so points allowed are genuinely checked, not inferred solely from fantasy scores.

Each saved compressed draw file contains player stat lines, team scoring events, DST events and fantasy scores. validate-nfl-joint.py checks file hashes, dimensions, event identities, recomputed offensive/DST scoring, public score vectors and every player summary. Both complete candidate artifacts passed these checks: 14 games, 275 offensive players, 28 DSTs, 303 aligned score vectors, 10,000 draws per vector. The artifacts deliberately retain kind=joint-research and publishApproved=false, so they cannot be imported as approved live data.

## Source-moment experiment

The second variant softly reweights and resamples whole outcomes toward source RR statistical expectations. It preserves all event relationships. Receiver TD targets are normalized to team passing TD totals, and the 197 target changes are explicitly reported; this is a joint research reconciliation, not a change to the published forecasts. A fixed regularizer and effective-sample-size backoff avoid concentration on a handful of outcomes. The initial untempered fit collapsed to roughly 29–92 effective draws per game and was rejected. Backoff retains at least 1,000 effective draws before resampling 10,000 rows. Resampled rows are not 10,000 independent historical observations. This procedure aligns moments; it is not proof of calibrated probabilities.

## Week 9 retrospective results

Both variants use the same 231 uniquely matched played results across 14 games. Missing results remain excluded, not zero-filled. Already-started Thursday games are excluded using the saved Sunday capture timestamp.

| Metric | Initial joint replay | Moment-aligned replay |
|---|---:|---:|
| Offensive mean DK MAE | 5.591 | 5.376 |
| Offensive mean bias | +0.004 | -0.089 |
| Middle-80% interval coverage | 74.9% | 77.1% |
| DST mean DK MAE, same 28 defenses | 4.182 | 4.598 |

On the 144-result cohort shared with the prior event-input candidate, its point MAE is 5.217; joint-mean MAE is 5.645 initially and 5.445 after alignment. The joint mean therefore does **not** replace the point forecast. Alignment improved offensive errors on this sample but worsened DST errors. The second experiment was developed after inspecting the first results: all comparisons remain exploratory, not an untouched holdout or prospective improvement claim. Source historical provider corrections may differ from originally available pre-lock records.

## Remaining release work

Unmodeled special-team/defensive fumbles and some return/recovery touchdowns remain explicit team events when a named-player role is unsupported. DNP probabilities, verified active rosters, calibration across additional frozen slates, model-source integrity and a valid historical salary/lineup replay remain unresolved. There is no contest payout or profitability claim. The next model step is improving player-role and game-context calibration without losing event consistency, followed by a frozen prospective test. Production approval is not justified by structural tests alone.

## Reproduction

Use the same private forecast, PBP, weekly-stat and schedule hashes recorded in each artifact. Only prior weeks enter template selection, role history or moment alignment; actual results are joined afterward.

```sh
OPENBLAS_NUM_THREADS=1 python scripts/pro/nfl-joint-research.py --forecast PRIVATE_WEEK9.csv --pbp PRIVATE_PBP.parquet --stats PRIVATE_STATS.parquet --schedule PRIVATE_GAMES.csv --season 2026 --week 9 --captured-at 2026-11-08T09:07:42.962904Z --output NEW_RAW_DIRECTORY
OPENBLAS_NUM_THREADS=1 python scripts/pro/nfl-joint-research.py --forecast PRIVATE_WEEK9.csv --pbp PRIVATE_PBP.parquet --stats PRIVATE_STATS.parquet --schedule PRIVATE_GAMES.csv --season 2026 --week 9 --captured-at 2026-11-08T09:07:42.962904Z --align-moments --output NEW_ALIGNED_DIRECTORY
python scripts/pro/validate-nfl-joint.py --directory SAVED_DIRECTORY
```
