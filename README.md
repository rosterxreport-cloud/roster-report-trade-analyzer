# The Roster Report Trade Analyzer

A deployable static website powered by the Roster Report Trade Analyzer v7 rankings.

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

The site reads scoring-specific v7 final values for Half PPR, Full PPR, and Standard.

Rookies retain the dedicated v7 rookie pathway used in the source rankings.

## Trade package adjustment

The website applies a transparent roster-aware calculation after player values are loaded:
- Best player on each side counts at full value.
- Modest elite consolidation premium: 5% at 95+, 3% at 90–94.99, 1.5% at 85–89.99.
- Additional players count only for value above a 50-point replacement baseline.
- Marginal multipliers decline by roster slot: 70%, 45%, 30%, 20%, then lower for larger packages.
- Within ±4% adjusted value = Fair Trade.

These thresholds live in `app.js` and can be tuned without changing the player-ranking model.
