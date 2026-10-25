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
