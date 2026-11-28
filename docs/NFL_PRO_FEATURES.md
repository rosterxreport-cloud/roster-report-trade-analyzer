# NFL Pro feature integration

Development preview adds /nfl/projections-pro/ and a premium weekly-analysis panel to all 307 existing player-profile URLs. Original free content, canonical URLs, rankings, projections and Substack embeds remain. Detailed payloads are requested only after clicking the premium load button and require a verified Pro session on the server. No premium analysis payload is embedded in static HTML.

The new view exposes the published weekly statline, positional PPR rank, projected team target/carry allocation, projected catch rate and yards-per-carry/catch ratios, full-PPR scoring components, source week/date, matchup and published injury/starter notes. These are derived from the existing weekly outputs; allocation is not observed usage, and a ratio is not a newly fitted efficiency model. Existing model parameters are unchanged. Older or missing player forecasts are explicitly reported, never manufactured.

The existing advanced trade view now displays both before and after starting lineups. It continues to use RR trade-value indexes and the current weekly projection impact; no calibrated uncertainty or full weekly rest-of-season forecast is claimed.

Validation: 156 application tests passed (38 existing + 118 Pro). Generated output contains premium panels on all current player pages (313 after syncing the current free release). Protected live GET /api/pro/?action=nfl-details returned HTTP 401 without a user session. The owner confirmed the authenticated premium view using the approved staging-only owner-comp grant. This is not evidence of a genuine paid Stripe subscription flow. The explicit zero-point duplicate placeholder is omitted only from the derived premium view; the positive published forecast remains unchanged. Current Week 11 generation, production publication and signed DFS publication were verified on November 19. The release remains preliminary and uses the original model. See RELEASE_STATUS.md for the exact runtime receipts and schedule-recovery distinction.

Toolkit Pro remains preview-only pending final release approval.
