# DraftKings slate ingestion and backtesting

The public repository contains no proprietary model inputs or current salary substitutes. All operational artifacts belong in private storage. These commands are offline operator tools, never exposed as public upload or publication APIs.

## Required inputs

1. Complete official DraftKings Classic salary CSV with ID, Name, Position, Salary, TeamAbbrev. Names with commas and quoted fields are supported. Do not use a scraped partial player pool as a complete slate.
2. A dated operator manifest: schemaVersion=1, sport, slateId, format="DraftKings Classic", gameIds, completeSalaryPool, publishApproved; salarySource/injurySource/scheduleSource and corresponding CapturedAt timestamps; playerMappings with dkId, modelId, team, opponent, gameId, startsAt, status, verifiedAt. IDs must be mapped explicitly; no fuzzy name joins. Any ownership input requires a source and capture timestamp, expressed as a fraction in [0,1].
3. An RR projection artifact: kind="projections", scoring="DraftKings", matching sport, capturedAt, validUntil, publishApproved, provenance.modelHash/sourceHash, and players with model id, name, team, opponent, gameId, projection. NFL scoring must account for DraftKings-specific scoring; existing generic PPR totals must not silently stand in for this artifact.
4. For advanced optimization, a matching RR joint simulation artifact with exactly 10,000 finite scores per model ID, consistent model hash, source snapshot hash and capture time. Draw indexes must represent the same joint game scenarios across players.

All timestamps require explicit timezones. Injury/availability evidence is valid for at most 90 minutes. Out, inactive, questionable and doubtful players are excluded conservatively; no return-to-play assumption is invented.

```
node scripts/pro/import-slate.mjs --salaries /private/DKSalaries.csv --manifest /private/slate-manifest.json --model /private/basic.json --joint /private/joint.json --decision-at 2026-11-15T01:00:00Z --output /private/slates/SLATE_ID.json
```

The report lists every missing identity, unmodeled active player and stale verification. Incomplete pools or unapproved source models keep publishApproved=false. The importer does not override a research gate. Projection expiry is mandatory and must be after the decision time. A slate expires at the earliest of its source projection expiry, player availability expiry or first game lock; refreshing salary or injury mappings cannot revive an expired model. Store only approved artifacts in the private deployment bucket under nba/slates/SLATE_ID.json or nfl/slates/SLATE_ID.json. The slate listing index is an operator-reviewed {"slates":[{"id":"...","name":"...","locksAt":"..."}]} at nba/slates.json or nfl/slates.json. Model artifacts and indexes are not automatically published by these tools.

## Backtest gate

```
node scripts/pro/backtest-slate.mjs --slate /private/frozen-slate.json --actuals /private/final-results.json --decision-at 2026-11-15T01:00:00Z --output /private/replay-report.json
```

Actuals require matching sport/slateId, scoring="DraftKings", complete=true, source, a final capture time and one finite points result per pool player with matching gameId and status final or DNP. A DNP must explicitly score zero. Optimization receives only the archived pre-decision inputs; actuals are joined afterward. Salary and manifest hashes are mandatory. Optional --options supplies solver controls. Optional --contest supplies a verified, matching-slate source and lastPaidScore/winningScore benchmark.

Reports include player MAE/bias, selected lineup scores, provenance hashes and any margin to verified score benchmarks. Cash rate and ROI remain null because a score comparison is not proof of contest entry or payout. Historical complete-pool datasets are still required before reporting empirical results for the new server optimizer. Unit-test fixtures are explicitly synthetic and are never deployed as current data.

Official rule references: https://lp.draftkings.com/help/rules/nba/classic and https://games.draftkings.com/help/rules/nfl/classic . NBA Classic uses eight slots, a $50,000 cap and at least two games. Only Classic is supported; Showdown and other formats are rejected.
