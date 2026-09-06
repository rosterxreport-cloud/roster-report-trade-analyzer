# The Roster Report Trade Analyzer

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

The site reads scoring-specific v10 final values for Half PPR, Full PPR, and Standard.

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
