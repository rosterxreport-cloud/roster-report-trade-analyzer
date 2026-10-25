# Basketball points toolkit

`/basketball/` is isolated from football. It supports ESPN and Yahoo default points scoring and custom weights for 11 counting statistics. Custom double-double/triple-double bonuses and category leagues are not supported in this release.

Rankings are calculated from ESPN full-season projected counting statistics divided by projected games. They are per-game points rankings, not an independent or backtested Roster Report forecast, rest-of-season totals or weekly projections. Yahoo changes scoring weights, not the ESPN projected statistics or position eligibility. Raw ESPN published rank order and editorial text are not imported. Injury-status snapshots appear in ranking rows and trade warnings; per-game values have no additional availability discounts.

Trade packages sum positive points per game above the player at `leagueSize * rosterSize + 1`. This assumes replacement-level roster fills/drops and does not optimize a real lineup. A gap within 5% of the larger package is close. Scoring, league depth and player selections never use football calculations or storage. Browser settings use `rr-basketball-points-v1`; the roster itself is not saved.

## Data contract

`data/basketball/players.json` includes season, retrieval timestamp, numeric-input source hash, source URL, normalized projected season totals, games, current team and ESPN eligibility, status flags, and excluded-player reasons. The timestamp records retrieval, not ESPN's generation time. Missing forecasts/statistics are excluded, never fabricated or converted to zero. Snapshot updates reject malformed totals, duplicate IDs, fewer than 200 usable players and coverage declines over 15% within the same season. The previous snapshot remains untouched on publisher failure.

Refresh: `python3 scripts/refresh-basketball.py`. For replay, pass `--season 2027 --input /path/to/espn-input.json --teams /path/to/espn-teams.json`. Downloaded raw inputs are scratch material and must not include ESPN editorial outlook text in published outputs.

`.github/workflows/refresh-basketball.yml` attempts a daily update at 13:17 UTC and supports manual dispatch. It only commits the basketball JSON after basketball and full-site checks pass. A failed data request, validation or concurrent branch update leaves the published snapshot in place. Vercel's existing main-branch integration builds and publishes the change. There is no live injury-feed guarantee.

Validation: `node --test tests/test-basketball.mjs tests/test-seo.mjs tests/test-app.mjs tests/test-scoring-settings.mjs tests/test-weekly-projections.mjs tests/test-player-profiles.mjs`.

## Provenance for scoring presets

ESPN: https://africa.espn.com/fantasy/basketball/story/_/id/30296896/espn-fantasy-default-points-league-scoring-explained

Yahoo: https://help.yahoo.com/kb/fantasy-basketball/SLN6919.html

All source calculations use the explicit weights in `basketball/model.mjs`, not a provider's precomputed fantasy score. This prevents accidentally importing a different league's scoring system.
