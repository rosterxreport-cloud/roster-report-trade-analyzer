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
