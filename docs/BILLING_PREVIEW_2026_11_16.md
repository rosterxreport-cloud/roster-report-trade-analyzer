# Stripe membership preview — November 16, 2026

The owner confirmed that current $5.99/month and $60/year plans and legacy $5/month and $50/year plans belong to The Roster Report. Preview configuration allowlists the 26 exact Substack price versions belonging to those four products; unrelated $8/$80 products remain excluded. No customer emails or secrets are stored in this repository.

The restricted runtime key and webhook signing secret are Vercel Secrets scoped to the development preview branch. Stripe endpoint `we_1UcUZWIpu4Wij9Iu4usOR3AN` uses API version `2026-09-30.endive`, the stable preview branch alias, and the canonical `/api/pro/` path. The owner explicitly approved Vercel's private automation bypass token for this receiver. Do not copy the complete webhook URL into documentation or logs. Retire this preview endpoint and revoke its bypass token when production takes over.

The direct HTTP test rejected unsigned requests (400). A correctly signed replay with a real subscription ID retrieved canonical Stripe account, subscription and customer state and saved the entitlement successfully (200). This verifies the actual restricted runtime credential rather than relying on connector access. Synthetic replay IDs are clearly prefixed `evt_rrpreview_`; real customer payments and subscriptions are not modified.

Testing exposed a gateway bug: forwarding a successful no-content RPC response using an empty string body raised a Fetch Response exception after the write succeeded. The gateway now forwards HTTP 204/205/304 with a null body. A regression test covers empty responses and ordinary JSON responses. Gateway authentication remains limited to the exact Vercel preview project identity.

This is isolated preview membership synchronization, not production release approval. Email sign-in delivery is still disabled. Apple purchases, gifts, group beneficiaries and complimentary subscribers are not claimed to be fully covered by these Stripe subscriptions. Production cutover, email delivery and a real Stripe-origin delivery receipt remain release checks; locally signed canonical replays are not Stripe-origin delivery receipts.
