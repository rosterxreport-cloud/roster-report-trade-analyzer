# Private runner recovery — November 16, 2026

## Observed state

Recovered branch head: 3a084c94e1a27246ff2148b442b2e43ecc15139a. PR #45 remains a draft. The matching Vercel deployment was READY. No production promotion was performed.

The local execution host was unavailable. An isolated project-scoped Vercel sandbox recovered the development checkout and all four owner-identified private archives. Private source remains outside the public checkout. A recovery sandbox is not a recurring production model service.

The latest basketball archive was version 51, modified November 16. Its November 16 snapshot contains 239 predictions, created at 16:17:06 UTC, model shared-preseason25-v1, publishApproved=false. The unchanged existing export adapter and recovered simulator executed successfully: 239 players, exactly 10,000 draws each. The release validator rejected the exported projection artifact because source approval is false. Neither source dates nor approval flags were changed. This execution verifies recoverability, not model release approval or live DFS readiness.

Supabase staging has an active toolkit-gateway v2. Its deployed artifact branch permits GET only. It verifies preview-scoped Vercel OIDC; that identity is not a publishing credential for an independent runner. Do not widen the application's existing gateway to arbitrary storage writes. toolkit-private exists and is private.

## Implemented direct execution interface

A private scheduled host can now run the established model and acquisition adapters and pass their complete JSON bundle directly to the existing validator/publisher. An external authenticated feed remains supported for compatibility, but is no longer a mandatory architectural dependency.

```sh
node scripts/pro/refresh-dfs.mjs --bundle /private/refresh-bundle.json --validate-only
node scripts/pro/refresh-dfs.mjs --bundle /private/refresh-bundle.json
```

The bundle schema is unchanged: slates with salaryCsv, manifest, model and joint, plus nba.basic and nba.distributions. Validation-only requires no storage credentials and performs no HTTP requests. Publishing requires securely provisioned SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY on the private host (or a separately implemented and verified narrowly scoped publishing identity). No such host credential was provisioned during recovery.

The direct path validates the entire bundle before any upload. Versioned slate writes now reject overwrites. Both discovery catalogs are written after all non-catalog objects. A failed object write leaves both catalogs unchanged. Catalog updates remain per sport: failure after the first catalog switch can leave a partial cross-sport update. The CLI now states that limitation accurately rather than implying every failed refresh is atomic. Do not blindly retry a partial publication.

## Concrete remaining source and hosting work

- Deploy a durable private scheduled execution service and securely provision its publishing identity. The recovery sandbox and this CLI do not establish that service.
- Recover/identify the established NFL executable and its current event-level DraftKings scoring and joint outputs. The four supplied archives do not establish a currently approved NFL execution path; no PPR substitution is allowed.
- Establish a release-approved source path for the incumbent NBA point forecasts and joint simulator. The recovered latest source and recovered November 15 validation report explicitly withhold publication approval. Do not substitute experimental variants or remove their gates.
- Retrieve current complete official salary pools, explicit stable-ID eligibility/game mappings and current availability evidence. November 15 salary captures are historical evidence; they were not republished for November 16.
- Build a complete current bundle and pass real retrieval, validation, storage publication and application readback. None of those end-to-end publication steps has passed.
- Configure the actual scheduler. The development-branch workflow remains inactive; GitHub cron only runs from the default branch. No workflow activation or main-branch change was performed.

Email sender/delivery configuration, a genuine Stripe-origin delivery receipt, authenticated free/paid browser flows and final mobile/desktop review remain open as recorded in RELEASE_STATUS.md.

## Validation

Full application suite after changes: 38 legacy tests + 82 Pro tests = 120 passed, zero failed. Build completed. Seven new direct-runner tests cover credential-free validation, malformed local inputs, complete synthetic bundles, immutable versioned writes, catalog ordering, transport failure redaction, expired-source rejection and preserved source dates/flags. Synthetic bundles are tests only and were never published. Real recovered NBA output was separately rejected by the release gate as expected.

No mathematical-optimality, profitability, current-slate or working-automation claim follows from these tests.
