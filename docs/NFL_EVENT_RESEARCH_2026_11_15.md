# NFL DFS event extension — research candidate

Implemented a prior-only empirical event extension around the unchanged RR offensive forecasts. It estimates yardage-bonus probabilities from each player's rescaled historical yardage distribution, fumbles from observed opportunity rates, two-point conversions from passing/rushing/target rates, and return/recovery TDs from observed appearances. This is a new experimental policy, not a validated replacement for the original model. It requires four prior recorded appearances and withholds unsupported opportunity/yardage histories instead of adding generic rates.

The existing weekly forecast values are never rewritten. Code: scripts/pro/nfl-event-candidate.py. Frozen player stats contain the actual event fields needed; earlier missing-input findings concerned the published forecast feed, not absence of all historical data.

## Week 9 retrospective check

Used the original saved Sunday pregame CSV, capture 2026-11-08T09:07:42.962904Z, and strictly earlier player histories (Weeks 1–8). Scheduled games already underway at capture are excluded. Player identity is joined using prior-only name/position and a unique player ID, followed by team/opponent/game checks for actuals. Provider corrections may differ from originally available historical records; no untouched prospective accuracy claim is made.

| Position | Matched results | Candidate DK MAE |
|---|---:|---:|
| QB | 22 | 6.355 |
| RB | 47 | 5.406 |
| WR | 32 | 5.600 |
| TE | 43 | 4.144 |
| Overall | 144 | 5.217 |

162 supported candidate forecasts were generated. Only 144 have a uniquely matched recorded actual; the other 18 are not treated as DNP or zero. At the candidate stage 135 rows were excluded: 56 unsupported projected opportunity rates, 49 fewer than four prior appearances, 22 games already started/unmatched at capture, seven unsupported yardage bases, one ambiguous/unmatched identity. These filters substantially reduce WR coverage, so the overall MAE cannot be compared directly with the prior 232-player PPR result or generalized to a complete slate. No historical salary replay, contest entry, payout or profitability is established.

## Defense and correlation work

Added a strict DST scoring adapter requiring event expectations and all seven points-allowed band probabilities. It refuses missing events or distributions that do not sum to one. Points allowed must be attributed to defense/special teams, not blindly copied from the opponent's final score. Rules: https://external.draftkings.com/help/rules/nfl/classic .

Retrieved nflverse play-by-play on November 15 at 20:49 UTC: 24,002 raw rows. The Week 10 training cutoff retains 23,822 rows / 136 games and excludes 180 Week 10 rows. Source: https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2026.parquet ; SHA256 786671a1ef96659e71586274ec4b6a9f822965665fbb95bed69ecc219e151fa9.

Remaining implementation: reconcile DST points-allowed and turnover/return scoring play by play, construct and backtest the DST forecasting policy, and generate/validate correlated game outcomes anchored to the RR offensive means. The scoring adapter alone is not a DST projection model. No independent player draws are passed off as joint simulations. All research outputs retain publishApproved=false; the live NFL DFS release remains gated.

Four new Python checks cover cutoff leakage, empirical bonus thresholds, missing data/support, and event-rate scaling. A JavaScript DST check covers event weights, nonlinear PA expectations and invalid distributions. Raw play-by-play and private candidate records are not shipped with static website files.
