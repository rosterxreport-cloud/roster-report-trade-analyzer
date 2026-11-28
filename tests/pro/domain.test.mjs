import test from 'node:test';import assert from 'node:assert/strict';import crypto from 'node:crypto';
import {pacificDay,stripeSignature,subscriptionGrant,activeMembership,validateArtifact} from '../../server/domain.mjs';
const now=Date.parse('2026-11-15T04:00:00Z');
test('Pacific day changes at midnight and handles both DST offsets',()=>{
 assert.equal(pacificDay(new Date('2026-11-15T07:59:59Z')),'2026-11-14');assert.equal(pacificDay(new Date('2026-11-15T08:00:00Z')),'2026-11-15');assert.equal(pacificDay(new Date('2026-07-01T06:59:59Z')),'2026-06-30');assert.equal(pacificDay(new Date('2026-07-01T07:00:00Z')),'2026-07-01');
});
test('Stripe accepts signed raw payloads and rejects tampering/replay',()=>{
 const raw='{"id":"evt_test"}',t=now/1000,sig=crypto.createHmac('sha256','secret').update(t+'.'+raw).digest('hex');const header=`t=${t},v1=${sig}`;
 assert(stripeSignature(raw,header,'secret',now));assert(!stripeSignature(raw+' ',header,'secret',now));assert(!stripeSignature(raw,header,'secret',now+301000));assert(!stripeSignature(raw,header,'wrong',now));assert(!stripeSignature(raw,'t=x,v1=bad','secret',now));
});
const subscription={id:'sub_example',status:'active',items:{data:[{current_period_end:now/1000+3600,price:{id:'legacy'}}]},cancel_at_period_end:true};
const customer={id:'cus_example',email:' USER@EXAMPLE.COM '},config={prices:['legacy']};
test('Verified legacy plan remains active through scheduled cancellation',()=>{const g=subscriptionGrant(subscription,customer,config,now);assert.equal(g.status,'active');assert.equal(g.email,'user@example.com');assert(activeMembership([g],now));assert(!activeMembership([g],now+3600001));});
test('cancellation, failed payment, expiration, pause and unapproved plans deny access; renewal restores',()=>{
 for(const status of ['canceled','unpaid','past_due','incomplete','paused','trialing'])assert.equal(subscriptionGrant({...subscription,status},customer,config,now).status,'inactive',status);
 assert.equal(subscriptionGrant(subscription,customer,{prices:['other']},now).status,'inactive');assert.equal(subscriptionGrant({...subscription,pause_collection:{}},customer,config,now).status,'inactive');assert.equal(subscriptionGrant(subscription,customer,config,now+3600001).status,'inactive');assert.equal(subscriptionGrant({...subscription,items:{data:[{current_period_end:now/1000+7200,price:{id:'legacy'}}]}},customer,config,now+3600001).status,'active');
});
test('unapproved, stale and incomplete artifacts cannot release',()=>{
 const a={schemaVersion:1,kind:'projections',sport:'NBA',publishApproved:true,capturedAt:new Date(now-1000).toISOString(),validUntil:new Date(now+1000).toISOString(),provenance:{modelHash:'a',sourceHash:'b'},players:[{}]};
 assert.equal(validateArtifact(a,{kind:'projections',sport:'NBA',now}),a);
 for(const bad of [{...a,publishApproved:false},{...a,validUntil:new Date(now-1).toISOString()},{...a,provenance:{}}])assert.throws(()=>validateArtifact(bad,{kind:'projections',sport:'NBA',now}));
});
test('mixed-interval grants use only allowlisted plan periods, including overlapping paid plans',()=>{
 const end=now/1000;
 const mixed={...subscription,current_period_end:end+90000,items:{data:[{current_period_end:end-10,price:{id:'other'}},{current_period_end:end+1000,price:{id:'legacy'}}]}};
 assert.equal(Date.parse(subscriptionGrant(mixed,customer,config,now).expires_at),(end+1000)*1000);
 mixed.items.data[1].current_period_end=end-1;assert.equal(subscriptionGrant(mixed,customer,config,now).status,'inactive');
 mixed.items.data.push({current_period_end:end+2000,price:{id:'legacy'}});assert.equal(subscriptionGrant(mixed,customer,config,now).status,'active');
 assert.equal(subscriptionGrant(subscription,{id:'cus_deleted',deleted:true},config,now).status,'inactive');
});

test('explicit scheduled cancellation caps access even when a paid item ends later',()=>{
 const sub={...subscription,cancel_at:now/1000+500};const g=subscriptionGrant(sub,customer,config,now);assert.equal(Date.parse(g.expires_at),now+500000);assert.equal(subscriptionGrant(sub,customer,config,now+500001).status,'inactive');
 const legacy={...subscription,current_period_end:now/1000+2000,items:{data:[{price:{id:'legacy'}}]}};assert.equal(subscriptionGrant(legacy,customer,config,now).status,'active');
});
