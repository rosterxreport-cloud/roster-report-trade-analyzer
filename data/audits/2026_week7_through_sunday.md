# Week 7, 2026 — through Sunday Night Football (KC @ SEA final)

**Through-Sunday, matched-player full-PPR MAE: 5.0594 across 217 players.** Week 7 is NOT complete: DAL @ PHI is scheduled for Monday October 26. An additional 23 players from other completed games have unresolved participation / no-stat records and are excluded rather than assigned invented zeroes.

Sources: immutable pregame [2026 Week 7 snapshot](../snapshots/2026_week7.json); 201 previously reconciled weekly-stat player records; [FootballDB KC–SEA completed box score](https://www.footballdb.com/games/boxscore/kansas-city-chiefs-vs-seattle-seahawks-2026102512). The 16 Chiefs/Seahawks rows below were independently scored from passing/rushing/receiving stats under full-PPR, 4-point passing touchdowns, -2 interceptions, -2 lost fumbles. Final: Seattle 20, Kansas City 3.

## Updated cumulative MAE

| Position | Matched players | PPR MAE |
|---|---:|---:|
| QB | 26 | 5.3996 |
| RB | 52 | 5.0975 |
| WR | 90 | 4.9706 |
| TE | 49 | 5.0016 |
| **Overall** | **217** | **5.0594** |

Overall **within 1: 22/217 (10.14%)**; **within 3: 85/217 (39.17%)**; **within 5: 131/217 (60.37%)**. The KC–SEA game alone was 4.8125 MAE (16 players). The previous matched-player audit was 5.0791 across 201.

MAEs above are calculated from prior published four-decimal positional aggregates plus the 16 new exact errors. Accordingly, values are subject to less than 0.0001 rounding uncertainty relative to recomputing directly from all 217 underlying records; this does not meaningfully affect the displayed results.

## KC–SEA: every saved player projection

| Player | Team | Position | Projected PPR | Actual PPR | Absolute error |
|---|---|---|---:|---:|---:|
| Patrick Mahomes | KC | QB | 15.74 | 6.00 | 9.74 |
| Sam Darnold | SEA | QB | 10.33 | 13.98 | 3.65 |
| Kenneth Walker III | KC | RB | 24.65 | 9.70 | 14.95 |
| Emanuel Wilson | SEA | RB | 12.67 | 18.50 | 5.83 |
| George Holani | SEA | RB | 6.48 | 3.30 | 3.18 |
| Emmett Johnson | KC | RB | 3.80 | 3.70 | 0.10 |
| Travis Kelce | KC | TE | 11.27 | 8.40 | 2.87 |
| Noah Gray | KC | TE | 6.97 | 7.40 | 0.43 |
| AJ Barner | SEA | TE | 5.04 | 8.60 | 3.56 |
| Jaxon Smith-Njigba | SEA | WR | 22.56 | 31.30 | 8.74 |
| Xavier Worthy | KC | WR | 12.42 | 4.10 | 8.32 |
| Rashid Shaheed | SEA | WR | 7.43 | 2.10 | 5.33 |
| Cooper Kupp | SEA | WR | 5.30 | 4.00 | 1.30 |
| Tory Horton | SEA | WR | 4.18 | 0.00 | 4.18 |
| Jalen Royals | KC | WR | 3.28 | 0.00 | 3.28 |
| Andrew Armstrong | KC | WR | 2.84 | 1.30 | 1.54 |

The two zero-point players (Horton and Royals) have documented targets in the completed box score; they are not zeroes inferred from absent records.

**Status:** Through-Sunday audit only. Do not label this final full-week MAE until Monday night and 23 unresolved participation records are addressed. The scheduled nflverse audit will rerun when complete weekly stats are released.
