# Model/data review and billing staging

This review does not approve production deployment or change sign-in readiness.

| Component | Decision | Evidence / remaining requirement |
|---|---|---|
| Official November 15 salary captures | Approved as frozen pre-lock salary evidence | NFL 514 / NBA 175 complete player records, official API/rules/CSV cross-checks. Historical capture approval does not establish current freshness or model approval. |
| Original NBA 25% preseason policy | Research only | Current Library version 50: 2,932 played player-games, 145 games, 19 dates. Predeclared minimum is 200 games under the same policy; policies cannot be pooled to meet it. DNP calibration remains unverified. |
| New NBA shooting candidate | Research only | 148 players / five games / 10,000 draws; hash verification passed. Prospective grading must wait for final results; minutes/per-minute and DNP limitations remain. |
| Updated official NBA injury report | Verified source facts, incomplete active pool | Retrieved 3:15 PM Eastern report, exact PDF SHA256 d1aa215e326e5b60a37514f876b9b7838c8f0b7f27f1f35b34e6e6f628b63968. Recovered parser matches 39 statuses in the selected main slate; Dallas submitted, no pending matched team reports. 109 players still have no explicit matched status. No absence-from-report inference of active status. |
| NFL DFS projections | Blocked | All 295 source rows reconcile baseline scoring, but required modeled DK events/probabilities, proprietary DST and approved joint draws remain absent. Identity/availability/opportunity issues remain documented. No free projection values changed. |
| Billing account configuration | Staged in development Preview only | Connected Stripe account and live-mode setting installed for feat/toolkit-pro-platform. Runtime read key, signed webhook, independent publication/price mapping and non-Stripe subscriber coverage remain unverified. Synchronization stays false. |

The private injury review is separate from the immutable 10:20 AM Pacific candidate; neither source forecast nor frozen candidate was overwritten. The newer report is evidence for a future refresh, not an amendment to a prior forecast.

## Billing activation

The connected Stripe service permits account inspection but does not expose a runtime restricted-key creation API. It is not a substitute for the server's Stripe credential. The runtime needs a dedicated restricted read key for account/customer/subscription verification, stored as a Vercel Secret, and the signing secret from the actual webhook endpoint. Never put either in chat, Git or public output.

No existing Stripe webhook endpoints were present at review. Do not enable a live webhook targeting the protected development preview or the not-yet-deployed production API. It must have a stable, publicly reachable receiver, signature verification, matching API version and lifecycle/invoice/customer events before activation. Existing customer subscriptions and payments were not changed.

Billing code now refuses activation without a signing secret, nonempty price allowlist, valid account, explicit mode, and matching key mode. Status uses the same validation so setting the verification flag alone cannot report billing ready. Public publication metadata retrieval is attempted separately to resolve the mapping without asking the owner to gather subscriber files.

For Substack Apple/gift/group/complimentary coverage, require an authoritative publisher-side reconciliation source. Do not infer that absent Stripe subscriptions mean no paid membership.

## Follow-up evidence

The three public Substack requests from the one-time GitHub capture returned HTTP 403 bot challenges. No publication mapping was accepted from those pages and automatic retries are disabled. Receipt artifact 14179686464, run 43759176834, digest f45c10261f6ffee72e5585f285aef406e96ddab0ac058323bfd75e70b57dd0e0 preserves that result.

Read-only Stripe review confirms four active Substack-application subscriptions: three on monthly5_99usd and one on a legacy price. The three current-plan invoice records are paid but carry generic plan names and no publication-specific metadata. These facts establish visibility, not authoritative mapping of both plans to this publication or comprehensive subscriber coverage. No subscriber emails or invoice bodies were copied into Git.

Latest local application suite: 100 passing checks. Preview status returns accountsConfigured=true, backendVerified=true, emailSignInReady=false and billingVerified=false, matching staged configuration. Production is unchanged.
