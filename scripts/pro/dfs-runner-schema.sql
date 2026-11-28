create extension if not exists pg_cron;
create extension if not exists pg_net with schema extensions;
create table if not exists public.dfs_runner_lease (
 id boolean primary key default true check(id),
 owner uuid not null,
 expires_at timestamptz not null
);
alter table public.dfs_runner_lease enable row level security;
revoke all on public.dfs_runner_lease from public,anon,authenticated;
grant all on public.dfs_runner_lease to service_role;
create or replace function public.dfs_acquire_runner(p_owner uuid) returns boolean
language plpgsql security invoker set search_path=public,pg_temp as $$
declare changed int;
begin
 insert into public.dfs_runner_lease(id,owner,expires_at) values(true,p_owner,now()+interval '12 minutes')
 on conflict(id) do update set owner=excluded.owner,expires_at=excluded.expires_at
 where dfs_runner_lease.expires_at < now();
 get diagnostics changed=row_count;
 return changed=1;
end; $$;
create or replace function public.dfs_release_runner(p_owner uuid) returns boolean
language plpgsql security invoker set search_path=public,pg_temp as $$
declare changed int;
begin
 delete from public.dfs_runner_lease where id=true and owner=p_owner;
 get diagnostics changed=row_count;
 return changed=1;
end; $$;
revoke all on function public.dfs_acquire_runner(uuid) from public,anon,authenticated;
revoke all on function public.dfs_release_runner(uuid) from public,anon,authenticated;
grant execute on function public.dfs_acquire_runner(uuid) to service_role;
grant execute on function public.dfs_release_runner(uuid) to service_role;
