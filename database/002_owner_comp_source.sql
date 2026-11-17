-- Explicit administrator-granted owner access, separate from paid Stripe eligibility.
-- No grant is created by this migration. Never store owner email addresses in source.
alter table public.pro_entitlements drop constraint pro_entitlements_source_check;
alter table public.pro_entitlements add constraint pro_entitlements_source_check
 check (source in ('stripe','substack_verified','owner_comp'));
