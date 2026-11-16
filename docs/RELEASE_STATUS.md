# Current Toolkit release status — November 16, 2026

This is the current implementation status. Earlier dated audit documents preserve their historical findings; use this document and the owner's latest instructions for release decisions.

| Area | Verified state | Work still required before production |
| --- | --- | --- |
| Existing free application | Original ranking/projection/browser assets and canonical pages are preserved by regression checks. | Final live mobile and desktop review. |
| Dedicated tool pages | Dashboard, NFL/NBA DFS, NBA projections/simulations, Pro trade, membership and Pro pages exist in the development preview. | Review all enabled user flows with real released artifacts. |
| NBA model adapter | Preview shows the unchanged, dated 268-player original-model snapshot, with DK/Yahoo/ESPN selection. | Deliver fresh established-model outputs through approved private storage; the snapshot is not a current DFS slate. |
| DFS backend | NFL/NBA roster/salary, locks/exclusions, stacking, exposure, multi-lineup and CSV constraints are tested. | Release current salaries, explicit player eligibility and compatible established-model inputs. No new model design is authorized. |
| Trade Pro | Published RR values and current-week lineup impact are implemented. | Calibrated trade uncertainty and full weekly rest-of-season forecasts are not supplied by current inputs. Do not invent them. |
| Membership billing | Owner-approved live Stripe webhook targets protected development preview. Signed canonical HTTP replays passed; real runtime key reads account/customer/subscription state. | Verify a Stripe-origin delivery receipt; configure and test production independently after owner approval. |
| Eligible membership plans | Only `monthly5_99usd` and `yearly60usd` qualify. Three current subscribers have active preview grants. Legacy access is revoked and a signed canonical replay confirmed it remains inactive. | Do not restore legacy plans even if Stripe labels an old subscription active. Apple/gift/comp/group beneficiary coverage is not proven. |
| Authentication | Server-side verified-email sessions, refresh/revocation, origin checks and rate limits exist. | Email sender/template/delivery configuration remains blocked on administrator access. AUTH_EMAIL_READY remains false. No sign-in bypass is allowed. |
| Free daily limit | Atomic quota is shared across NFL/NBA and resets at midnight Pacific, with daylight-saving tests and failed-run/idempotency coverage. | Verify the complete authenticated browser flow once email works and a usable current slate is released. |
| Backtesting | Previously recovered research stays separate from the product. | No new profitability claim or verified historical optimizer ROI is established by application tests. |

The owner requested pausing remote administrator sign-in attempts after password, passkey and SSO failures. Continue independent implementation and checks without another login prompt unless explicitly requested. Existing models must remain unchanged. Production has not been approved or deployed.

## Preview request hardening

Browser API calls and the reconciliation schedule use the canonical `/api/pro/` path to avoid redirects. Mutations accept only HTTPS origins explicitly configured by APP_ORIGIN, VERCEL_URL or VERCEL_BRANCH_URL. Arbitrary Host and forwarding headers cannot expand that allowlist. This permits both the exact build URL and Vercel's stable branch URL without admitting unrelated origins.
