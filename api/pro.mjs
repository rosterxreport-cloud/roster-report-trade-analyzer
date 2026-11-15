import crypto from 'node:crypto';
import fs from 'node:fs';
import {fail,HttpError,normalizeEmail,activeMembership,pacificDay,stripeSignature,validateArtifact} from '../server/domain.mjs';
import {config as serviceConfig,supa,rpc,modelArtifact} from '../server/store.mjs';
import {reconcileEvent,syncEmail,reconcileKnown} from '../server/membership.mjs';
import {optimize} from '../server/optimizer.mjs';
import {tradeAnalysis} from '../server/trade.mjs';
export const config={api:{bodyParser:false}};
const read=p=>JSON.parse(fs.readFileSync(new URL('../'+p,import.meta.url),'utf8'));
const cookieOptions='; HttpOnly; Secure; SameSite=Lax; Path=/';
function cookies(req){return Object.fromEntries((req.headers.cookie||'').split(';').map(x=>x.trim().split('=')).filter(x=>x.length===2));}
function session(res,data){res.setHeader('Set-Cookie',[`rr_access=${data.access_token}${cookieOptions}; Max-Age=${Math.min(data.expires_in||3600,3600)}`,`rr_refresh=${data.refresh_token}${cookieOptions}; Max-Age=2592000`]);}
async function body(req,max=16384){
 if(req.body!==undefined){let parsed;try{parsed=typeof req.body==='object'?req.body:JSON.parse(req.body);}catch{fail(400,'Invalid request body.');}if(!parsed||Array.isArray(parsed)||typeof parsed!=='object')fail(400,'Invalid request body.');if(Buffer.byteLength(JSON.stringify(parsed))>max)fail(413,'Request too large.');return parsed;}
 let s='';for await(const chunk of req){s+=chunk;if(Buffer.byteLength(s)>max)fail(413,'Request too large.');}try{return JSON.parse(s||'{}');}catch{fail(400,'Invalid request body.');}
}
async function rate(key,limit,seconds=60){if(!await rpc('pro_rate_limit',{p_key:key,p_limit:limit,p_seconds:seconds}))fail(429,'Too many requests. Please try again shortly.');}
async function identity(req){const token=cookies(req).rr_access;if(!token)fail(401,'Sign in to use this tool.');const user=await supa('user',{auth:true,token});if(!user.id||!user.email_confirmed_at)fail(401,'Verify your email before continuing.');let claims;try{claims=JSON.parse(Buffer.from(token.split('.')[1],'base64url'));}catch{fail(401,'Invalid session.');}if(!/^[0-9a-f-]{36}$/i.test(claims.session_id||'')||!await rpc('pro_session_active',{p_user:user.id,p_session:claims.session_id}))fail(401,'Your session has ended. Please sign in again.');return user;}
async function membership(user){const rows=await supa('pro_entitlements?email=eq.'+encodeURIComponent(normalizeEmail(user.email))+'&select=status,expires_at,source');return {pro:activeMembership(rows),memberships:rows};}
async function requirePro(req){const user=await identity(req),status=await membership(user);if(!status.pro)fail(403,'Roster Report Pro membership is required.');return user;}
function origin(req){const e=process.env;const expected=e.APP_ORIGIN||(e.VERCEL_URL?'https://'+e.VERCEL_URL:null);if(!expected||req.headers.origin!==expected)fail(403,'Request origin could not be verified.');}
export default async function handler(req,res){
 res.setHeader('Cache-Control','private, no-store');res.setHeader('X-Content-Type-Options','nosniff');
 try{
  const action=new URL(req.url,'https://toolkit.local').searchParams.get('action')||'status';
  let result;
  if(action==='reconcile'){
   if(req.method!=='GET'||!process.env.CRON_SECRET||req.headers.authorization!=='Bearer '+process.env.CRON_SECRET)fail(401,'Unauthorized.');
   result=await reconcileKnown();
  }else if(action==='webhook'){
   if(req.method!=='POST')fail(405,'Method not allowed.');
   let raw='';for await(const c of req){raw+=c;if(Buffer.byteLength(raw)>262144)fail(413,'Request too large.');}
   if(!stripeSignature(raw,req.headers['stripe-signature'],process.env.STRIPE_WEBHOOK_SECRET))fail(400,'Invalid webhook signature.');
   let event;try{event=JSON.parse(raw);}catch{fail(400,'Invalid event.');}
   result=await reconcileEvent(event);
  }else if(req.method==='GET'&&action==='status'){
   let serviceConfigured=true;try{serviceConfig();}catch{serviceConfigured=false;}
   result={accountsConfigured:serviceConfigured,billingVerified:process.env.STRIPE_SYNC_VERIFIED==='true',upgradeUrl:'https://rosterxreport.substack.com/subscribe',dailyReset:'Midnight America/Los_Angeles',modelRelease:'Requires approved private model artifacts'};
  }else if(req.method==='GET'&&action==='nba-basic'){
   const a=validateArtifact(await modelArtifact('nba/basic.json'),{kind:'projections',sport:'NBA'});
   result={capturedAt:a.capturedAt,model:a.provenance.modelHash,players:a.players.map(({id,name,team,opponent,minutes,statline,projection})=>({id,name,team,opponent,minutes,statline,projection}))};
  }else if(req.method==='GET'&&action==='slates'){
   const sport=new URL(req.url,'https://toolkit.local').searchParams.get('sport');if(!['NBA','NFL'].includes(sport))fail(400,'Unsupported sport.');
   const a=await modelArtifact(sport.toLowerCase()+'/slates.json');
   if(!Array.isArray(a.slates))fail(503,'Current slates are unavailable.');
   result={slates:a.slates.filter(s=>Date.parse(s.locksAt)>Date.now()).map(({id,name,locksAt})=>({id,name,locksAt}))};
  }else if(req.method==='GET'&&action==='account'){
   const u=await identity(req),m=await membership(u);
   const usage=await supa('pro_usage?user_id=eq.'+encodeURIComponent(u.id)+'&day=eq.'+pacificDay()+'&select=request_id');
   result={email:u.email,...m,freeLineupUsed:!!usage.length,day:pacificDay(),dailyReset:'Midnight Pacific'};
  }else{
   if(req.method!=='POST')fail(405,'Method not allowed.');origin(req);const input=await body(req);
   const ip=req.headers['x-vercel-forwarded-for']||req.headers['x-forwarded-for']||'unknown';
   const hash=crypto.createHmac('sha256',serviceConfig().RATE_LIMIT_SECRET).update(String(ip)).digest('hex');
   await rate('ip:'+hash,60);
   if(action==='login'){
    const email=normalizeEmail(input.email);if(!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)||email.length>254)fail(400,'Enter a valid email.');
    await rate('login:'+hash,5,900);await rate('email:'+crypto.createHash('sha256').update(email).digest('hex'),3,900);
    await supa('otp',{auth:true,method:'POST',body:{email,create_user:true}});result={sent:true};
   }else if(action==='verify'){
    await rate('verify:'+hash,10,900);
    if(!/^\d{6,8}$/.test(input.code||''))fail(400,'Enter the emailed verification code.');
    const data=await supa('verify',{auth:true,method:'POST',body:{email:normalizeEmail(input.email),token:input.code,type:'email'}});
    if(!data.user?.email_confirmed_at||!data.access_token||!data.refresh_token)fail(401,'Email verification failed.');session(res,data);let syncPending=false;if(process.env.STRIPE_SYNC_VERIFIED==='true'){try{await syncEmail(data.user.email);}catch{syncPending=true;}}result={signedIn:true,syncPending};
   }else if(action==='refresh'){
    const token=cookies(req).rr_refresh;if(!token)fail(401,'Sign in again.');
    const data=await supa('token?grant_type=refresh_token',{auth:true,method:'POST',body:{refresh_token:token}});session(res,data);result={refreshed:true};
   }else if(action==='logout'){
    const token=cookies(req).rr_access;if(token)await supa('logout',{auth:true,method:'POST',token});
    res.setHeader('Set-Cookie',[`rr_access=${cookieOptions}; Max-Age=0`,`rr_refresh=${cookieOptions}; Max-Age=0`]);result={signedOut:true};
   }else if(action==='sync'){
    const u=await identity(req);await rate('sync:'+u.id,2,300);result=await syncEmail(u.email);
   }else if(action==='optimize'){
    const u=await identity(req),m=await membership(u);await rate('optimizer:'+u.id,10);
    if(!['NBA','NFL'].includes(input.sport)||!/^[-a-zA-Z0-9_]{1,80}$/.test(input.slateId||''))fail(400,'Select an available slate.');
    const advanced=input.advanced===true;if(advanced&&!m.pro)fail(403,'Advanced optimization requires Pro.');
    if(!/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(input.requestId||''))fail(400,'A request ID is required.');
    if(!m.pro){const rows=await supa('pro_usage?user_id=eq.'+u.id+'&day=eq.'+pacificDay()+'&select=request_id,result');if(rows.length){if(rows[0].request_id===input.requestId){res.status(200).json(rows[0].result);return;}fail(429,'Your daily free lineup has been used. It resets at midnight Pacific.');}}
    const a=await modelArtifact(input.sport.toLowerCase()+'/slates/'+input.slateId+'.json');
    if(a.slateId!==input.slateId||a.sport!==input.sport)fail(503,'Slate identity mismatch.');
    result=optimize(a,{advanced,count:input.count??1,locks:input.locks??[],excludes:input.excludes??[],stack:input.stack??0,bringBack:input.bringBack===true,maxExposure:input.maxExposure??1});
    if(!m.pro){const saved=await rpc('pro_save_free',{p_user:u.id,p_request:input.requestId,p_result:result});if(!saved.allowed)fail(429,'Your daily free lineup has already been used.');result=saved.result;}
   }else if(action==='simulation'){
    const u=await requirePro(req);await rate('simulation:'+u.id,20);
    const a=validateArtifact(await modelArtifact('nba/distributions.json'),{kind:'distributions',sport:'NBA'});
    if(a.draws!==10000||a.scoring!=='DraftKings')fail(503,'The simulation release is incomplete.');
    result={draws:a.draws,scoring:a.scoring,capturedAt:a.capturedAt,provenance:a.provenance,players:a.players,label:'Simulated outcomes; experimental distribution, not verified historical data'};
   }else if(action==='trade'){
    const u=await requirePro(req);await rate('trade:'+u.id,20);
    result=tradeAnalysis(input,read('server/published-trade-values.json'),read('data/weekly-projections.json'));
   }else fail(404,'Unknown action.');
  }
  res.status(200).json(result);
 }catch(error){const status=error instanceof HttpError?error.status:500;if(status>=500)console.error('Toolkit API error',{status,type:error.name});res.status(status).json({error:error instanceof HttpError?error.message:'The tool is temporarily unavailable.'});}
}
