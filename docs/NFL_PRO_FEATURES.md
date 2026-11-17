# NFL Pro feature integration

Development preview adds /nfl/projections-pro/ and a premium weekly-analysis panel to all 307 existing player-profile URLs. Original free content, canonical URLs, rankings, projections and Substack embeds remain. Detailed payloads are requested only after clicking the premium load button and require a verified Pro session on the server. No premium analysis payload is embedded in static HTML.

The new view exposes the published weekly statline, positional PPR rank, projected team target/carry allocation, projected catch rate and yards-per-carry/catch ratios, full-PPR scoring components, source week/date, matchup and published injury/starter notes. These are derived from the existing weekly outputs; allocation is not observed usage, and a ratio is not a newly fitted efficiency model. Existing model parameters are unchanged. Older or missing player forecasts are explicitly reported, never manufactured.

The existing advanced trade view now displays both before and after starting lineups. It continues to use RR trade-value indexes and the current weekly projection impact; no calibrated uncertainty or full weekly rest-of-season forecast is claimed.

Validation: 153 application tests passed (38 existing + 115 Pro). Generated output contains premium panels on 307/307 player pages. Protected live GET /api/pro/?action=nfl-details returned HTTP 401 without a user session. The owner confirmed the authenticated premium view using the approved staging-only owner-comp grant. This is not evidence of a genuine paid Stripe subscription flow. The explicit zero-point duplicate placeholder is omitted only from the derived premium view; the positive published forecast remains unchanged. Source publication still depends on the separately approved Tuesday NFL workflow and validation of current inputs; page delivery is not proof that a new weekly forecast has been generated.

Toolkit Pro remains preview-only pending final release approval.
