import test from 'node:test';import assert from 'node:assert/strict';
import {reconcileEvent,syncEmail,reconcileKnown,stripeConfig} from '../../server/membership.mjs';
function harness(t){
 const original=global.fetch,env={...process.env};t.after(()=>{global.fetch=original;for(const key of Object.keys(process.env))if(!(key in env))delete process.env[key];Object.assign(process.env,env);});
 Object.assign(process.env,{SUPABASE_URL:'https://db.example.test',SUPABASE_ANON_KEY:'publishable_fixture',SUPABASE_SERVICE_ROLE_KEY:'service_fixture',RATE_LIMIT_SECRET:'fixture',STRIPE_SYNC_VERIFIED:'true',STRIPE_SECRET_KEY:'sk_test_fixture',STRIPE_WEBHOOK_SECRET:'whsec_fixture',STRIPE_ACCOUNT_ID:'acct_fixture',STRIPE_PRICE_IDS:'price_pro,price_legacy',STRIPE_LIVE_MODE:'false'});delete process.env.SUPABASE_GATEWAY_URL;
 const customer={id:'cus_fixture',email:'paid@example.test',livemode:false};
 const subscription={id:'sub_fixture',customer:customer.id,livemode:false,status:'active',items:{data:[{price:{id:'price_legacy'},current_period_end:Math.floor(Date.now()/1000)+86400}]}};
 const state={customer,subscription,grants:new Map(),events:new Set(),calls:[],locked:false,failSubscription:false};
 const response=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});
 global.fetch=async(url,options={})=>{
  const u=new URL(url);state.calls.push(u.pathname+u.search);
  if(u.hostname==='api.stripe.com'){
   if(u.pathname==='/v1/account')return response({id:'acct_fixture'});
   if(u.pathname==='/v1/customers/cus_fixture')return response(state.customer);
   if(u.pathname==='/v1/subscriptions/sub_fixture')return state.failSubscription?response({error:{}},503):response(state.subscription);
   if(u.pathname==='/v1/customers')return response({data:[state.customer],has_more:false});
   if(u.pathname==='/v1/subscriptions')return response({data:[state.subscription],has_more:false});
   throw Error('Unexpected Stripe fixture route '+u.pathname);
  }
  if(u.hostname!=='db.example.test')throw Error('Unexpected network request');
  const body=options.body?JSON.parse(options.body):null,base=u.pathname.replace('/rest/v1/','');
  if(base==='rpc/pro_lease')return response(!state.locked);
  if(base==='pro_sync_lease'&&options.method==='DELETE')return response([]);
  if(base==='rpc/pro_set_entitlement'){state.grants.set(body.p_grant.source_id,structuredClone(body.p_grant));return response(null);}
  if(base==='pro_stripe_events'){
   if(options.method==='POST'){state.events.add(body.event_id);return response([]);}
   return response(state.events.has(u.searchParams.get('event_id')?.slice(3))?[{event_id:u.searchParams.get('event_id').slice(3)}]:[]);
  }
  if(base==='pro_entitlements'){
   let rows=[...state.grants.values()];const source=u.searchParams.get('source_id'),cust=u.searchParams.get('evidence->>customer');
   if(source)rows=rows.filter(r=>r.source_id===source.slice(3));if(cust)rows=rows.filter(r=>r.evidence.customer===cust.slice(3));
   return response(rows.slice(Number(u.searchParams.get('offset')||0),Number(u.searchParams.get('offset')||0)+Number(u.searchParams.get('limit')||100)));
  }
  throw Error('Unexpected backend fixture route '+base);
 };
 return state;
}
const event=(id='evt_fixture',type='customer.subscription.updated',object={id:'sub_fixture'})=>({id,type,livemode:false,data:{object}});

test('canonical reconciliation overrides stale event payloads; duplicate deliveries are idempotent',async t=>{
 const s=harness(t);s.subscription.status='canceled';await reconcileEvent({...event(),data:{object:{id:'sub_fixture',status:'active'}}});assert.equal(s.grants.get('sub_fixture').status,'inactive');const before=s.calls.filter(p=>p.startsWith('/v1/subscriptions/')).length;assert((await reconcileEvent(event())).duplicate);assert.equal(s.calls.filter(p=>p.startsWith('/v1/subscriptions/')).length,before);
 s.subscription.status='active';await reconcileEvent(event('evt_renewal'));assert.equal(s.grants.get('sub_fixture').status,'active');
});
test('failed canonical lookup is retryable and never marks the event processed',async t=>{const s=harness(t);s.failSubscription=true;await assert.rejects(()=>reconcileEvent(event()),/temporarily unavailable/);assert(!s.events.has('evt_fixture'));s.failSubscription=false;await reconcileEvent(event());assert(s.events.has('evt_fixture'));});
test('deleted canonical customer revokes the known grant even without an email',async t=>{const s=harness(t);await reconcileEvent(event('evt_active'));s.customer={id:'cus_fixture',deleted:true};await reconcileEvent(event('evt_deleted'));const grant=s.grants.get('sub_fixture');assert.equal(grant.status,'inactive');assert.equal(grant.email,'paid@example.test');assert(grant.evidence.subject_unavailable);});
test('customer deletion and email changes reconcile existing subscription subjects',async t=>{const s=harness(t);await reconcileEvent(event('evt_active'));s.customer.email='new@example.test';await reconcileEvent(event('evt_customer_email','customer.updated',{id:'cus_fixture'}));assert.equal(s.grants.get('sub_fixture').email,'new@example.test');s.customer={id:'cus_fixture',deleted:true};await reconcileEvent(event('evt_customer_deleted','customer.deleted',{id:'cus_fixture'}));assert.equal(s.grants.get('sub_fixture').status,'inactive');});
test('expanded invoice subscription references use canonical state',async t=>{const s=harness(t);await reconcileEvent(event('evt_invoice','invoice.paid',{parent:{subscription_details:{subscription:{id:'sub_fixture',object:'subscription'}}}}));assert.equal(s.grants.get('sub_fixture').status,'active');});
test('verified email sync backfills legacy paid plans and known reconciliation revokes failed payments',async t=>{const s=harness(t);const result=await syncEmail(' PAID@example.test ');assert.equal(result.customerCount,1);assert.equal(s.grants.get('sub_fixture').status,'active');s.subscription.status='past_due';assert.equal((await reconcileKnown()).checked,1);assert.equal(s.grants.get('sub_fixture').status,'inactive');});
test('mode/account mismatches and busy reconciliation leases fail closed',async t=>{const s=harness(t);await assert.rejects(()=>reconcileEvent({...event(),livemode:true}),/scope mismatch/);await assert.rejects(()=>reconcileEvent({...event(),account:'acct_other'}),/scope mismatch/);s.locked=true;await assert.rejects(()=>reconcileEvent(event()),/busy/);assert.equal(s.grants.size,0);});

test('billing activation requires complete scoped runtime configuration and signed webhooks',t=>{
 harness(t);assert.equal(stripeConfig().live,false);
 for(const [key,value] of [['STRIPE_WEBHOOK_SECRET',''],['STRIPE_PRICE_IDS',' , '],['STRIPE_ACCOUNT_ID','wrong'],['STRIPE_LIVE_MODE',''],['STRIPE_SECRET_KEY','rk_live_fixture'],['STRIPE_SYNC_VERIFIED','false']]){const old=process.env[key];process.env[key]=value;assert.throws(()=>stripeConfig(),/runtime configuration/);process.env[key]=old;}
 process.env.STRIPE_SECRET_KEY='rk_test_fixture';assert.equal(stripeConfig().live,false);
});
