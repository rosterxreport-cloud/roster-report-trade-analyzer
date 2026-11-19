# Roster Report DST model — first implementation

Implemented scripts/pro/nfl-dst-model.py and eight regression tests. Production, free forecasts, sign-in and billing activation are unchanged.

## Historical scoring ledger

Reconstructed 272 team results across 136 regular-season games through Week 9 from the preserved nflverse play-by-play. All scoring-play totals reconcile with the final play-by-play scoreboards and frozen schedule scores. Points allowed exclude opposing defensive touchdowns and safeties; extra points after defensive touchdowns still count, as do kick/punt/field-goal return touchdowns and conversion returns. Team sacks, both fumble recoveries on a multiple-turnover play, blocked kicks and conversion returns are handled separately. Penalty safeties remain counted even when play_type is no_play.

Scoring reference: https://external.draftkings.com/help/rules/nfl/classic . These are reconstructed labels, not a claim of independent matching against DraftKings contest settlements.

Cross-checks against frozen weekly defensive player totals found six discrepancies. Four team sacks are corroborated by opposing quarterbacks' sacks_suffered totals and lack individual defensive sack credits. Two safety discrepancies were checked against final ESPN scoring plays and matching final scores: no Buffalo safety in event 401872932; a Las Vegas team safety in event 401872941. The play-by-play values were retained with source hashes and explicit resolution notes. No underlying source file was rewritten. Zero unresolved component discrepancies remain for these selected cross-checks; not every scoring component has an independent provider cross-check.

## Forecast model and backtest

The new research policy equally mixes whole prior results from the defense and prior results by defenses facing its scheduled opponent. It requires at least four games for each. Weights are an exploratory hypothesis, not tuned or validated production coefficients. Each historical sample retains its event/points-allowed dependence. Expected points are computed analytically from event expectations and the seven PA band probabilities; each defense also receives 10,000 seeded draws, median, P10 and P90. Matchup-specific seeds prevent accidental shared-index correlations across separately modeled defenses.

Rolling Weeks 5–9 evaluation uses only strictly earlier weeks for every forecast, 144 team results / 72 games:

| Metric | Result |
|---|---:|
| Candidate DK MAE | 4.282 |
| Own-team prior-mean baseline MAE | 4.538 |
| League prior-mean baseline MAE | 4.307 |
| Middle-80% interval coverage | 78.5% |

Game-cluster bootstrap 95% intervals (2,000 resamples) for candidate minus baseline MAE: own-team -0.497 to -0.001; league -0.282 to +0.239. The league comparison does not establish improvement. Historical outcomes had already been accessible, so this remains exploratory, not an untouched holdout or prospective result. Historical provider corrections may differ from original pre-lock records.

Created 28 schedule-based Week 10 research forecasts and checked that every expected point total matches the application's JavaScript DST scoring adapter. These were generated after lock and are explicitly labeled research reconstructions. The official frozen main-slate DST salary identities are joined separately; this does not renew their expired pre-lock validity or approve a live slate.

## Release boundaries and next integration

The historical ledger has completed scoreboard and selected-component reconciliation. The DST model and artifacts retain publishApproved=false pending independent settlement checks and prospective validation. This is a real first-party research forecast policy, not third-party defense projections.

Within-DST bootstrap dependence is implemented. Joint dependence with quarterbacks, receivers, opposing offenses and the other DST is not implemented and is not claimed. The optimizer must continue rejecting advanced NFL runs until that full game/player joint artifact, complete offensive event inputs, source integrity and current availability are approved. DST scoring/data coverage is materially advanced; the entire optimizer is not production-ready.

Reproduce using the preserved PBP, frozen weekly player stats/schedule and two dated ESPN summary captures:

```sh
python scripts/pro/nfl-dst-model.py --pbp PRIVATE_PBP.parquet --stats PRIVATE_PLAYER_STATS.parquet --schedule PRIVATE_GAMES.csv --season 2026 --week 10 --verification-dir PRIVATE_ESPN_CAPTURES --salary-pool PRIVATE_APPROVED_SALARY_POOL.json --output NEW_PRIVATE_OUTPUT_DIRECTORY
```
