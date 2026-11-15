# Development finalization — November 15, 2026

Production has not been promoted. Existing routes, rankings, projections, player pages, SEO and Substack embeds remain preserved.

## Membership verification

Added canonical Stripe lifecycle coverage for deleted customers, changed customer emails, invoice subscription references, event retries and deduplication, historical backfill and cancellation/failed-payment reconciliation. Access expiry follows the allowlisted subscription item's paid period and explicit cancellation date; unrelated mixed-interval items cannot extend access. Webhook signature verification now preserves raw UTF-8 bytes across stream chunks.

The production webhook must include customer.updated and customer.deleted in addition to subscription lifecycle and invoice events. These changes have only been exercised against synthetic fixtures; no real entitlements were granted or billing records changed.

## NBA prospective research

Frozen at 18:20:27 UTC, before the official 23:00 UTC first lock: 148 players, five games, 10,000 joint outcomes per player. A paired incumbent shooting-policy control shares the same injury evidence, calibration and seed. The existing historical shooting guard suppresses five unsupported attempt categories; this remains a research assumption to grade after final results, not a proven improvement. Structural checks passed and artifact hash was verified.

The original forecast archive is unchanged. Private candidate, control and grading plan are retained separately in Roster_Report_NBA_Prospective_Candidate_2026_11_15.zip. All outputs retain publishApproved=false. Availability includes 116 Unknown players and a pending Dallas report; this is not an approved playable slate.

Three dated player examples appear on NBA projections/simulations only when VERCEL_ENV=preview. A whitelist excludes private model fields and joint outcome arrays. Production builds remove the example payload and sections. The full simulation API remains gated by authentication, membership and approved data.

## Checks and release gates

Local npm test passed: 38 legacy checks and 56 platform checks, 94 total. Includes server-side access, atomic Pacific-day quota, roster/salary constraints, membership lifecycle and preview-only publication checks. Historical accuracy results remain documented separately; no optimizer profit or ROI is claimed.

Still required before production approval:

- Configure reliable authenticated email delivery and enable the sign-in readiness gate.
- Install runtime Stripe read credentials and a signed webhook securely; independently confirm publication mapping and coverage of Apple/gift/group/comp subscriptions before enabling synchronization.
- Complete NBA historical review and prospective grading, resolve availability, and approve the model/slate artifacts.
- Complete NFL DraftKings scoring/DST and approved joint simulation inputs; preserve the existing free projections in the meantime.
- Verify the deployed preview and required CI checks. Request production approval only after release gates are satisfied.

## Continuation with sign-in paused

Owner requested continued work excluding sign-in setup. Email delivery and authentication readiness remain unchanged. All checks on commit b8cd535 passed, including the research-validation CI job.

Added immutable candidate/control grading with official final-game evidence, explicit NBA/source ID crosswalk requirements, exact observed scoring, partial-result handling and separate played/DNP cohorts. The frozen November 15 bundle passed hash and pre-lock verification. Empirical results must wait for final games; no prospective accuracy is asserted. See [grading contract and limitations](NBA_PROSPECTIVE_GRADING.md).

Added a pure NFL DraftKings scoring adapter and integrated it into the read-only feed audit. It requires RR-modeled event counts and yardage-threshold probabilities; it never derives bonuses by thresholding mean yards or assigns absent inputs zero. Missing or invalid rows retain null DK scores. DST modeling, feed integrity, availability and joint simulations remain separate release gates. Existing free forecast data is unchanged.

Continuation validation: 99 application tests passed (38 legacy + 61 platform), plus 15 Python research checks (six candidate grading, four simulation, two historical shooting, three NFL archive). The unchanged 295-row NFL feed reconciles baseline scoring but all 295 DK scores remain withheld for missing modeled event inputs. No forecast values or membership settings were altered.
