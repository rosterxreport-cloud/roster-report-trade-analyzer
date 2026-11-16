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

## Reproducible release preflight

Run `npm run release:check -- /absolute/private/artifact-root` in the intended deployment environment. It outputs only check names, readiness and safe failure reasons, and exits nonzero if any gate fails. Set RELEASE_COMMIT to the candidate commit and supply dated test receipts in private release-evidence.json for stripeOriginDelivery, authenticatedFreeAndPaidFlows and mobileAndDesktopReview. Each receipt requires passed=true, commit, checkedAt and receipt fields. These are recorded observations, not flags to set without performing the tests.

Running this command in an unconfigured local shell does not inspect Vercel secrets and cannot invalidate the already verified preview billing connection. Missing current private artifacts and missing observations remain explicit blockers. The command does not enable authentication, change models, grant memberships or deploy production.

## Automatic DFS refresh

The new refresh-dfs workflow is scheduled every 30 minutes and supports manual dispatch. It consumes the existing private model pipeline's authenticated HTTPS feed, not a replacement projection model. Its feed contains slates (each with salaryCsv, manifest, model and joint) and nba.basic / nba.distributions in the established artifact schemas. All model outputs, salaries, availability, identity mappings, dates and complete joint arrays must pass the existing validators and produce a feasible advanced lineup before publication.

The runner validates the entire bundle before storage writes. It writes immutable versioned slate objects first and switches each sport's catalog only after the objects exist. Catalog switches are per sport, not a cross-sport database transaction. Failed validation retains the previous published version; expiry rules prevent stale inputs from being used. A storage outage can leave unreferenced new objects, but cannot point a catalog at a not-yet-uploaded slate.

Activation still requires the existing private model generator to expose the feed and secure GitHub dfs-preview environment credentials: DFS_SOURCE_URL and DFS_SUPABASE_URL variables; DFS_SOURCE_TOKEN and DFS_SUPABASE_SERVICE_ROLE_KEY secrets. DFS_AUTOMATION_ENABLED must be true. Credentials must never enter Git or chat. No such source connection was available at implementation time, so automatic publishing is not yet active. GitHub scheduled workflows run from the default branch after review/merge; adding a cron on this development branch does not activate it. Scheduled executions may be delayed; the app still checks expiry at request time. GitHub failed-job notifications provide failure reporting. This workflow does not manufacture missing NFL event/DST or NBA injury inputs, and does not refresh timestamps to revive stale model outputs.

## November 16 runner recovery follow-up

See [PRIVATE_RUNNER_RECOVERY_2026_11_16.md](PRIVATE_RUNNER_RECOVERY_2026_11_16.md) for actual infrastructure observations and execution results. Direct private-host publication from a local bundle is now supported, including a credential-free validation-only mode. A separate feed service is optional. The recovered NBA simulator executed for 239 players × 10,000 draws; its source approval remains false and publication was rejected. The staging gateway is read-only for artifacts. No scheduled model host or real end-to-end publication has been connected. Full application validation now passes 120 tests. Production remains unapproved.
