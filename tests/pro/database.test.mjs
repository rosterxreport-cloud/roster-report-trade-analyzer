import test from 'node:test';
import {PGlite} from '@electric-sql/pglite';import fs from 'node:fs';import assert from 'node:assert/strict';import crypto from 'node:crypto';
test('PostgreSQL migration, RLS, quota retries, rate limits and session revocation',async()=>{
const db=new PGlite();await db.exec(`create role anon;create role authenticated;create role service_role bypassrls;create schema auth;create table auth.users(id uuid primary key);create table auth.sessions(id uuid primary key,user_id uuid);`);
const sql=fs.readFileSync(new URL('../../database/001_pro.sql',import.meta.url),'utf8');await db.exec(sql);await db.exec(sql);
const user=crypto.randomUUID(),request=crypto.randomUUID();await db.query('insert into auth.users values($1)',[user]);
await db.exec('set role service_role');
const run=async(q,params=[])=>(await db.query(q,params)).rows[0];
let a=await run('select pro_save_free($1,$2,$3) as value',[user,request,{sport:'NBA',lineups:[1]}]);assert(a.value.allowed);assert.equal(a.value.result.sport,'NBA');
a=await run('select pro_save_free($1,$2,$3) as value',[user,request,{sport:'NFL',lineups:[2]}]);assert.equal(a.value.result.sport,'NBA');
a=await run('select pro_save_free($1,$2,$3) as value',[user,crypto.randomUUID(),{sport:'NFL'}]);assert(!a.value.allowed);
const queued=await Promise.all(Array.from({length:10},()=>run('select pro_save_free($1,$2,$3) as value',[user,crypto.randomUUID(),{}])));assert(queued.every(x=>!x.value.allowed));
for(let i=1;i<=4;i++){a=await run('select pro_rate_limit($1,3,60) as value',['user']);assert.equal(a.value,i<=3);}
await db.exec('reset role');
const sessionId=crypto.randomUUID();await db.query('insert into auth.sessions values($1,$2)',[sessionId,user]);await db.exec('set role service_role');assert((await run('select pro_session_active($1,$2) as value',[user,sessionId])).value);await db.exec('reset role');await db.query('delete from auth.sessions where id=$1',[sessionId]);await db.exec('set role service_role');assert(!(await run('select pro_session_active($1,$2) as value',[user,sessionId])).value);await db.exec('reset role');
for(const role of ['anon','authenticated']){await db.exec('set role '+role);for(const q of ['select * from pro_entitlements','select * from pro_usage',"select pro_rate_limit('x',1,60)","select pro_lease('00000000-0000-0000-0000-000000000001')"]){await assert.rejects(()=>db.query(q),/permission denied/);}await db.exec('reset role');}
const rls=(await db.query("select relname,relrowsecurity from pg_class where relname in ('pro_entitlements','pro_usage','pro_rate_limits','pro_stripe_events','pro_sync_lease')")).rows;assert(rls.every(x=>x.relrowsecurity));
const grants=(await db.query("select proname,prosecdef from pg_proc where proname like 'pro_%' and pronamespace='public'::regnamespace")).rows;assert(grants.every(x=>!x.prosecdef));
await db.close();
});
