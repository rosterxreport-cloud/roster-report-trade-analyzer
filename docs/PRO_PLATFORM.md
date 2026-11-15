# Toolkit Pro implementation and release record

## Audit — 2026-11-14 Pacific
Base commit: 58acc1b47635c99189505d2ffd4da07dceb72ba4 (main).
Existing stack: static HTML/CSS/JavaScript, Node SEO build, Python offline NFL model, no package manager, database, authentication, or API. Vercel project prj_Yh4nqosEYTcKKgJmnXoVEVN16YR7, team team_i1lZgAiJDqwdDqFDZ97qajZC. Production custom domain www.rosterreport.app; preview protection enabled. Existing build outputs, canonical URLs, JSON-LD, free data, scripts and embeds must be retained.

## Phases
1. Audit repository, production and private research; capture baseline and release gates.
2. Add dedicated routes, shared navigation and responsive sport themes through an additive build step.
3. Add Supabase verified-email authentication, server-only entitlements, transactional quotas/rate limits, Stripe canonical-state reconciliation, account UI.
4. Implement validated slate ingestion, constrained tournament optimization, correlated-distribution consumers, trade analysis, private artifact adapters.
5. Run regression/security/constraint tests and recovered research tests. Deploy development branch preview in the same Vercel project. Activate live integrations only after secure configuration and data approval.
6. Production approval only after live membership lifecycle, authenticated browser flows and current-slate tests pass.

## Research recovered
Latest private NBA bundle version 49, SHA256 cc7af433f881ae0906a39be2c42eb1661018a49c88996e06d2aa71804f310979. NBA DFS archive version 2, SHA256 b69af1e4445fd38f1db702cbeb09f17b4586e9dbde3545e8e00553a6a5aa8652. Private research stays outside this public repository.

The Nov 14 snapshot uses shared-preseason25-v1 with usage 1, potential assists .25, rebound chances 1, opponent defense .75; publishApproved=false. Active shooting policy is recency-weighted estimates shrunk toward observed history, not exact historical percentages. Do not override this gate or claim the requested shooting policy is satisfied. Preserve the incumbent point forecasts: the Nov 7 simulation point estimates were worse (original Yahoo MAE 7.88 versus simulated mean 8.37). Simulation intervals are experimental; not verified history.

Recovered NBA Home Run replay: five restricted-pool slates averaged 206.45 DK vs standard GPP 209.15; zero of five published top-20% references cleared. Incomplete salary pools and missing complete pre-lock fields prevent ROI/cash-rate conclusions. New Toolkit optimizer is separately implemented and requires its own forward validation; recovered results do not validate it.

## Membership integration decision
No live Stripe account subscription visibility has yet been verified. Keep STRIPE_SYNC_VERIFIED disabled. Only allowlisted publication price IDs in the verified Stripe account may grant access. Never infer membership from payouts, arbitrary customer email, user-submitted flags, or all Stripe subscriptions. Use canonical subscription retrieval for event delivery, account/livemode checks and idempotent processing. Run periodic reconciliation to recover missed events. Cancel-at-period-end retains access through paid expiration; canceled/unpaid/paused/incomplete/past_due deny access under the initial strict policy. Trials do not grant paid access.

Substack Apple IAP, gifts, comps and group billing require separate coverage investigation. Authoritative externally verified grants can be reconciled through the server-only entitlement table with explicit expiry and audit evidence. There is no automatic Substack coverage claim or public self-claim route. Existing subscribers match only verified login email; customer identity is retrieved server-side. A scheduled authoritative full snapshot must revoke removed grants. Stripe connection alone is not runtime provisioning.

## Configuration and production gates
See .env.example and database/001_pro.sql. Configure secrets directly in Vercel Preview environment, using a separate Supabase staging project; never paste them into chat. Run migration there, enable email OTP and set the email template to expose Token, configure provider email limits and delivery. Stripe requires canonical account ID, live/test mode, allowlisted prices, signed webhook endpoint, verified coverage and existing subscriber backfill. Private storage artifact must pass release, timestamps, slate and source checks. No fabricated current salaries, ownership or forecasts are shipped.

## Live account investigation update
The connected Stripe live account exposes Substack-managed subscriptions: subscription.application is populated, application_fee_percent=10, and item.price.metadata.substack=yes. Active subscriptions include a legacy plan, so filtering only the new monthly price would incorrectly exclude an existing subscriber. Product-name searches did not independently confirm publication identity; retain the integration gate until publication mapping is confirmed, all current prices are enumerated, signed webhooks are installed, and backfill is complete. There is no proof of full Apple/gift/comp coverage. No customer records, emails or payment methods are committed here.

Supabase connection succeeded; it contains no projects. Its only organization was quoted $0/month for a project. Provisioning remains pending the provider-required cost acknowledgment. Runtime service-role and billing credentials have not been provisioned in Vercel. A ChatGPT connection does not automatically expose credentials to deployed functions.

## Verification so far
- Existing JavaScript suite: 37/37 passed, including all original SEO, player pages, published-input byte comparisons, scoring and projections.
- Platform unit/route suite: 20/20 passed before final hardening; rerun after all edits.
- Recovered private NBA model suite: 84/84 passed.
- Recovered private NBA DFS suite: 7/7 passed.
- Recovered joint simulation executed successfully: 145 players × 10,000 outcomes using the Nov 14 source. Source publication gate remains false. No generic forecast substituted.
- Initial same-project Vercel preview reached READY. Live status endpoint returned 200 with private/no-store, accountsConfigured=false and billingVerified=false.
- Desktop browser confirmed dashboard, NBA DFS unavailable-data state and account page. Embedded Substack was unavailable in the cloud browser; markup/links remain intact. Full mobile and authenticated end-to-end tests remain open.

## Remaining production blockers
1. Provision staging Supabase, apply/review migration, configure OTP email delivery, and put runtime secrets in sensitive Preview environment variables.
2. Verify publication/price mapping, obtain least-privilege read-only Stripe runtime credential, register signed webhook, reconcile all existing subscribers and test lifecycle in a separate sandbox.
3. Authoritative Substack reconciliation for Apple, gift, group and complimentary subscribers; implement coverage before claiming all paid subscribers activate automatically.
4. NBA model release audit, including historical-shooting policy conflict, prospective minutes/per-minute validation and calibrated distributions. The existing research gate stays closed.
5. Complete current DraftKings salary/eligibility pools, pre-lock injury/starter evidence, reliable ownership when available, and approved NFL joint simulation artifacts. No current slate is fabricated.
6. Full historical backtesting of this new server optimizer on complete frozen pre-lock pools; contest payouts/ROI remain unverified. Recovered NFL Week 9 HTML is a fixed research tool with omitted DK bonuses/fumbles and external DST estimates, not an approved current-slate source.
7. Live concurrency, authentication/renewal/cancellation/browser-mobile tests and final production review. Do not merge or promote until those pass.

Advanced player comparisons use current-week projections and an existing value index; calibrated trade confidence, multi-week starting-lineup distributions, and dated consensus-disagreement feeds remain future work. The platform is a tested preview foundation, not a completed production launch.

## Additional hardening
Migration exercised twice against PGlite 0.5.16 PostgreSQL WASM: one free result across sports, idempotent retries, queued duplicate calls, rate-limit windows, direct-table and RPC denial for anon/authenticated, RLS and immediate session-revocation lookup all passed. This is not a live Supabase multi-connection test. Privileged RPCs use SECURITY INVOKER and service-role-only grants. Trade values are exported from the original injury-adjusted browser model build, so Pro uses the same value index as the free tool. Optimizer search is bounded and explicitly does not claim global optimality.

## Final test and preview record
Final local suites: 37 legacy JavaScript tests and 23 platform tests (including the PostgreSQL migration/security check). Recovered private suites: 84 model + 7 optimizer tests. The private simulator exported exactly 10,000 joint outcomes for each of 145 players. Website output contains 335 pages (326 original plus 9 routes), and no server code, private research or credentials in static output. Test success demonstrates implementation invariants, not model profitability or readiness of unconfigured external integrations.

## Free staging backend — continuation
Created Supabase staging project `zretrikowlvfvdrnnoil` in the approved existing organization on the quoted $0/month plan, us-east-1. Applied toolkit_pro_foundation migration and checked live function privileges: anon/authenticated cannot execute any privileged RPC. Security advisors reported only informational no-policy notices on the five intentionally server-only RLS tables.

Staging Vercel functions use a Supabase Edge gateway with Vercel OIDC federation. Gateway verifies RS256 signatures against Vercel JWKS, expiration, issuer, audience, team ID, project ID, environment=preview and exact subject. Production and other projects are denied. The edge handler performs its own JWT verification; Supabase's legacy JWT precheck is disabled because it does not understand Vercel issuer tokens. The service-role key stays in Supabase's built-in function environment. Only the public auth key, gateway URL and generated per-branch rate-limit/cron secrets are configured for this development branch's Preview environment.

AUTH_EMAIL_READY remains false until the OTP template, redirect configuration and email delivery are verified. Supabase's default email service permits organization-team addresses only; a general subscriber launch needs a custom SMTP provider or a supported Send Email hook. Never bypass email verification to make staging login appear functional.
