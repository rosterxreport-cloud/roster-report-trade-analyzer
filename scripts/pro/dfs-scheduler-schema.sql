-- Staging signed DFS scheduler. Contains no model source or credential values.
create table if not exists public.dfs_cron_nonces (
 nonce uuid primary key, created_at timestamptz not null default now()
);
alter table public.dfs_cron_nonces enable row level security;
revoke all on public.dfs_cron_nonces from public, anon, authenticated;
grant all on public.dfs_cron_nonces to service_role;
create table if not exists public.dfs_schedule_runs (
 nonce uuid primary key, started_at timestamptz not null default now(),
 finished_at timestamptz, status text not null check(status in ('running','completed','failed')),
 http_status integer, receipt jsonb
);
alter table public.dfs_schedule_runs enable row level security;
revoke all on public.dfs_schedule_runs from public, anon, authenticated;
grant all on public.dfs_schedule_runs to service_role;
create or replace function public.dfs_claim_cron_nonce(p_nonce uuid, p_time bigint)
returns boolean language plpgsql security invoker set search_path=pg_catalog,public as $$
declare inserted int;
begin
 if abs(extract(epoch from now())-p_time)>90 then return false; end if;
 delete from public.dfs_cron_nonces where created_at<now()-interval '1 day';
 insert into public.dfs_cron_nonces(nonce) values(p_nonce) on conflict do nothing;
 get diagnostics inserted=row_count;
 return inserted=1;
end; $$;
revoke all on function public.dfs_claim_cron_nonce(uuid,bigint) from public,anon,authenticated;
grant execute on function public.dfs_claim_cron_nonce(uuid,bigint) to service_role;
-- Deliberately narrow private Vault lookup: service role only, fixed names, no caller inputs.
create or replace function public.dfs_private_cron_config()
returns jsonb language sql security definer set search_path=pg_catalog,public as $$
 select jsonb_build_object(
  'signingKey',(select decrypted_secret from vault.decrypted_secrets where name='dfs_cron_signing_key'),
  'runnerUrl',(select decrypted_secret from vault.decrypted_secrets where name='dfs_runner_url'),
  'runnerToken',(select decrypted_secret from vault.decrypted_secrets where name='dfs_runner_token'),
  'bypass',(select decrypted_secret from vault.decrypted_secrets where name='dfs_preview_bypass')
 );
$$;
revoke all on function public.dfs_private_cron_config() from public,anon,authenticated;
grant execute on function public.dfs_private_cron_config() to service_role;
-- Activate only after the private runner, relay and Vault entries have been configured.
-- pg_net receives only a one-use, 90-second proof; never queue permanent credentials.
-- The deployed staging schedule is every 30 minutes:
-- select cron.schedule('dfs-established-staging-refresh','*/30 * * * *', $cron$
-- with proof as (select floor(extract(epoch from clock_timestamp()))::bigint::text as stamp,gen_random_uuid()::text as nonce), signed as (select stamp,nonce,encode(extensions.hmac(stamp||'.'||nonce,(select decrypted_secret from vault.decrypted_secrets where name='dfs_cron_signing_key'),'sha256'),'hex') as signature from proof)
-- select net.http_post(url:='https://zretrikowlvfvdrnnoil.supabase.co/functions/v1/dfs-schedule',headers:=jsonb_build_object('Content-Type','application/json','x-dfs-time',stamp,'x-dfs-nonce',nonce,'x-dfs-signature',signature),body:='{}'::jsonb,timeout_milliseconds:=15000) from signed;
-- $cron$);
