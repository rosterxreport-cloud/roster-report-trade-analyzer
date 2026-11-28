-- Apply only in the intended staging project first. All writes are server-only.
begin;
create table if not exists public.pro_entitlements (
 source text not null check(source in ('stripe','substack_verified')),
 source_id text not null, email text not null check(email=lower(trim(email))),
 status text not null check(status in ('active','inactive')), expires_at timestamptz not null,
 evidence jsonb not null, updated_at timestamptz not null default now(),
 primary key(source,source_id)
);
create index if not exists pro_entitlement_email on public.pro_entitlements(email);
create table if not exists public.pro_usage (user_id uuid not null references auth.users(id) on delete cascade, day date not null, request_id uuid not null, result jsonb not null, primary key(user_id,day));
create table if not exists public.pro_rate_limits (key text primary key, window_start timestamptz not null, hits int not null);
create table if not exists public.pro_stripe_events (event_id text primary key, processed_at timestamptz not null default now());
alter table public.pro_entitlements enable row level security;
alter table public.pro_usage enable row level security;
alter table public.pro_rate_limits enable row level security;
alter table public.pro_stripe_events enable row level security;
revoke all on public.pro_entitlements, public.pro_usage, public.pro_rate_limits, public.pro_stripe_events from anon, authenticated;
grant all on public.pro_entitlements, public.pro_usage, public.pro_rate_limits, public.pro_stripe_events to service_role;
create or replace function public.pro_rate_limit(p_key text,p_limit int,p_seconds int) returns boolean
language plpgsql security invoker set search_path=public as $$
declare v_hits int;
begin
 insert into pro_rate_limits(key,window_start,hits) values(p_key,now(),1)
 on conflict(key) do update set hits=case when pro_rate_limits.window_start<=now()-make_interval(secs=>p_seconds) then 1 else pro_rate_limits.hits+1 end,
 window_start=case when pro_rate_limits.window_start<=now()-make_interval(secs=>p_seconds) then now() else pro_rate_limits.window_start end returning hits into v_hits;
 return v_hits<=p_limit;
end $$;
-- Generate before calling: a failed solver never consumes quota. First completed
-- concurrent request wins. Return the stored response for a repeated request ID.
create or replace function public.pro_save_free(p_user uuid,p_request uuid,p_result jsonb) returns jsonb
language plpgsql security invoker set search_path=public as $$
declare v_day date := (now() at time zone 'America/Los_Angeles')::date; v_row pro_usage;
begin
 insert into pro_usage(user_id,day,request_id,result) values(p_user,v_day,p_request,p_result) on conflict do nothing;
 select * into v_row from pro_usage where user_id=p_user and day=v_day;
 if v_row.request_id<>p_request then return jsonb_build_object('allowed',false); end if;
 return jsonb_build_object('allowed',true,'result',v_row.result);
end $$;
-- Canonical Stripe state is fetched on each delivery. Serialize reconciliation in
-- the caller using a short database lease; idempotent event recording is atomic.
create table if not exists public.pro_sync_lease (id int primary key check(id=1), token uuid not null, expires_at timestamptz not null);
alter table public.pro_sync_lease enable row level security;
revoke all on public.pro_sync_lease from anon,authenticated;
grant all on public.pro_sync_lease to service_role;
create or replace function public.pro_lease(p_token uuid) returns boolean language plpgsql security invoker set search_path=public as $$
declare n int; begin
 insert into pro_sync_lease values(1,p_token,now()+interval '90 seconds') on conflict(id) do update set token=excluded.token,expires_at=excluded.expires_at where pro_sync_lease.expires_at<now();
 get diagnostics n=row_count; return n=1;
end $$;
revoke all on function public.pro_rate_limit(text,int,int),public.pro_save_free(uuid,uuid,jsonb),public.pro_lease(uuid) from public,anon,authenticated;
grant execute on function public.pro_rate_limit(text,int,int),public.pro_save_free(uuid,uuid,jsonb),public.pro_lease(uuid) to service_role;
-- Atomic server-only idempotent entitlement upsert.
create or replace function public.pro_set_entitlement(p_grant jsonb) returns void
language sql security invoker set search_path=public as $$
 insert into pro_entitlements(source,source_id,email,status,expires_at,evidence)
 values(p_grant->>'source',p_grant->>'source_id',p_grant->>'email',p_grant->>'status',(p_grant->>'expires_at')::timestamptz,p_grant->'evidence')
 on conflict(source,source_id) do update set email=excluded.email,status=excluded.status,expires_at=excluded.expires_at,evidence=excluded.evidence,updated_at=now();
$$;
revoke all on function public.pro_set_entitlement(jsonb) from public,anon,authenticated;
grant execute on function public.pro_set_entitlement(jsonb) to service_role;

-- Verify session revocation in addition to Auth's signed user lookup.
grant usage on schema auth to service_role;
grant select(id,user_id) on auth.sessions to service_role;
create or replace function public.pro_session_active(p_user uuid,p_session uuid) returns boolean
language sql security invoker set search_path='' as $$
 select exists(select 1 from auth.sessions where id=p_session and user_id=p_user);
$$;
revoke all on function public.pro_session_active(uuid,uuid) from public,anon,authenticated;
grant execute on function public.pro_session_active(uuid,uuid) to service_role;
commit;
