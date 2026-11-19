# Established-model DFS integration — November 16, 2026

This supersedes earlier statements that the incumbent NBA model needs another owner approval. The owner explicitly delegated that approval on November 16. Production deployment remains separately unapproved.

## Implemented and verified

- NBA release authorization is pinned to the incumbent shared-preseason25-v1 fingerprint, feature policy and six existing private simulator/scoring dependency hashes. The source files remain private. Export authorization records the original source approval flag separately; it never edits forecasts or revives timestamps. Experimental source changes fail authorization.
- Real export: 239 players × 10,000 joint draws. Approved export player records exactly match the earlier unchanged export, including the original capture timestamp.
- NFL publication requires the established weekly structural v4 lineage. The current recorded model hash matches scripts/projection_week10_league_v4.py exactly. This is the existing weekly generator, not the unrelated next-season model fitting workflow.
- The NFL adapter consumes the published weekly JSON and its run manifest, preserves every supplied statline and Standard/Half-PPR/PPR total, and applies DraftKings scoring only from explicit existing-model event/bonus supplements. DST must come from supplied existing RR defense forecasts. No candidate-model imports, new fitting, zero-filled missing fields or fabricated bonuses are used.
- NBA/NFL refreshes can be selected independently through bundle.sports. Failure or absence of the other sport no longer blocks a selected sport. The entire selected bundle still validates before any write.
- Basic DFS no longer requires joint draws. Advanced optimization continues to require matching complete simulations.
- Current official salary discovery selects upcoming supported multi-game Classic slates, retrieves their full CSV/API/rules/lobby evidence, and cross-checks the complete pool. Historical fixed group IDs are no longer the only capture path.
- Real captures passed: NBA group 156745, 244 players, seven games, November 16 4 p.m. Pacific first lock; NFL group 156561, 504 players, November 22 10 a.m. Pacific first lock. Salary approval is independent of model/availability approval.

## Commands

```sh
node scripts/pro/capture-current-salaries.mjs NBA /private/nba-capture
node scripts/pro/capture-current-salaries.mjs NFL /private/nfl-capture
python scripts/pro/export-nba.py --model-dir /private/existing-nba-model --snapshot /private/current-snapshot.json --output /private/nba-artifacts --release-policy config/nba-incumbent-release.json
node scripts/pro/export-nfl-weekly.mjs /private/weekly.json /private/weekly-run-manifest.json /private/existing-rr-dk-evidence.json /private/nfl-basic.json
node scripts/pro/refresh-dfs.mjs --bundle /private/refresh-bundle.json --validate-only
```

NFL bundles may supply weekly, weeklyManifest and scoringEvidence directly instead of an already adapted model. The source hash and model lineage are checked before publication.

## Validation and remaining operational work

126 application tests pass (38 legacy + 88 Pro), plus four Python authorization tests. Tests include experimental-model rejection despite approval flags, independent sport refresh, basic versus advanced inputs, unchanged NFL means, explicit DK scoring, current-slate discovery, stale rejection and failed-upload behavior. Private NBA source hashes and real salary captures were checked separately.

The DFS integration code is implemented; a live automatically published slate has not been demonstrated. A durable scheduled execution service and its narrowly scoped publishing identity are still not provisioned. The existing staging gateway permits artifact reads only. Current availability evidence and explicit complete identity mappings still need to be assembled. A diagnostic name/team comparison found 41 unmatched NBA salary records, including aliases and players absent from the incumbent snapshot; these are not silently assigned projections or claimed inactive. This diagnostic is not an approved identity join.

The retrieved NFL Sunday salaries belong to the upcoming week; the recovered published forecast is Week 10. A matching established-model forecast must be generated through the normal weekly process. Missing DraftKings event/bonus, DST and matching joint inputs remain explicit; experimental replacements are not authorized.

No production deployment, authentication bypass, fabricated readiness receipt or automatic-refresh activation occurred. Email delivery, Stripe-origin receipt and authenticated browser flows remain open.
