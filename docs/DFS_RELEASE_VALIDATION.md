# DFS release validation — November 15, 2026

Decision: **not release-approved**. No publication flag, production data or private model weights were changed. These are empirical validation results, not claims of profitability.

## NBA joint distributions

`validate-simulations.py` ran the recovered model at 10,000 draws per player on November 7–13. It separately ran the existing historical-shooting policy as a retrospective challenger, withholding complete games containing unsupported player shooting histories. The two variants generated 24.5 million player outcomes across 14 date/variant runs. Scoring and all structural checks passed: finite/nonnegative boxes, makes versus attempts, point identities, team and individual minutes, opposing game lengths, assists, steals and blocks.

| Metric | Incumbent full cohort | Historical-only challenger | Incumbent paired cohort |
|---|---:|---:|---:|
| Played appearances / games | 1,056 / 51 | 672 / 33 | 672 / 33 |
| Existing point forecast DK MAE | 7.698 | — | 7.561 |
| Simulation mean DK MAE, all draws | 8.021 | 8.015 | 8.042 |
| Simulation mean DK MAE, conditional on playing | 7.824 | 7.642 | 7.693 |
| Middle 80% coverage, all draws | 83.0% | 84.5% | 83.6% |
| Middle 80% coverage, conditional on playing | 78.0% | 80.5% | 79.9% |

The source point forecast is conditional on playing. All-draw simulations include absences, so played-draw metrics are also required. DNP calibration is not established by this played-observation sample. All seven source snapshots have Unknown availability statuses. The current forecast policy's wider 140-game archive remains below its existing 200-game review threshold.

The incumbent all-draw coverage has a game-cluster bootstrap 95% interval of 80.4%–85.5% (2,000 resamples). Its all-draw mean MAE exceeds point MAE by 0.323, with a game-cluster interval of +0.014 to +0.646. Neither the all-draw nor conditional simulation mean warrants replacing the saved point forecast. The challenger is reconstructed retrospectively, on a reduced cohort, with no refitting. Shared seeds do not force identical latent random draws when distributions change; the small paired difference does not establish a prospective improvement.

The adapter derives bonuses from each complete simulated box: PTS + 0.5×3PM + 1.25×REB + 1.5×AST + 2×STL + 2×BLK − 0.5×TOV, plus 1.5 for at least two double-digit categories and another 3 for at least three. Each bonus occurs at most once. Source: [official NBA Classic rules](https://lp.draftkings.com/help/rules/nba/classic), checked November 15.

## NFL saved forecast and current-feed audit

The recovered Week 9 Sunday pregame CSV was registered at 2026-11-08T09:07:42.962904Z. `validate-nfl-archive.py` grades its unchanged forecasts using player + team + opponent + position, scheduled kickoff cutoffs, and recorded nflverse PPR. It excludes 22 already-started Thursday rows and 43 unmatched actuals, without assigning missing players zero.

| Position | Matched n | PPR MAE |
|---|---:|---:|
| QB | 28 | 6.335 |
| RB | 59 | 4.910 |
| WR | 98 | 5.079 |
| TE | 47 | 3.947 |
| Overall | 232 | 4.958 |

This is one week's matched-observation PPR accuracy, not DraftKings or contest performance. The original Week 10 source model and frozen inputs were also recovered privately.

`audit-nfl-dfs.mjs` checks the current Week 10 publication without modifying values. All 295 rows reconcile with published baseline scoring. Release remains blocked by CIN targets 35.96 > pass attempts 35.39, duplicate Kirk Cousins teams, and Kyle McCord's positive projection carrying an Out/IR note. Missing DK bonus/event inputs, proprietary DST forecasts and joint NFL draws are not replaced with zero or generic projections. Official DK interception scoring is −1; the current PPR baseline uses −2. Source: [official NFL Classic rules](https://games.draftkings.com/help/rules/nfl/classic), checked November 15.

## Salary approval

No complete official DraftKings salary export was located in the recovered files. Official NBA/NFL lobby salary requests returned an unavailable page in this environment. Existing excerpt pools with `research-*` IDs cannot clear the importer or establish a valid CSV export. Current official Classic DKSalaries.csv files for both sports are needed. Historical testing additionally requires the original pre-lock complete pools and availability captures. Salary files alone do not approve models or repair unknown availability.

## Reproduction

Install optional offline validation dependencies with `pip install -r scripts/pro/requirements-validation.txt`. They are not runtime application dependencies. All private input and output paths below are placeholders.

```sh
python scripts/pro/validate-simulations.py --model-dir PRIVATE_MODEL_DIR --dates 2026-11-07 2026-11-08 2026-11-09 2026-11-10 2026-11-11 2026-11-12 2026-11-13 --output PRIVATE_SIM_REPORT.json
python scripts/pro/validate-nfl-archive.py --forecast PRIVATE_WEEK9.csv --actuals PRIVATE_STATS.parquet --schedule PRIVATE_GAMES.csv --season 2026 --week 9 --forecast-captured-at 2026-11-08T09:07:42.962904Z --output PRIVATE_NFL_REPORT.json
node scripts/pro/audit-nfl-dfs.mjs data/weekly-projections.json PRIVATE_READINESS_REPORT.json
```

Full empirical reports retain source hashes, simulator identity, seeds, cohort exclusions and limitations. The public adapters and synthetic regression tests contain no proprietary weights or raw research inputs. New tests cover bonus scoring, CRPS, invalid joint boxes, historical capture cutoffs, duplicate identities, missing actuals, scoring integrity and source contradictions. CI runs the seven statistical/join tests in a separate job; empirical private research is not shipped into CI.
