import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
import {PGlite} from '@electric-sql/pglite';
import handler from '../../api/pro.mjs';

// Real application handler and quota/session SQL, with fixture Auth/storage transport.
// This does not establish live email delivery, Stripe billing or a browser session.
test('API and PostgreSQL share the free allowance, preserve failed runs, and honor paid access and revocation',async()=>{
 const db=new PGlite(),originalFetch=globalThis.fetch,environment={...process.env};
 await db.exec('create role anon;create role authenticated;create role service_role bypassrls;create schema auth;create table auth.users(id uuid primary key);create table auth.sessions(id uuid primary key,user_id uuid);');
 await db.exec(fs.readFileSync(new URL('../../database/001_pro.sql',import.meta.url),'utf8'));
 const user=crypto.randomUUID(),session=crypto.randomUUID(),email='fixture@example.invalid';
 await db.query('insert into auth.users values($1)',[user]);await db.query('insert into auth.sessions values($1,$2)',[session,user]);
 Object.assign(process.env,{APP_ORIGIN:'https://fixture.example',SUPABASE_URL:'https://database.example',SUPABASE_ANON_KEY:'fixture-public',SUPABASE_SERVICE_ROLE_KEY:'fixture-server',RATE_LIMIT_SECRET:'fixture-rate'});
 delete process.env.SUPABASE_GATEWAY_URL;
 const token='fixture.'+Buffer.from(JSON.stringify({session_id:session})).toString('base64url')+'.fixture';
 let ready=false;
 const slate=sport=>{
  const now=Date.now(),positions=sport==='NBA'?['PG','SG','SF','PF','C']:['QB','RB','WR','TE','DST'];
  return {schemaVersion:1,kind:'slate',sport,slateId:'fixture',format:'DraftKings Classic',salaryCap:50000,publishApproved:ready,capturedAt:new Date(now-1000).toISOString(),validUntil:new Date(now+3600000).toISOString(),scoring:sport==='NFL'?'RR-DK-core':'DraftKings',provenance:{modelHash:'fixture',sourceHash:'fixture',salarySource:'fixture',injurySource:'fixture',eligibilitySource:'fixture',scoringMethod:'weekly-ppr-plus-interceptions'},players:Array.from({length:30},(_,i)=>({id:String(i+1),name:'Fixture '+i,team:i%2?'AAA':'BBB',opponent:i%2?'BBB':'AAA',gameId:String(Math.floor(i/10)),positions:[positions[i%5]],salary:4000,projection:20+i/10,status:'active',verifiedAt:new Date(now-1000).toISOString(),startsAt:new Date(now+3600000).toISOString()}))};
 };
 globalThis.fetch=async(url,options={})=>{
  const u=new URL(url),path=u.pathname,args=options.body?JSON.parse(options.body):{};let value;
  if(path==='/auth/v1/user')value={id:user,email,email_confirmed_at:new Date().toISOString()};
  else if(path.endsWith('/rpc/pro_session_active'))value=(await db.query('select pro_session_active($1,$2) as value',[args.p_user,args.p_session])).rows[0].value;
  else if(path.endsWith('/rpc/pro_rate_limit'))value=(await db.query('select pro_rate_limit($1,$2,$3) as value',[args.p_key,args.p_limit,args.p_seconds])).rows[0].value;
  else if(path.endsWith('/rpc/pro_save_free'))value=(await db.query('select pro_save_free($1,$2,$3) as value',[args.p_user,args.p_request,args.p_result])).rows[0].value;
  else if(path.endsWith('/pro_entitlements'))value=(await db.query('select status,expires_at,source from pro_entitlements where email=$1',[email])).rows;
  else if(path.endsWith('/pro_usage'))value=(await db.query('select request_id,result from pro_usage where user_id=$1 and day=$2',[user,u.searchParams.get('day').slice(3)])).rows;
  else if(path.includes('/storage/'))value=slate(path.includes('/nfl/')?'NFL':'NBA');
  else throw Error('Unexpected fixture transport: '+path);
  return new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json'}});
 };
 const call=async(sport,requestId,extra={})=>{
  let status,result;const res={setHeader(){},status(code){status=code;return this;},json(body){result=body;}};
  await handler({url:'/api/pro/?action=optimize',method:'POST',headers:{origin:'https://fixture.example',cookie:'rr_access='+token},body:{sport,slateId:'fixture',requestId,...extra}},res);
  return {status,result};
 };
 try{
  let r=await call('NBA',crypto.randomUUID());assert.equal(r.status,503);assert.equal((await db.query('select count(*)::int as n from pro_usage')).rows[0].n,0);
  ready=true;const request=crypto.randomUUID();r=await call('NBA',request);assert.equal(r.status,200);assert.equal(r.result.lineups[0].players.length,8);
  const retry=await call('NBA',request);assert.equal(retry.status,200);assert.equal(retry.result.csv,r.result.csv);
  r=await call('NFL',crypto.randomUUID());assert.equal(r.status,429);assert.equal((await db.query('select count(*)::int as n from pro_usage')).rows[0].n,1);
  await db.query("insert into pro_entitlements(source,source_id,email,status,expires_at,evidence) values('stripe','sub_fixture',$1,'active',now()+interval '1 day','{}')",[email]);
  for(let i=0;i<2;i++){
   r=await call('NFL',crypto.randomUUID(),{advanced:true,count:2});assert.equal(r.status,200);assert.equal(r.result.lineups.length,2);assert.equal(r.result.csv.split('\r\n').length,3);
  }
  assert.equal((await db.query('select count(*)::int as n from pro_usage')).rows[0].n,1);
  await db.query('delete from auth.sessions where id=$1',[session]);r=await call('NFL',crypto.randomUUID());assert.equal(r.status,401);
 }finally{
  globalThis.fetch=originalFetch;for(const key of Object.keys(process.env))if(!(key in environment))delete process.env[key];Object.assign(process.env,environment);await db.close();
 }
});
