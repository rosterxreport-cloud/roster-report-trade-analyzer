# Established-model product integration

The development Preview NBA projections page now loads all 268 players from the original November 15 shared-preseason25-v1 forecast. Point values and the 13 displayed stat fields are copied exactly; no simulator, shooting-policy adjustment or recalibration is invoked. Source SHA256: d1a05f2e9d1844aa7d28d99dcc32f7858adcca94514e6100b8ea0a8efea9783b.

scripts/pro/export-nba-basic.py is a data adapter only. It resolves opponent teams from the original game's two team identities and strips all private features, model coefficients and research variants. The saved snapshot is explicitly dated and availability is unverified. It is not a current eligible DFS slate.

The existing approved private-storage route remains preferred. If that route is unavailable in Vercel Preview, nba-basic returns the dated original-model snapshot for product review. Production cannot use this fallback. Neither optimizer nor premium simulations consumes the snapshot, and no source publishApproved flag is overridden. The frontend preserves the label/date when displaying and searching all records.

Verification: all 268 exported point forecasts and stat lines were compared against the original source. Tests cover data identity, duplicate/invalid records, private-field stripping, Preview-only access, the HTTP route fallback and production rejection. No experimental projection examples are reintroduced.

Remaining activation work is operational integration: reliable email delivery, runtime billing credentials, signed webhook delivery, publication-plan mapping, established-model artifact delivery and end-to-end free/paid flows. Additional model redesign is out of scope. Missing current-slate eligibility data must still be reported explicitly rather than invented.

The projection table offers DraftKings, Yahoo and ESPN point outputs copied from the established source, sorted for the selected scoring format. Source values are never recomputed. Snapshot date/availability notices sit outside the horizontal table scroll, and search displays result counts and an explicit empty state. Approved artifact exports can carry the same optional existing scoring outputs.
