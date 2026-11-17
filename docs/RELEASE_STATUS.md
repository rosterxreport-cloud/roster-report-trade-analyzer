# Current Toolkit release status — November 16, 2026 (Pacific)

This document supersedes earlier dated implementation claims. Production remains unapproved and unchanged. Development branch: `feat/toolkit-pro-platform`; draft PR #45.

| Area | Verified state | Remaining release requirement |
| --- | --- | --- |
| Free Toolkit | Existing rankings, projections, player pages, SEO assets and Substack embeds pass regression checks. | Final live desktop/mobile review. |
| Dedicated tools | Dashboard, NBA/NFL DFS, NBA projections/simulations, Pro trade and account pages remain inside the Toolkit. | Authenticated free/paid browser tests after email delivery is configured. |
| NBA model | The owner delegated incumbent approval. The pinned established `shared-preseason25-v1` model runs privately, with 10,000 simulations; no projection formula was changed. | Current slate publication continues to require verified salaries, identity joins and official availability. A successful past run does not make its now-locked slate usable. |
| NFL model | DFS reads the actual final published weekly JSON and matching CSV from the same main-branch commit. All 295 current Week 10 rows match exactly. The original weekly projections are preserved. | Current salary/DST sources have advanced beyond Week 10. Matching final weekly projections are required; stale Week 10 values are never relabelled. |
| DFS scoring | Original NBA model scoring is preserved. NFL uses the recovered original RR PPR/interception core adapter and separately attributed DST source, with omitted scoring events disclosed as `RR-DK-core`. | Full NFL event simulations and omitted DK scoring components are not fabricated or claimed complete. |
| Optimization | Roster/salary constraints, locks, exclusions, stacks, exposure, multiple lineups and CSV export are tested. NFL projection controls do not require invented joint outcomes; NBA upside requires the real 10,000 draws. | Bounded beam search does not establish mathematical optimality or profitability. |
| Automatic refresh | **Active in staging:** Supabase cron invokes a signed relay every 30 minutes. Real scheduled executions have run the private model and published NBA projections, simulations and a usable slate. | NFL publication waits for matching weekly inputs; NBA future slates wait for complete availability/feasibility checks. Monitor per-sport receipts rather than HTTP status alone. |
| Billing | Current eligible Stripe plans remain `monthly5_99usd` and `yearly60usd`; legacy grants remain revoked. Signed canonical replays and runtime reads passed previously. | Genuine Stripe-origin delivery still needs verification. Apple/gift/comp/group beneficiary coverage is not established. Charges/subscriptions have not been modified. |
| Email authentication | Verified-email sessions, revocation, rate limits and canonical origin controls exist. | Sender/template/delivery configuration is incomplete; `AUTH_EMAIL_READY` remains false. No authenticated browser sign-in is claimed. |
| Daily free lineup | One basic lineup per Pacific day, shared across NBA and NFL, with atomic quota/idempotency coverage. | Verify the real authenticated free and paid user flows after email is configured. |
| Trade Pro | Uses published RR values and current-week lineup impact. | Calibrated uncertainty and complete weekly rest-of-season forecasts remain unavailable. |

## Private execution and secure publishing

The existing private model is hosted in the persistent named Vercel sandbox `toolkit-pro-dfs-runner`. Its source stays outside the public repository. A preview-only authenticated route resumes it, checks out the deployed public integration revision, executes the fixed worker and stops/snapshots the sandbox. A database lease prevents overlapping jobs.

The staging `dfs-publisher` Edge function owns storage credentials and validates publication paths, lineage, freshness, scoring, distributions and slate/catalog references. The worker receives only its scoped publishing capability. Validation precedes publication; versioned slate objects are uploaded before discovery catalogs switch. Catalog publication is per sport. Failure can leave unreferenced objects but cannot point a catalog at a missing object. Expiry remains enforced at request time.

The staging cron job `dfs-established-staging-refresh` is active on `*/30 * * * *`. Its `pg_net` requests contain only a one-use HMAC proof valid for 90 seconds. Permanent runner authentication and the dedicated preview bypass stay in Vault and enter the outbound request only in Edge memory. They were rotated after the initial connectivity test; the separate Stripe webhook bypass was preserved. Public and signed-in roles cannot read scheduler receipts or execute the private Vault configuration RPC.

GitHub's older feed-based `refresh-dfs.yml` workflow remains gated and is **not** the active scheduler. There is no required imaginary external feed service, and this development cron does not depend on GitHub default-branch scheduling.

## Recorded live evidence

- Scheduled trigger: November 16 at 4:00 PM Pacific (November 17 00:00 UTC); private receipt nonce `ab48bbc4-2a3c-4213-8ea5-e3dd8168fb41`, runner `9f9a5839-8113-4628-a656-30e9ab64f94a`.
- It generated 150 established NBA forecasts × 10,000 draws, validated 104 current NBA salary rows and 504 NFL salary rows, and published NBA slate/catalog/model artifacts. NFL returned `waiting` because the weekly source did not match.
- Stable preview readback returned HTTP 200 for the NBA catalog and its 68-player slate, with joint simulation and projection controls available. This is historical execution evidence, not permission to use that slate after lock.
- Live relay security tests: reused nonce HTTP 409; expired signature HTTP 401; invalid signature HTTP 401.
- Later scheduled runs continued at 30-minute intervals. When salary sources rolled to another day, mismatched inputs were blocked instead of republished.
- Follow-up fixes select the actual upcoming NBA salary slate's Eastern game date and complete sandbox stop/lease release before responding. The updated live invocation generated 143 next-day NBA forecasts at November 16 6:42 PM Pacific; the slate remained blocked by release validation. The lease table was empty after its response.
- Application CI at integration revision `cc2a9f35c1494f83061ad5e2192d67e23a3d509e`: **147 passing application tests** (38 existing + 109 Pro), plus 13 Python checks across shooting, NBA release, availability and private-worker integration. SEO/profile checks passed. Research validation is separate and never promotes experimental models.

## Latest blocked-refresh and expiry verification

The November 16 6:45 PM Pacific follow-up (runner `1961885d-f995-4d44-825b-14ac94b9d4f5`) regenerated 143 genuine forecasts and validated 176 NBA salary rows. Its NBA slate was blocked because LAL, SAS, DET, NYK, TOR, LAC, UTA and CHA did not have fully verified availability for the slate. Only 21 active modeled players remained, representing fewer than two playable games. The runner does not assume those players are available. NFL remained waiting for matching final weekly forecasts.

The blocked refresh left the NBA catalog's update time and ETag unchanged. The preview returned an empty upcoming-slate list; a direct request for the previously published expired slate returned HTTP 503, `Model inputs require a fresh pre-lock update.` The runner lease table was empty after completion. This verifies real failure preservation and stale-input rejection; it does not establish a currently playable next-day slate.

## NBA next-day availability correction — verified live

The earlier “eight unverified teams” observation exposed a parser integration bug: a current official injury PDF includes multiple game dates, but the adapter selected the report's publication date instead of the upcoming slate date. The adapter now selects the actual forecast/slate game date while retaining the current report's genuine timestamp and hash. No player status is carried across dates and unsubmitted teams remain unverified.

The corrected live refresh at November 16 6:52 PM Pacific published 143 unchanged-model forecasts with 10,000 simulations, validated 176 official salary rows and 141 identity joins, and published a five-game NBA slate. Preview catalog and slate-player reads both returned HTTP 200; the slate contains 78 eligible modeled players and exposes real joint simulation plus projection controls. Runner `cf6e0809-9603-4e35-af12-3172e7798876` completed and left no lease. Existing expiry and conservative exclusions remain enforced.

CI for `4e6109980ef9eb57cb078952a5cfdfd0e937ff33` passed 147 application tests and 15 Python checks. NFL's source remains the final Week 10 JSON/CSV with throughWeek=9. No Week 11 output was found on main. Current Week 11 salaries cannot authorize repurposing those forecasts; recovering/running the complete established weekly input-and-adjustment pipeline remains necessary for NFL current publication.

## What is still not a production-ready release

Matching current NFL weekly forecasts, email delivery, a genuine Stripe-origin receipt, authenticated free/paid quota flows, and final mobile/desktop review remain required. No remote Google, SSO, password or passkey flow should be restarted. No private model source or credentials may be committed.

Run `npm run release:check -- /absolute/private/artifact-root` in the configured candidate environment. Record actual observations for Stripe-origin delivery, authenticated free/paid flows and mobile/desktop review with the candidate commit, timestamp and receipt. Missing evidence is a blocker, never a flag to set without testing. Production deployment still requires explicit owner approval.
