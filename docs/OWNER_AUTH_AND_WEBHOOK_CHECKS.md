# Remaining administrator checks

## Email verification codes

Project: https://supabase.com/dashboard/project/zretrikowlvfvdrnnoil/auth/templates

Configure the existing project's email sender/SMTP provider in Supabase Authentication settings using the provider's dashboard. Keep credentials in those settings, never chat or Git. Use the Magic Link email template for the existing email OTP login; template subject: `Your Roster Report sign-in code`. Suggested body:

```html
<h2>Your Roster Report sign-in code</h2>
<p>Enter this code in the Toolkit:</p>
<p style="font-size:28px;font-weight:bold;letter-spacing:6px">{{ .Token }}</p>
<p>If you did not request this code, you can ignore this email.</p>
```

Keep email verification enabled. After sender/template configuration, set AUTH_EMAIL_READY=true only for the protected development preview and redeploy that preview to perform the real delivery/verification test. Return it to false if delivery fails. Production remains disabled pending its separate approval. The application uses the same email as the paid Substack subscription. The connected Supabase tools do not expose these administrator sender/template settings; no remote sign-in attempts should be restarted.

## Genuine Stripe delivery

Use Stripe Dashboard → Workbench → Webhooks → endpoint `we_1UcUZWIpu4Wij9Iu4usOR3AN` → Event deliveries. Resend an existing relevant subscription event to that endpoint. Record the event ID, delivery timestamp and HTTP 2xx response. This resends an event; it does not change a subscription or charge. Never copy a credential-bearing endpoint URL into Git or chat.

The endpoint was confirmed enabled through Stripe API. Supabase currently contains only explicitly labelled canonical replay IDs; that is not proof of a Stripe-origin delivery. After a real delivery, correlate the exact event ID with pro_stripe_events and verify legacy subscriptions remain denied. No membership changes or charges are authorized by this check.

## Final preview checks

After delivery configuration: verify login/refresh/logout, paid membership, a free NBA lineup, cross-sport rejection after that shared daily allowance is spent, failed optimization without spending quota, Pro controls/CSV, and desktop/mobile behavior. Store actual receipts for the deployed commit; never mark gates passed from code inspection alone.
