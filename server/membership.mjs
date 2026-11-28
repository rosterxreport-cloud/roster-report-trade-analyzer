import crypto from 'node:crypto';
import {fail,normalizeEmail,subscriptionGrant} from './domain.mjs';
import {supa,rpc} from './store.mjs';
export function stripeConfig(){
 const e=process.env;
 const prices=(e.STRIPE_PRICE_IDS||'').split(',').map(x=>x.trim()).filter(Boolean),mode=e.STRIPE_LIVE_MODE==='true'?'live':'test';
 if(e.STRIPE_SYNC_VERIFIED!=='true'||!new RegExp('^(rk|sk)_'+mode+'_').test(e.STRIPE_SECRET_KEY||'')||!/^whsec_\S+$/.test(e.STRIPE_WEBHOOK_SECRET||'')||!/^acct_[a-zA-Z0-9]+$/.test(e.STRIPE_ACCOUNT_ID||'')||!['true','false'].includes(e.STRIPE_LIVE_MODE)||!prices.length||prices.some(x=>!/^[a-zA-Z0-9_]+$/.test(x)))fail(503,'Substack billing coverage and runtime configuration have not been verified for automatic activation.');
 return {secret:e.STRIPE_SECRET_KEY,account:e.STRIPE_ACCOUNT_ID,prices,live:e.STRIPE_LIVE_MODE==='true'};
}
async function stripe(path,c){
 const r=await fetch('https://api.stripe.com/v1/'+path,{headers:{Authorization:'Bearer '+c.secret,'Stripe-Version':'2026-09-30.endive'},signal:AbortSignal.timeout(10000)});
 if(!r.ok)fail(503,'Membership verification is temporarily unavailable.');return r.json();
}
async function withLease(fn){
 const token=crypto.randomUUID();if(!await rpc('pro_lease',{p_token:token}))fail(503,'Membership reconciliation is busy; please retry.');
 try{return await fn();}finally{await supa('pro_sync_lease?id=eq.1&token=eq.'+token,{method:'DELETE'});}
}
async function verifyAccount(c){const a=await stripe('account',c);if(a.id!==c.account)fail(503,'Billing account verification failed.');}
// PostgREST upserts need explicit merge semantics, supplied by this dedicated call.
async function upsertGrant(sub,c){
 if(sub.livemode!==c.live)fail(400,'Billing mode mismatch.');
 const customer=await stripe('customers/'+encodeURIComponent(typeof sub.customer==='string'?sub.customer:sub.customer.id),c);
 const grant=subscriptionGrant(sub,customer,c);
 if(!grant.email){
  // Deleted customers no longer carry email. Revoke the known source grant
  // rather than silently leaving its former email paid through period end.
  const known=await supa('pro_entitlements?source=eq.stripe&source_id=eq.'+encodeURIComponent(sub.id)+'&select=email');
  if(known.length!==1)return;
  grant.email=known[0].email;grant.status='inactive';grant.evidence.subject_unavailable=true;
 }
 await rpc('pro_set_entitlement',{p_grant:grant});
}
async function refreshCustomer(customerId,c){
 const customer=await stripe('customers/'+encodeURIComponent(customerId),c);
 let offset=0;
 for(let page=0;page<5;page++){
  const rows=await supa('pro_entitlements?source=eq.stripe&evidence->>customer=eq.'+encodeURIComponent(customerId)+'&order=source_id.asc&limit=100&offset='+offset+'&select=source_id,email,expires_at,evidence');
  for(const row of rows){
   if(customer.deleted){
    await rpc('pro_set_entitlement',{p_grant:{source:'stripe',source_id:row.source_id,email:row.email,status:'inactive',expires_at:row.expires_at,evidence:{...row.evidence,customer:customerId,subject_unavailable:true,verified_at:new Date().toISOString()}}});
   }else await upsertGrant(await stripe('subscriptions/'+encodeURIComponent(row.source_id),c),c);
  }
  if(rows.length<100)return;
  offset+=100;
 }
 fail(503,'Customer membership history requires an administrative reconciliation.');
}
export async function reconcileEvent(event){
 const c=stripeConfig();if(event.livemode!==c.live||(event.account&&event.account!==c.account))fail(400,'Billing event scope mismatch.');
 return withLease(async()=>{
  await verifyAccount(c);
  const seen=await supa('pro_stripe_events?event_id=eq.'+encodeURIComponent(event.id)+'&select=event_id');
  if(seen.length)return {received:true,duplicate:true};
  const obj=event.data?.object;
  if(['customer.deleted','customer.updated'].includes(event.type)&&/^cus_[a-zA-Z0-9]+$/.test(obj?.id||''))await refreshCustomer(obj.id,c);
  else{
   const candidate=event.type.startsWith('customer.subscription.')?obj?.id:obj?.subscription??obj?.parent?.subscription_details?.subscription;
   const id=typeof candidate==='string'?candidate:candidate?.id;
   if(typeof id==='string'&&/^sub_[a-zA-Z0-9]+$/.test(id))await upsertGrant(await stripe('subscriptions/'+id,c),c);
  }
  await supa('pro_stripe_events',{method:'POST',body:{event_id:event.id}});
  return {received:true};
 });
}
export async function syncEmail(email){
 const c=stripeConfig();email=normalizeEmail(email);
 return withLease(async()=>{
  await verifyAccount(c);
  // Complete exact-email customer pagination, bounded to protect the function.
  let after='',pages=0,customerCount=0;
  do{
   const customers=await stripe('customers?email='+encodeURIComponent(email)+'&limit=100'+after,c);
   for(const customer of customers.data){
    if(normalizeEmail(customer.email)!==email||customer.livemode!==c.live)continue;
    customerCount++;let cursor='',subPages=0;
    do{
     const subscriptions=await stripe('subscriptions?customer='+encodeURIComponent(customer.id)+'&status=all&limit=100'+cursor,c);
     for(const sub of subscriptions.data)await upsertGrant(sub,c);
     if(!subscriptions.has_more)break;
     if(++subPages>=5)fail(503,'Membership history requires an administrative reconciliation.');
     cursor='&starting_after='+encodeURIComponent(subscriptions.data.at(-1).id);
    }while(true);
   }
   if(!customers.has_more)break;
   if(++pages>=5)fail(503,'Membership history requires an administrative reconciliation.');
   after='&starting_after='+encodeURIComponent(customers.data.at(-1).id);
  }while(true);
  return {synced:true,customerCount,coverage:'Verified allowlisted Stripe subscriptions only; other Substack billing requires reconciliation.'};
 });
}

export async function reconcileKnown(){
 const c=stripeConfig();return withLease(async()=>{
  await verifyAccount(c);
  const rows=await supa('pro_entitlements?source=eq.stripe&order=updated_at.asc&limit=20&select=source_id');
  for(const row of rows)await upsertGrant(await stripe('subscriptions/'+encodeURIComponent(row.source_id),c),c);
  return {checked:rows.length};
 });
}
