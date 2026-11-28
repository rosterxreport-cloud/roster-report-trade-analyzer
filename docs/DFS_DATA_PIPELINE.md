# DraftKings slate ingestion and backtesting

The public repository contains no proprietary model inputs or current salary substitutes. All operational artifacts belong in private storage. The scheduled staging runner retrieves and assembles the operational inputs automatically. The CLI examples below remain recovery and audit tools; routine operation does not require uploads. Private model source has no public upload/download route.

## Active staging automation

Supabase cron runs every 30 minutes through the authenticated one-use `dfs-schedule` relay. It invokes the preview-only private runner, which resumes the persistent Vercel sandbox and executes `scripts/pro/run-private-dfs.py`. The established NBA model is unchanged; its forecast date comes from the upcoming official salary slate. NFL consumes the final published weekly JSON/CSV from the same commit. The separate older GitHub feed workflow is gated and inactive.

A scoped `dfs-publisher` validates and writes private artifacts. Model outputs, salaries, identity mappings, official availability and simulations are retrieved/generated without manual uploads. Missing current inputs yield a per-sport blocked/waiting receipt; they do not authorize estimated replacements. See [RELEASE_STATUS.md](RELEASE_STATUS.md) for actual executions and limitations.

## Required inputs

1. Complete official DraftKings Classic salary CSV with ID, Name, Position, Salary, TeamAbbrev. Names with commas and quoted fields are supported. Do not use a scraped partial player pool as a complete slate.
2. A dated operator manifest: schemaVersion=1, sport, slateId, format="DraftKings Classic", gameIds, completeSalaryPool, publishApproved; salarySource/injurySource/scheduleSource and corresponding CapturedAt timestamps; playerMappings with dkId, modelId, team, opponent, gameId, startsAt, status, verifiedAt. IDs must be mapped explicitly; no fuzzy name joins. Any ownership input requires a source and capture timestamp, expressed as a fraction in [0,1].
3. An RR projection artifact: kind="projections", scoring="DraftKings", matching sport, capturedAt, validUntil, publishApproved, provenance.modelHash/sourceHash, and players with model id, name, team, opponent, gameId, projection. NFL may instead declare `scoring="RR-DK-core"` for the recovered original RR PPR/interception adapter, with its omitted events disclosed. It must not be labelled complete DraftKings scoring.
4. For simulation-based NBA upside optimization, a matching RR joint simulation artifact with exactly 10,000 finite scores per model ID, consistent model hash, source snapshot hash and capture time. Draw indexes must represent the same joint game scenarios across players.

All timestamps require explicit timezones. Injury/availability evidence is valid for at most 90 minutes. Out, inactive, questionable and doubtful players are excluded conservatively; no return-to-play assumption is invented.

```
node scripts/pro/import-slate.mjs --salaries /private/DKSalaries.csv --manifest /private/slate-manifest.json --model /private/basic.json --joint /private/joint.json --decision-at 2026-11-15T01:00:00Z --output /private/slates/SLATE_ID.json
```

The report lists every missing identity, unmodeled active player and stale verification. Incomplete pools or unapproved source models keep publishApproved=false. The importer does not override a research gate. The owner-approved incumbent NBA release is distinct from experimental research. NFL projection-based controls can run without fabricated joint simulations. Projection expiry is mandatory and must be after the decision time. A slate expires at the earliest of its source projection expiry, player availability expiry or first game lock; refreshing salary or injury mappings cannot revive an expired model. Store only approved artifacts in the private deployment bucket under nba/slates/SLATE_ID.json or nfl/slates/SLATE_ID.json. The automatic runner validates all inputs, uploads versioned slate objects and then updates the {"slates":[{"id":"...","name":"...","locksAt":"..."}]} catalog at nba/slates.json or nfl/slates.json. A failure leaves the previous catalog intact; the application still rejects its expired entries.

## Backtest gate

```
node scripts/pro/backtest-slate.mjs --slate /private/frozen-slate.json --actuals /private/final-results.json --decision-at 2026-11-15T01:00:00Z --output /private/replay-report.json
```

Actuals require matching sport/slateId, scoring="DraftKings", complete=true, source, a final capture time and one finite points result per pool player with matching gameId and status final or DNP. A DNP must explicitly score zero. Optimization receives only the archived pre-decision inputs; actuals are joined afterward. Salary and manifest hashes are mandatory. Optional --options supplies solver controls. Optional --contest supplies a verified, matching-slate source and lastPaidScore/winningScore benchmark.

Reports include player MAE/bias, selected lineup scores, provenance hashes and any margin to verified score benchmarks. Cash rate and ROI remain null because a score comparison is not proof of contest entry or payout. Historical complete-pool datasets are still required before reporting empirical results for the new server optimizer. Unit-test fixtures are explicitly synthetic and are never deployed as current data.

Official rule references: https://lp.draftkings.com/help/rules/nba/classic and https://games.draftkings.com/help/rules/nfl/classic . NBA Classic uses eight slots, a $50,000 cap and at least two games. Only Classic is supported; Showdown and other formats are rejected.

### Weekly NBA roster projections

For a Monday–Sunday Pacific week, collect seven dated schedule captures and the current player/team roster. A game with unresolved teams blocks the weekly package. Run the incumbent privately and use the approved daily basic releases as inputs. The weekly builder uses the existing pinned release policy and preserves the source statlines and capture dates.

Run `node scripts/pro/build-nba-roster-weekly.mjs manifest.json output.json daily-basic.json [more daily files]`. The manifest contains `weekStart`, `games` (id, startsAt, home, away), `scheduleDays` (day, gameIds, sourceHash, including empty days), and `roster` (id, team). Optional `absences` rows contain id, gameId, asOf and evidenceHash for confirmed absences. Missing player forecasts on scheduled dates stay uncovered. All scheduled games must have forecast coverage.

The staging publisher and gateway must run versions that admit only the exact additional object path `nba/roster-weekly.json`. The weekly artifact expires by first tipoff. Publish through the existing private publisher and verify the stored object and a signed-in Pro comparison before describing the release as available.
