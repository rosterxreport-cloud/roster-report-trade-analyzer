# Official DFS salary recovery — November 15, 2026

The missing-salary-file blocker from the earlier validation was resolved without a user login or user-supplied download. The development GitHub runner successfully retrieved DraftKings' own lobby, draftable pool, Classic rules and bulk salary export. No third-party projections were substituted.

| Dataset | Draft group | Games | Official CSV records | API slot-specific records | Salary-data validation |
|---|---:|---:|---:|---:|---|
| NFL main slate | 156416 | 10 | 514 | 943 | Passed |
| NBA main slate | 156734 | 5 | 175 | 590 | Passed |

Both complete CSVs match every corresponding unique API player. Cross-checks cover export ID, name, team, salary, positions, all eligible roster slots, opponent and scheduled game start. The official rules match supported Classic lineup slots, $50,000 cap and two-game minimum. Slot-specific API records are distinct from unique athletes and are retained in the normalized data; they are not mistaken for extra players. A third-party listing's NBA ID 160791 returned 404; official lobby discovery established 156734.

The final source export receipts were completed at 2026-11-15T17:19:53.602Z (NFL) and 17:19:54.102Z (NBA), before first locks at 18:00Z and 23:00Z respectively. Capture workflow run 43740473918 produced artifact 14171513677. Original response hashes, source URLs, request/receipt times, workflow commit and immutable artifact metadata are retained privately with the data. The original capture artifact is not relied upon as permanent storage.

## Importer correction

The real bulk export is a lineup-entry template followed by an indented salary table, not a bare salary table starting on line one. `parseCsv` now recognizes only the supported NBA/NFL Classic template prefixes, locates one unambiguous salary header, strips the leading template columns, and retains row-width/header/quoting checks. Unknown preambles, duplicate tables and malformed rows fail. Tests include both actual template structures.

## Approval scope

`validateOfficialCapture` produces kind=`official-salary-pool`, salaryDataApproved=true, publishApproved=false. Salary verification does not approve a projection model, assume a player is active, authorize an optimizer run or establish profitability. The normal model, availability and slate-release checks remain in place. A new capture after lock is rejected for pre-lock approval.

Official NBA injury PDF (November 15, noon ET) and NFL Week 10 inactives HTML were also captured successfully. These are preserved as dated sources; the validator does not assert complete final availability from them. The NBA report still lists Dallas as not yet submitted. Today's NBA model snapshot remains research-only and still carries Unknown source availability.

## Research joins

Read-only pairing to the latest recovered RR forecasts found 148 of 175 NBA players and 212 of 514 NFL records, with all other entries explicitly unmatched. Identity uses exact normalized names plus team and matching game/kickoff; NFL additionally checks opponent and position. The existing NBA optimizer's single Alexandre/Alex Sarr alias and NFL LA/LAR team alias are explicitly recorded. There is no fuzzy matching, missing-player zero fill or replacement projection. The NFL feed is PPR, so its DraftKings field remains null. These joins are private research artifacts and do not constitute a release-approved player pool.

The latest recovered NBA bundle is version 50, registered November 15 at 16:45 UTC. Its saved policy audit now has 2,932 matched played player-games across 145 games/19 dates; Yahoo MAE 7.815 and DraftKings MAE 7.789. It still does not meet its existing 200-game review rule. No private model weights changed.

## Reproduction

```sh
node scripts/pro/validate-salary-capture.mjs --directory PRIVATE_CAPTURE_DIRECTORY --sport NFL --group 156416 --output PRIVATE_NFL_POOL.json
node scripts/pro/validate-salary-capture.mjs --directory PRIVATE_CAPTURE_DIRECTORY --sport NBA --group 156734 --output PRIVATE_NBA_POOL.json
python scripts/pro/pair-salary-research.py --pool PRIVATE_APPROVED_SALARY_POOL.json --forecast PRIVATE_FORECAST.json --output PRIVATE_RESEARCH_PAIRING.json
```

The development capture workflow intentionally records these specific November 15 slates. It is not a production recurring feed. Its validation step rejects stale/locked captures. A production feed will need current official-lobby selection, pre-lock refreshes, private storage and model release approval before automatic serving.
