# Roster Report — Week 7, 2026 projection audit (preliminary)

Source: saved published `data/weekly-projections.json` and nflverse weekly player stats. Calculated October 25, 2026, after Sunday's completed games.

**201 matched players; overall PPR MAE: 5.0791.** 224 projections were eligible for teams with available game statistics; 23 have no matching individual statistical record. 89.73% match coverage; 4 teams' games not yet represented (DAL, KC, PHI, SEA). Do not report as final full-week MAE.

| Position | Matched | MAE | Projected minus actual | Within ±1 | Within ±3 | Within ±5 |
|---|---:|---:|---:|---:|---:|---:|
| Overall | 201 | 5.0791 | -0.3145 | 9.95% | 39.80% | 60.20% |
| QB | 24 | 5.2917 | -0.2767 | 8.33% | 37.50% | 62.50% |
| RB | 48 | 5.0210 | -1.4165 | 6.25% | 39.58% | 60.42% |
| WR | 83 | 4.9960 | +0.5184 | 12.05% | 43.37% | 59.04% |
| TE | 46 | 5.1787 | -0.6874 | 10.87% | 34.78% | 60.87% |

## Largest errors (projected → actual PPR)
- Tony Pollard, RB: 10.99 → 36.50 (25.51)
- Mason Taylor, TE: 4.38 → 25.20 (20.82)
- Zay Flowers, WR: 10.63 → 27.70 (17.07)
- Bo Nix, QB: 9.96 → 26.18 (16.22)
- KC Concepcion, WR: 7.00 → 23.20 (16.20)
- Omar Cooper Jr., WR: 6.51 → 22.50 (15.99)
- Davis Allen, TE: 2.13 → 18.00 (15.87)
- Bryce Young, QB: 21.11 → 5.42 (15.69)
- Tee Higgins, WR: 12.29 → 26.80 (14.51)
- Sam LaPorta, TE: 16.72 → 2.80 (13.92)

### Audit controls
Weekly results should be reconciled when all games finish. Unmatched records are listed as unresolved, **never silently assigned zero**. Scoring was cross-checked against the nflverse fantasy_points_ppr column (zero deviations in the currently available offensive player records). No projection model or trade-engine code was altered.
