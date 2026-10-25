# Automated player profiles

This feature extends the existing static SEO build. It does not replace the trade engine, source rankings or weekly forecast model.

## Data and publication

1. Tuesday's existing rankings workflow runs the original formulas with optional calculation capture (`--evidence`). Capturing evidence never changes model outputs. The comparison test checks the inspected upstream implementation across all formats and early/mid-season guardrails.
2. `build-player-evidence.py` resolves GSIS IDs using nflverse rosters, reads verified weekly player statistics and PFR snap counts, and records source URLs, SHA-256 checksums, snapshot times and completed-week coverage. It refuses ambiguous identities, incomplete week coverage, duplicate rows or impossible counting-stat relationships. Online runs select a fully completed scheduled week. A checked local-input mode supports reproducible bootstrap and recovery.
3. `publish-player-profiles.mjs` creates the entire release in memory before writing it. It uses the unchanged browser injury layer and RB premium for displayed default-league values. The initial selection is the first 250 QB/RB/WR/TE players in published Half-PPR rank order; ties retain the published file order. Each GSIS ID receives a permanent slug. Future players leaving that selection retain their URL.
4. Evidence failures retain the prior release and raise a GitHub Actions warning/job summary. Valid rankings updates continue. If published inputs differ from the profile release, static pages visibly label the older snapshot and link to the current analyzer.
5. Projection publication also regenerates profiles from the newest validated forecast. It preserves the forecast's original run time. Profiles never rerun, overwrite or extrapolate the forecast.

No new scheduled ChatGPT task or manual editing is required. Production behavior starts only after the branch is explicitly approved and merged.

## Content integrity

Paragraphs are generated from recorded evidence and position-specific branches. Statistical aggregates and rates use recorded offensive appearances, excluding missed-game zeros. Offense-only snap records missing corresponding counting stats are flagged rather than converted into zero production. Team pass-attempt shares are measured only over the player's recorded games, and are labeled accordingly.

Actual published ranks, positional ranks, model scores and default-league values remain distinct. An overall `999` placeholder is displayed as unranked. The current data contains 237 core players with a published overall rank and 16 provisional/unranked QBs; selecting 250 core players includes 13 of those QBs. This feature does not repair or invent overall rankings.

The initial release has nine players without a verified current-season offensive counting-stat sample. Their pages explain that limit and use available rankings and projection assumptions. They do not fabricate efficiency, trends or injury explanations. Returning-player forecast assumptions remain visible. The first release cannot explain changes against an unavailable earlier profile snapshot; subsequent releases compare saved ranks/scores. Recorded calculation changes describe actual signal/role changes without claiming that correlation proves a causal reason for an overall rank change.

Neutral model defaults are marked unobserved in calculation capture and never used as observed NFL statistics. All initial profiles contain 200–300 analysis words; validation allows modest evidence-driven variation (180–340 words) in later snapshots instead of padding sparse data. Length exceptions are reported by the publisher.

## SEO and rendering

Every `/players/<permanent-slug>/` page includes the full analysis in static HTML, unique metadata, canonical URL, Person/WebPage structured data, source dates, scoring values, internal position links and an analyzer CTA. `/players/` lists all 250 current profiles without JavaScript and adds progressive search. Existing rankings link to available profiles. The sitemap includes all retained URLs. No fictitious dateModified/model-run timestamp is emitted. Sources and their checksums are available in expandable page notes.

No profile JSON is fetched on page view: individual pages remain lightweight. The full release and evidence live in the repository for validation and recovery, not in the public asset-copy list.

## Verification

```
python tests/test-ranking-evidence.py
node --test tests/test-player-profiles.mjs tests/test-seo.mjs tests/test-app.mjs tests/test-scoring-settings.mjs tests/test-weekly-projections.mjs
```

The reference parity test requires Git history containing upstream commit `7c66e8e854d639d8e8b29014eebee07da8e1da45`; CI checks out full history. An explicit `--reference` file is supported for offline snapshot testing.

Bootstrap replay (original files already stored under projection inputs):

```
python scripts/build-player-evidence.py --input-dir data/projections/inputs/week7 --manifest data/projections/2026_week7_run_manifest.json --through-week 6
node scripts/publish-player-profiles.mjs
node scripts/build-seo.mjs
```

Normal online publication:

```
python scripts/build-player-evidence.py --output .profile-candidate/statistics.json
node scripts/publish-player-profiles.mjs --evidence .profile-candidate/statistics.json --ranking-evidence data/ranking-evidence.pending.json --require-fresh
```

The separate feature branch must not publish rankings to main. The rankings refresh job now explicitly requires `refs/heads/main`, preventing the legacy push trigger from running its main-branch publication command on this feature branch.

## Team logos

Profiles and directory cards display current-team logos from the verified ESPN team API URL pattern. No player headshots are collected, stored, rendered, requested or included in Person metadata. JAC/JAX and WAS/WSH aliases resolve to the same verified team logo. Logo requests reserve dimensions, omit outgoing referrers and decode asynchronously. Directory logos load lazily. If a logo is unavailable, a local team abbreviation badge remains visible. The existing rankings, projections and weekly publication safeguards are unchanged.

Logo verification: `node --test tests/test-player-images.mjs`. Tests cover all 250 profiles, reject arbitrary image hosts through an explicit team allowlist, and ensure no headshot URLs or Person image properties are rendered.

## Definitive, evidence-driven editorial voice

The narrative generator lives in `scripts/player-analysis.mjs`. It interprets the existing outputs without changing rankings, trade values, projections or scoring. Each profile leads with a rest-of-season asset verdict, explains workload direction and efficiency, gives a weekly lineup call, and closes with a trade stance and same-position model-price peers.

Rest-of-season tiers use published Half-PPR positional ranks and a 12-team baseline. QB/TE ranks 1–12 are starter tiers; RB/WR ranks 1–24 cover the two starting slots, with 25–36 labeled FLEX/WR3 options. Elite tiers are the top three QB/TEs and top six RB/WRs. Weekly calls use the player's rank among every player of that position in the published PPR forecast, not just the selected profiles. These are transparent editorial rules, not newly fitted model outputs or external market consensus.

Workload comparisons use two disjoint appearance windows, up to three games each, and never missed-game zeros. Expanding/contracting labels require at least a 20% change and at least one carry/target (three pass attempts) per game. Efficiency comparisons require three recorded games and 50 pass attempts, 30 carries or 20 targets by position within the measured analyzer pool. Top/bottom-quarter interpretations refer only to that disclosed pool. Receiving production, interception scoring costs, snap shares and touchdown dependence are calculated directly from the same verified records.

The current projection manifest's verified out overrides suppress lineup starts only when forecast week and original run timestamp match the published forecast. Missing projections never become invented out designations. Returning-player historical inputs and workload assumptions remain conditional. Same-position trade peers are the two nearest default Half-PPR model values, not claims about market pricing or guaranteed one-for-one offers. Rank-movement explanations remain limited to recorded changes; no injury or usage cause is invented.

Shared methodology and repeated disclaimers appear in source notes rather than padding each analysis. Team logos remain unchanged. Verify with `node --test tests/test-player-analysis.mjs tests/test-player-profiles.mjs`.

### Defensive matchup context

`scripts/build-matchup-evidence.py` aggregates the complete nflverse weekly player-stat source, rather than the selected Top 250. The checked-in `data/matchup-evidence.json` records the source URL, SHA-256, season, completed-week boundary, capture time, totals and per-game denominators. Its source checksum must match the player-evidence snapshot. Tuesday profile updates build a candidate matchup snapshot and commit it with the validated profile data. If validation fails, the previous snapshots are restored and rankings may still publish.

Profile matchup sections use QB/RB/WR/TE PPR points allowed per defensive game, position-specific counting stats and efficiency. Rank 1 allows the most; tied ranks share rank. At least three defensive games are required. Favorable/difficult labels mean the top/bottom quartile of ranked defenses by raw PPR points allowed, not a strength-of-schedule-adjusted rating. All opposing players at the position contribute, not only ranked fantasy players.

Leading-WR results use the highest targets per recorded player-stat appearance for the opposing team entering each game. Only earlier weeks determine the role. Week 1, tied leaders and games without a recorded appearance by the identified leader are excluded. At least three qualifying games are needed for a split rank. Only the currently measured leading WR receives this split on their profile. This is not cornerback tracking or shadow coverage data.

Matchup claims are withheld for known outs, retained profiles, absent forecasts/opponents, incomplete metrics or mismatched season/completed-week boundaries. The forecast week must immediately follow the defensive evidence week. Source notes distinguish positional totals from individual forecasts and raw results from opponent-adjusted defensive skill. No model inputs, scoring formulas, projections, trade values or rankings change, and no causal projection effect is claimed.

## Related Substack articles

Profiles render up to three matching articles from `data/related-articles.json`, prioritizing dedicated heading/title matches, then newest dates. Passing full-name mentions are labeled separately. No match produces no section. Outbound links carry placement/player UTM tags and use the existing readable link styles.

`refresh-related-articles.yml` checks the public RSS feed daily and commits new matches, triggering the existing deployment. The standard-library Python indexer reads public feed text only, tolerates omitted name suffixes, retains older indexed articles outside the feed window, and fails without overwriting the index when the feed is unavailable. Paywalled text, image-only mentions, initials and nicknames may not match. Initial verified metadata covers the five dedicated sections in the October 22 buy-low article. The daily refresh needs a successful GitHub Actions run to verify live feed access; local access returned an unavailable response.
