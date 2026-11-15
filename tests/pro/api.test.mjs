import test from 'node:test';import assert from 'node:assert/strict';import handler from '../../api/pro.mjs';
async function call({action='account',method='GET',origin,body,headers={}}={}){const req={async *[Symbol.asyncIterator](){yield '{}';},url:'/api/pro?action='+action,method,headers:{...headers,...(origin?{origin}:{} )},body};let status,result;const h={};const res={setHeader:(k,v)=>h[k]=v,status:s=>(status=s,res),json:d=>result=d};await handler(req,res);return {status,result,headers:h};}
test('unauthenticated premium APIs and account endpoint fail closed',async()=>{for(const action of ['account','trade','simulation','optimize']){const r=await call({action,method:action==='account'?'GET':'POST',origin:'https://test.example',body:{pro:true}});assert([401,403,503].includes(r.status));assert(!r.result.players);}});
test('cross-origin and missing-origin mutations reject before any work',async()=>{process.env.APP_ORIGIN='https://test.example';for(const origin of [undefined,'https://evil.example']){const r=await call({action:'login',method:'POST',origin,body:{email:'test@example.com'}});assert.equal(r.status,403);}});
test('status discloses no secrets and every API response is uncached',async()=>{const r=await call({action:'status'});assert.equal(r.status,200);assert.equal(r.headers['Cache-Control'],'private, no-store');assert(!JSON.stringify(r.result).includes('SERVICE_ROLE'));});

test('server entitlements override client Pro claims, and revoked sessions deny access',async()=>{
 const originalFetch=globalThis.fetch,env={...process.env};
 Object.assign(process.env,{SUPABASE_URL:'https://database.example',SUPABASE_ANON_KEY:'public-test',SUPABASE_SERVICE_ROLE_KEY:'server-test',RATE_LIMIT_SECRET:'fixture-test',APP_ORIGIN:'https://test.example'});
 const user={id:'00000000-0000-0000-0000-000000000001',email:'fixture@example.com',email_confirmed_at:new Date().toISOString()},token='header.'+Buffer.from(JSON.stringify({session_id:'00000000-0000-0000-0000-000000000002'})).toString('base64url')+'.signature';
 let pro=false,session=true;
 globalThis.fetch=async url=>{
  const p=new URL(url).pathname;let data;
  if(p.endsWith('/user'))data=user;
  else if(p.endsWith('/pro_session_active'))data=session;
  else if(p.includes('/pro_entitlements'))data=pro?[{status:'active',expires_at:new Date(Date.now()+3600000).toISOString(),source:'stripe'}]:[];
  else if(p.endsWith('/pro_rate_limit'))data=true;
  else throw new Error('Unexpected external request '+p);
  return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}});
 };
 try{
  let r=await call({action:'simulation',method:'POST',origin:'https://test.example',headers:{cookie:'rr_access='+token},body:{pro:true}});assert.equal(r.status,403);
  r=await call({action:'optimize',method:'POST',origin:'https://test.example',headers:{cookie:'rr_access='+token},body:{pro:true,advanced:true,sport:'NBA',slateId:'test'}});assert.equal(r.status,403);
  pro=true;session=false;r=await call({action:'simulation',method:'POST',origin:'https://test.example',headers:{cookie:'rr_access='+token},body:{}});assert.equal(r.status,401);
 }finally{globalThis.fetch=originalFetch;for(const k of Object.keys(process.env))if(!(k in env))delete process.env[k];Object.assign(process.env,env);}
});
test('invalid webhook signatures and oversized mutation bodies reject',async()=>{
 process.env.APP_ORIGIN='https://test.example';
 const large=await call({action:'login',method:'POST',origin:'https://test.example',body:{email:'x'.repeat(20000)}});assert.equal(large.status,413);
 const webhook=await call({action:'webhook',method:'POST'});assert.equal(webhook.status,400);
});
