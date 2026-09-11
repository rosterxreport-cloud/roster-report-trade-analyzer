# The Roster Report Trade Analyzer

## Tier 0 acquisition premium

Trade evaluation adds 10% to Jahmyr Gibbs's and Bijan Robinson's adjusted contribution, after the existing consolidation multiplier or replacement-level/package discount. It applies symmetrically on either trade side and only to those players' contributions, not their teammates. A single-player offer therefore costs 110% of its previous adjusted trade value. Both can receive the premium in a package. Results display “Elite Asset Premium applied.” when a positive premium is included. Source scores, displayed rankings, raw sums, and lineup-fit values are unchanged; evaluations never mutate player records.

## Team Needs & Trade Targets

The panel below My Team updates from the saved roster, scoring, league size, and lineup slots, including Superflex. It compares average starter values per slot group against a benchmark built by allocating the available Top 250 across league-wide starting slots (restricted positions first, then FLEX, then SF). Empty slots take priority, followed by the largest positive average shortfall. Unsupported benchmark groups are marked unavailable instead of assigned an invented baseline. Bench backup concerns are reported separately.

Targets are lower-, middle-, and upper-value options among eligible players outside the entered roster who improve its optimal starting lineup. Add-only gains assume no outgoing players. For each target, one- and two-player offers are checked against the complete resulting lineup and the existing trade engine, including Tier 0 acquisition premiums. Only offers strictly inside the 4% fair-trade band, with a positive lineup gain and no additional empty slots, are suggested. Among these, the greatest lineup gain wins, with trade-value closeness breaking ties. This is a limited search, not a guarantee of the best possible trade.

Packages are withheld for incomplete starting lineups, over-capacity rosters, or unknown saved players. Opponent rosters and availability are unknown; suggestions do not imply the other manager will accept. Evaluate Trade loads a proposal into the analyzer without modifying the saved roster or sending an offer. Recommendations use model values, not projected fantasy points. Results are cached until saved team settings, roster, or scoring changes.

A deployable static website powered by the Roster Report Trade Analyzer v10 rankings.

Includes Top 250 Redraft Rankings with the subtitle “The Roster Report v10 Model • Full PPR, Half PPR & Standard.” Both scoring controls update the rankings and analyzer together using the existing player data. The main tool remains Fantasy Football Trade Analyzer.

The repository currently contains no official Roster Report logo asset; the existing RR brand mark is retained until the actual logo is supplied.

## Run locally

Because the app loads `players.json`, run it from a local web server rather than opening `index.html` directly.

Python:
```bash
python3 -m http.server 8000
```

Then open http://localhost:8000.

## Deploy free for testing

### Vercel
1. Go to Vercel.
2. Create a new project / use Vercel Drop.
3. Upload this entire folder.
4. No build command is needed; this is a static site.

### GitHub Pages
Commit the files to a repository, then enable Pages for the repository's root branch.

## Model

Veterans:
- 45% AW rankings
- 35% Roster Report 2023–2025 analytics
- 10% positional scarcity
- 10% market/trade value

The site reads scoring-specific v10 final values for Half PPR, Full PPR, and Standard. All 32 current primary kickers and all 32 team defenses are searchable. K and D/ST use separate, deliberately compressed replacement-level models and never enter the QB/RB/WR/TE analytics formula.

## League Scoring Settings

Users can layer custom passing-yard, passing/rushing/receiving touchdown, rushing/receiving first-down, documented 40+/50+ touchdown bonus, and TE-reception-premium scoring onto the selected Half-PPR, Full-PPR, or Standard baseline. Default settings bypass the layer and return the exact live values. Active settings use `scoring-profiles.json`, cap each player's scoring-driven change at ±10%, rerank dynamically, and preserve the base rank/value internally. Players with missing inputs receive no adjustment for that field.

The calculation order is: live Roster Report value (including the existing RB premium) → custom scoring adjustment → existing Superflex QB scarcity → existing trade-package and Tier 0 adjustments. Settings persist only in the user's browser and can be reset to defaults.

## 2026 in-season refresh

`.github/workflows/refresh-2026-player-data.yml` runs on alternating ISO weeks and with `workflow_dispatch`. It reads the latest nflverse 2026 player/team data, moves only the current-season portion of the locked 35% analytics component, rebuilds all three scoring formats, refreshes documented scoring profiles, and rechecks every primary kicker against PFN's current all-team depth chart. AW inputs, veteran and rookie pathways, Superflex behavior, trade-engine thresholds, and the Tier 0 Bijan Robinson/Jahmyr Gibbs premium are not rewritten.

Publishing is fail closed. The workflow will not commit if source columns, schemas, values, core Top 250 coverage, uniqueness, or 32-team K/D/ST coverage are invalid. Each run uploads `refresh-summary.md` with ranking movers, kicker changes, warnings, and update status. A validated `players.json` change is committed to `main`, which triggers the existing Vercel deployment.

Rookies retain the dedicated v10 rookie pathway used in the source rankings.

## Fantasy starting-RB premium

After loading the source v10 values, the app applies a 3% premium to fantasy RB1–12 and 1.5% to RB13–24 in each scoring format. Eligibility follows unadjusted model value, with original overall rank breaking ties; the source `posRank` is not used. RB25 onward and other positions retain their values. Premium values are rounded to two decimals and overall rankings are recalculated. Values may exceed 100 to preserve the full premium and ordering among elite backs.

The same adjusted records power search, Top 250 rankings, and trade calculations. The premium does not modify the source analytics, weights, or `players.json`. The premium is applied once before the existing trade-package calculation (including its elite thresholds). Base values are retained to prevent compounding if the transformation is reapplied. Updating the source data automatically recalculates eligibility on the next page load.

## Trade package adjustment

The website applies a transparent roster-aware calculation after player values are loaded:
- Best player on each side counts at full value.
- Modest elite consolidation premium: 5% at 95+, 3% at 90–94.99, 1.5% at 85–89.99.
- Additional players count only for value above a 50-point replacement baseline.
- Marginal multipliers decline by roster slot: 70%, 45%, 30%, 20%, then lower for larger packages.
- Within ±4% adjusted value = Fair Trade.

These thresholds live in `app.js` and can be tuned without changing the player-ranking model.

## Player data source

`players.json` imports all 250 rows from each of the Half-PPR, Full-PPR, and Standard sheets in `Roster_Report_Trade_Analyzer_Top_250_v10_Analytics_Audit.xlsx`. Workbook Final Score maps to the base `value`; missing Analytics Rating remains null. Workbook ranks and supporting fields are preserved. The existing browser-side RB premium and trade-package adjustments are applied after loading these base values.

## Superflex roster slot and QB scarcity

My Team supports Superflex (SF), eligible for QB, RB, WR, or TE. SF is a roster slot, never a player position. It defaults to zero; older saved teams migrate with zero SF slots. Dedicated positions fill first, followed by FLEX and then SF, without using a player twice.

Saving one or more SF slots enables a model-based QB scarcity premium across search, rankings, trades, and lineup comparisons in all three scoring formats. Starting QB demand is `min(32, leagueSize * (QB slots + SF slots))`. The starter premium is `min(0.40, 0.20 * leagueSize * SF slots / 12)`. Each QB receives this premium multiplied by `min(1, demand / QB model rank)`, using the current scoring format's QB value order. Thus a 12-team, 1-QB, 1-SF league gives QB1–24 a 20% premium, tapering beyond QB24. This is a configurable scarcity assumption, not an externally sourced Superflex market ranking.

Values are rounded to two decimals and overall ranks are recalculated. The adjustment always starts from the unchanged database after the existing RB premium; it never compounds across saves, reloads, or scoring changes. Saving zero SF slots restores the standard values exactly. Selected trade players refresh when settings change. Workbook data, player positions, scoring formats, RB premiums, package discounts, elite thresholds, and verdict boundaries are unchanged.

