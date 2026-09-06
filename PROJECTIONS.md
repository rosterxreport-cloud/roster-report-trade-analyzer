# Roster Report Fantasy Football Projection System

## Status

Phase 1 projection mechanics and the Phase 2 historical/backtest pipeline are implemented. The projection system remains separate from the live v10 trade-analyzer values until the projection models are validated and 2026 role/team assumptions are populated.

Nothing here changes the production RB premium, Superflex scarcity, package discounts, Tier 0 acquisition premium, or existing trade verdicts.

## Core chain

`Team environment -> player opportunity -> player efficiency -> raw stats -> fantasy points -> uncertainty -> projection signal`

The model projects football statistics first. Full PPR, Half PPR, and Standard points are scoring layers over the same stat projection.

## v10 trade-analyzer prior

The current v10 player-quality prior is:

- **45% AW rankings**
- **35% Roster Report 2023-2025 analytics**
- **10% positional scarcity**
- **10% market/trade value**

The projection system may use that prior as one input, but does not overwrite the production v10 value.

Rookies retain their dedicated v10 pathway rather than being treated as veterans with missing NFL history.

## Historical Roster Report weighting

Current-player analytical history uses:

- 2025: 50%
- 2024: 30%
- 2023: 20%

Partial seasons use `season weight × min(games / 12, 1.0)`, after which available season weights are renormalized.

These recency rules describe the current-player analytical prior. The projection backtest may use additional historical seasons later to learn which football metrics are predictive without changing the 2023-2025 player-input window.

## Data pipeline

`scripts/build-projection-history.py` converts the v10 analytics audit workbook into projection-history records.

`scripts/build-nflverse-features.py` pulls nflverse regular-season player summary files and creates:

- player-season feature tables
- team-season environment tables
- QB/RB/WR/TE next-season training tables

The verified nflverse inputs are `stats_player_reg_2023.csv`, `stats_player_reg_2024.csv`, and `stats_player_reg_2025.csv` from the `stats_player` release.

## Model fitting

`scripts/fit-projection-models.py` predicts **next-season PPR points per game**. It deliberately does not fit same-season fantasy points.

The first validation design is:

- train on 2023 inputs -> 2024 outcomes
- validate on 2024 inputs -> 2025 outcomes

Every position is compared with a persistence baseline (`last season PPR/game = next season PPR/game`). Candidate ridge models can use a full feature set or a smaller opportunity/role feature set and can be conservatively blended with persistence. A challenger is promoted only if its holdout RMSE beats the baseline.

This prevents added complexity from being accepted merely because it looks sophisticated.

## Current feature families

### QB

Games, attempts, completion rate, yards/attempt, pass TD rate, interception rate when available, sacks, passing EPA/attempt, rushing volume, rushing efficiency, rushing TD rate, and prior PPR/game.

### RB

Games, carries/game, yards/carry, rushing TD rate, rushing first-down rate, rushing EPA, targets/game, target share, catch rate, yards/target, receiving TD rate, receiving first-down rate, receiving EPA, and prior PPR/game.

### WR / TE

Games, targets/game, target share, air-yard share, WOPR, catch rate, yards/target, air yards/target, YAC/reception, TD/target, receiving first-down rate, receiving EPA/target, and prior PPR/game.

## First successful historical build

The 2023-2025 source pipeline produced:

- 1,776 player-season rows
- 96 team-season rows
- 577 player rows in 2023
- 589 in 2024
- 610 in 2025

The original full ridge v0.1 holdout results were:

| Position | N | MAE PPR/G | RMSE PPR/G | Correlation |
|---|---:|---:|---:|---:|
| QB | 63 | 4.39 | 5.32 | 0.655 |
| RB | 106 | 2.92 | 3.76 | 0.781 |
| WR | 178 | 2.57 | 3.48 | 0.742 |
| TE | 106 | 1.86 | 2.38 | 0.804 |

The persistence comparison showed that QB and TE improved on persistence, while the first RB and WR full-feature ridge versions did not consistently beat it. v0.2 therefore adds baseline-gated model selection and opportunity-focused challengers instead of automatically promoting every fitted model.

## Projection engine

`projection-engine.js` currently provides:

- team-volume projection
- QB projection functions
- RB projection functions
- WR/TE projection functions
- PPR / Half PPR / Standard scoring
- floor / median / ceiling heuristics
- overall and position ranks
- partial-season historical weighting
- a non-production trade-value projection hook

## Next milestones

1. Validate baseline-gated v0.2 by position.
2. Expand historical calibration if needed while preserving the 2023-2025 current-player prior.
3. Add 2026 rosters, depth-chart roles, coaching/team environment and availability assumptions.
4. Generate first 2026 QB/RB/WR/TE raw-stat projections.
5. Backtest and calibrate raw-stat errors, fantasy points and finish probabilities.
6. Add weekly/ROS matchup and role updates.
7. Only after validation, test a projection signal inside the production trade analyzer.
