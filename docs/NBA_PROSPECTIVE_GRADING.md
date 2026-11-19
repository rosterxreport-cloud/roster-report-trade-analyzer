# Frozen NBA candidate grading

Sign-in setup is paused at the owner's request. This research workflow is offline and does not depend on accounts or premium authorization. It never grants access or approves a model for publication.

`scripts/pro/grade-nba-candidate.py` verifies all six frozen candidate/control artifacts against their saved SHA256 manifest, checks a matching original forecast, injury evidence and seed, and requires both variants to predate first lock. The November 15 bundle passes verification: 148 players, five games, 10,000 outcomes each, frozen at 18:20:27 UTC (10:20 AM Pacific), first lock at 23:00 UTC (3 PM Pacific).

## Result evidence

Actuals must be normalized from official NBA final box scores. The model uses ESPN player/game identifiers, so the retrieval step must establish and retain an explicit crosswalk to NBA source identifiers. Never match on name alone or assume model and official IDs are interchangeable. Keep the original response bytes and retrieval receipts alongside normalized actuals. A timestamp after tipoff does not establish finality; the official source must explicitly mark the game final.

The input JSON has sport `NBA`, scoring `DraftKings`, an HTTPS nba.com or subdomain `source`, a timezone-aware `capturedAt`, `games`, and `players`:

- Each game: model `gameId`, `status: final`, exact official `source`, SHA256 of raw source bytes, and timezone-aware `verifiedAt` after tipoff and no later than capture.
- Each player: model `id` and `gameId`, `identityVerified: true` after the explicit crosswalk, official `sourcePlayerId`, `status: played` or an explicit official `DNP`, and observed `statline`.
- Required box fields: MIN, PTS, FGM, FGA, FG3M, FG3A, FTM, FTA, REB, AST, STL, BLK, TOV. Counting statistics must be integers; minutes may be fractional. Exact point and makes/attempt identities are enforced.
- DNP requires an explicit source record and all-zero statline. Absent records remain missing, never synthesized as DNP.

Do not set `identityVerified` without checking the crosswalk. The grader checks the normalized evidence contract, not the authenticity of manually asserted source facts. It is not an independent data collector or release-approval authority.

```sh
python scripts/pro/grade-nba-candidate.py --bundle PRIVATE_FROZEN_DIRECTORY --actuals PRIVATE_OFFICIAL_ACTUALS.json --output PRIVATE_GRADE.json
```

## Report interpretation

The output separates played appearances, explicit DNP, and all explicit results. It reports point MAE only for played appearances, simulation mean MAE/bias, CRPS, middle-80% coverage, projected-minutes MAE and paired mean-MAE differences on the same matched cohort. A missing result produces a clearly partial report. No salaries, valid lineup replay, cash rate, payouts or ROI are established.

The existing frozen bundle contains score vectors but not per-draw participation indicators. Therefore DNP probability calibration and conditional-on-playing simulation MAE cannot be computed from it. Zero fantasy points do not reliably imply DNP; those metrics remain unavailable rather than inferred. Existing private simulator audit results remain separate.

Negative paired MAE difference favors the candidate on that exact cohort. One slate, even if complete, cannot establish a durable improvement. Six synthetic tests cover scoring, explicit DNP, missing records, tampered archives, finality/timing, duplicate identities and source restrictions. Empirical grading must wait until the games finish.
