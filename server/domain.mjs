import crypto from 'node:crypto';
export class HttpError extends Error { constructor(status,message){super(message);this.status=status;} }
export const fail=(status,message)=>{throw new HttpError(status,message)};
export const pacificDay=(now=new Date())=>new Intl.DateTimeFormat('en-CA',{timeZone:'America/Los_Angeles',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
export const normalizeEmail=s=>String(s||'').trim().toLowerCase();
export function stripeSignature(raw,header,secret,now=Date.now()){
 if(!secret||!header)return false;
 const values=header.split(',').map(x=>x.split('='));const t=values.find(x=>x[0]==='t')?.[1];
 if(!/^\d+$/.test(t||'')||Math.abs(now/1000-Number(t))>300)return false;
 const expected=crypto.createHmac('sha256',secret).update(t+'.'+raw).digest('hex');
 return values.some(([k,v])=>k==='v1'&&/^[a-f0-9]{64}$/.test(v)&&crypto.timingSafeEqual(Buffer.from(v,'hex'),Buffer.from(expected,'hex')));
}
export function subscriptionGrant(sub,customer,config,now=Date.now()){
 const items=sub.items?.data||[];const periods=items.map(x=>x.current_period_end).filter(Number.isFinite);
 const end=sub.current_period_end??(periods.length?Math.min(...periods):0);
 const publication=items.some(i=>config.prices.includes(i.price?.id));
 const paid=publication&&sub.status==='active'&&!sub.pause_collection&&end*1000>now&&!customer.deleted;
 return {source:'stripe',source_id:sub.id,email:normalizeEmail(customer.email),status:paid?'active':'inactive',expires_at:new Date(Math.max(0,end)*1000).toISOString(),evidence:{customer:customer.id,publication,subscription_status:sub.status,cancel_at_period_end:!!sub.cancel_at_period_end,verified_at:new Date(now).toISOString()}};
}
export function activeMembership(rows,now=Date.now()) {return rows.some(x=>x.status==='active'&&Date.parse(x.expires_at)>now);}
export function validateArtifact(a,{kind,sport,now=Date.now(),current=true}={}){
 if(!a||a.schemaVersion!==1||a.kind!==kind||a.sport!==sport||a.publishApproved!==true)fail(503,'No release-approved model data is available.');
 if(!a.provenance?.modelHash||!a.provenance?.sourceHash||!Number.isFinite(Date.parse(a.capturedAt)))fail(503,'Model provenance is incomplete.');
 if(current&&(!Number.isFinite(Date.parse(a.validUntil))||Date.parse(a.validUntil)<=now||Date.parse(a.capturedAt)>now))fail(503,'Model inputs require a fresh pre-lock update.');
 if(!Array.isArray(a.players)||!a.players.length)fail(503,'Model player data is unavailable.');
 return a;
}
