# Roster Report Fantasy Football Projection System

## Status

Phase 1 foundation is implemented in `projection-engine.js`.

The projection system is deliberately separate from the live v10 trade-analyzer calculations until it has been populated with real inputs and backtested. Nothing in the existing rankings, RB premiums, Superflex logic, package discounts, or Tier 0 asset treatment is changed by this phase.

## Core model

The projection chain is:

`Team environment -> Player opportunity -> Player efficiency -> Raw stats -> Fantasy points -> Uncertainty -> Trade-value signal`

This is intentionally different from projecting fantasy points directly. Each player's projected stats must reconcile with a plausible team environment.

## Existing trade-analyzer analytics

The v10 audit workbook is the source of truth for the veteran player-quality prior:

- 45% Roster Report 2023-2025 analytics
- 35% AW rankings
- 10% positional scarcity
- 10% market/trade value

Rookies keep a dedicated pathway rather than being treated as veterans with missing NFL history.

The projection engine exposes `tradeAnalyzerPrior` when those component ratings are available, but does not overwrite the existing v10 `value` field.

## Historical weighting

Default recency weights inside the projection engine:

- 2023: 20%
- 2024: 30%
- 2025: 50%

Partial seasons follow the v10 audit rule: each season weight is multiplied by `min(games / 12, 1.0)`, then the observed season weights are renormalized.

These are intended for predictive player inputs, not for replacing the established 45/35/10/10 trade-value formula.

## Team inputs

Every team projection should eventually include:

- games
- plays per game
- pass rate
- sack rate per dropback
- passing yards per attempt
- passing TD rate
- interception rate
- rushing yards per carry
- rushing TD rate

Later versions should add explicit coaching/scheme priors, offensive-line quality, pace, neutral-script pass rate, expected game environment, and QB-change effects.

## QB inputs

Current engine inputs:

- projected games
- QB attempt share
- passing yards per attempt
- passing TD rate
- interception rate
- rushing attempts per game
- rushing yards per attempt
- rushing TD per attempt
- role multiplier

Planned analytical features include EPA/dropback, CPOE, adjusted completion rate, pressure-to-sack rate, scramble rate, designed-rush rate, deep-ball efficiency, red-zone usage, and offensive-line/context adjustments.

## RB inputs

Current engine inputs:

- projected games
- carry share
- yards per carry
- route participation
- targets per route
- catch rate
- yards per target
- rushing TD share
- receiving TD rate
- role multiplier

Planned analytical features include yards after contact per attempt, missed tackles forced, explosive-run rate, success rate, yards before contact, targets per route, receiving efficiency, goal-line carry share, expected fantasy points, and offensive-line/context adjustments.

## WR / TE inputs

Current engine inputs:

- projected games
- route participation
- targets per route
- catch rate
- yards per target
- receiving TD per target
- optional rushing usage
- role multiplier

Planned analytical features include first-read target share, target share, air-yard share, yards per route run, separation/coverage performance where available, YAC, catch rate over expectation, deep targets, red-zone targets, end-zone targets, and QB/context adjustments.

## Regression

Noisy efficiency rates regress toward league averages. Current default regression strengths are configurable and include:

- catch rate: 30%
- yards per target: 35%
- receiving TD rate: 55%
- yards per carry: 35%
- passing TD rate: 45%
- interception rate: 40%

TD rates are intentionally regressed more aggressively than stable volume metrics.

## Rookies

The engine accepts rookie flags and expands their uncertainty bands. The full rookie feature pipeline still needs to be populated from the dedicated v10 rookie methodology.

Target rookie inputs:

### WR / TE
- draft capital
- college target share / dominator
- yards per route run
- breakout age
- receiving yards per team pass attempt
- early-declare status
- athletic profile
- competition adjustment
- historical NFL comps

### RB
- draft capital
- college workload
- receiving involvement
- yards after contact
- missed tackles forced
- explosive-run rate
- athletic testing
- projected depth-chart role

### QB
- draft capital
- age / experience
- passing efficiency
- pressure performance
- rushing production
- designed-rush profile
- expected starting probability
- historical NFL comps

## Uncertainty

The engine outputs floor, median, and ceiling fantasy points for every scoring format.

Base uncertainty is position specific and expands for:

- rookies
- major role changes
- meaningful injury concerns

The current bands are heuristic and must be calibrated during backtesting. A later simulation layer should replace simple bands with empirical outcome distributions and probabilities such as Top-5, Top-12, Top-24, and Top-36 finishes.

## Fantasy scoring

The engine currently supports:

- Full PPR
- Half PPR
- Standard

Because the model projects actual football statistics first, scoring formats are calculated from the same underlying player projection rather than using three independent models.

## Trade analyzer integration

`projectionTradeValueHook()` creates a normalized projection signal using projected points plus floor/ceiling information.

Important: the hook does **not** currently change trade values. It is designed so we can backtest the projection signal before deciding how much weight it deserves in the production trade analyzer.

A likely future trade-value structure is:

`existing v10 value + rest-of-season projection signal + role trend + schedule + availability`

The exact weights should be learned from historical tests rather than chosen arbitrarily.

## Phase roadmap

### Phase 1 — foundation
- [x] Team-volume projection
- [x] QB projection functions
- [x] RB projection functions
- [x] WR/TE projection functions
- [x] PPR / Half PPR / Standard scoring
- [x] Floor / median / ceiling framework
- [x] Projection rankings
- [x] Trade-analyzer projection hook
- [x] v10 recency and partial-season weighting

### Phase 2 — real data pipeline
- [ ] Build 2023-2025 historical feature table
- [ ] Import current 2026 rosters/depth charts
- [ ] Import team environment assumptions
- [ ] Map v10 analytics fields into projection inputs
- [ ] Import dedicated rookie features
- [ ] Resolve missing-season veterans with prior/role fallback

### Phase 3 — backtest
- [ ] Train/test using historical seasons without look-ahead leakage
- [ ] Measure MAE/RMSE by raw stat and fantasy points
- [ ] Test positional rank accuracy
- [ ] Calibrate regression rates
- [ ] Calibrate uncertainty bands
- [ ] Compare against simple baseline projections

### Phase 4 — 2026 season projections
- [ ] Generate every QB/RB/WR/TE projection
- [ ] Produce Top 200 / Top 250 in all scoring formats
- [ ] Publish player projection cards
- [ ] Add projection explanations to the site

### Phase 5 — in-season model
- [ ] Weekly role updates
- [ ] Opponent matchup adjustments
- [ ] Injuries and depth-chart movement
- [ ] Rest-of-season projections
- [ ] Weekly start/sit rankings
- [ ] Feed validated ROS signal into the trade analyzer
