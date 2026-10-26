# Week 7 2026 — unmatched-player investigation

**Status:** 23 unresolved out of 224 projections eligible for teams with available weekly statistical records. 201 matched. The matched-player PPR MAE remains **5.0791**; the full-week MAE is not yet available.

The nflverse weekly offensive statistics feed contains **no Week 7 row** for any of these 23 player/team pairs. The separate nflverse snap-count dataset currently provides Week 7 participation for **NE and CHI only** (Thursday game). It has no matching player row for any of the 23, but this does not establish inactive status or zero points. All 23 remain unresolved rather than being falsely counted as zero.

| Player | Team | Position | Classification |
|---|---|---|---|
| Jawhar Jordan | HOU | RB | No statistical record; playing-time status unverified |
| CJ Donaldson | NO | RB | No statistical record; playing-time status unverified |
| Pierre Strong | GB | RB | No statistical record; playing-time status unverified |
| Lan Larison | NE | RB | No statistical record; playing-time status unverified |
| DJ Herman | MIA | RB | No statistical record; playing-time status unverified |
| Audric Estimé | CLE | RB | No statistical record; playing-time status unverified |
| AJ Dillon | CAR | RB | No statistical record; playing-time status unverified |
| Kaleb Johnson | GB | RB | No statistical record; playing-time status unverified |
| Kalel Mullings | TEN | RB | No statistical record; playing-time status unverified |
| Foster Moreau | HOU | TE | No statistical record; playing-time status unverified |
| Teagan Quitoriano | ARI | TE | No statistical record; playing-time status unverified |
| Marlin Klein | HOU | TE | No statistical record; playing-time status unverified |
| Pharaoh Brown | IND | TE | No statistical record; playing-time status unverified |
| Ben Yurosek | MIN | TE | No statistical record; playing-time status unverified |
| Isaiah Bond | CLE | WR | No statistical record; playing-time status unverified |
| Chris Moore | BAL | WR | No statistical record; playing-time status unverified |
| Tim Patrick | NYJ | WR | No statistical record; playing-time status unverified |
| Devontez Walker | BAL | WR | No statistical record; playing-time status unverified |
| Jackson Meeks | DET | WR | No statistical record; playing-time status unverified |
| Kevin Austin Jr. | NO | WR | No statistical record; playing-time status unverified |
| Deven Thompkins | LV | WR | No statistical record; playing-time status unverified |
| Lewis Bond | HOU | WR | No statistical record; playing-time status unverified |
| Ja'Seem Reed | CAR | WR | No statistical record; playing-time status unverified |

## Resolution and audit policy

- If an updated weekly fantasy-stat row appears, match it by normalized player name and team and use its full-PPR points.
- If a player's **offensive snap count is greater than zero** and there is no corresponding offensive-stat row, record a verified zero-point appearance under the current QB/RB/WR/TE fantasy scoring conventions.
- If neither a stat row nor verified offensive participation exists, exclude the player from MAE and keep the case open. Do not assume the player was inactive or had zero points.
- This remains a **partial** Week 7 report. NFL schedule: Sunday night KC–SEA and Monday night DAL–PHI were missing from the available stats feed when checked.

Calculated from the immutable saved Week 7 pregame snapshot and 2026 nflverse weekly-stat/snap-count sources. The audit is scheduled to refresh as more stat and participation data is released.
