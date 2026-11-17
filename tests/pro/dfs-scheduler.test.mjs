import test from 'node:test';
import assert from 'node:assert/strict';
let handler, background;
const nativeFetch=globalThis.fetch;
globalThis.Deno={env:{get:key=>({SUPABASE_URL:'https://staging.example',SUPABASE_SERVICE_ROLE_KEY:'test-service-key'})[key]},serve:fn=>{handler=fn;}};
globalThis.EdgeRuntime={waitUntil:promise=>{background=promise;}};
await import('../../supabase/functions/dfs-schedule/index.ts');
const runner='https://roster-report-trade-analyzer-git-feat-5550b3-the-roster-report.vercel.app/api/dfs-refresh/';
const config={signingKey:'test-signing-key',runnerUrl:runner,runnerToken:'test-runner-key',bypass:'test-bypass-key'};
const encoder=new TextEncoder();
async function request({offset=0,invalid=false}={}){
 const stamp=String(Math.floor(Date.now()/1000)+offset),nonce=crypto.randomUUID();
 const key=await crypto.subtle.importKey('raw',encoder.encode(config.signingKey),{name:'HMAC',hash:'SHA-256'},false,['sign']);
 const signature=Buffer.from(await crypto.subtle.sign('HMAC',key,encoder.encode(stamp+'.'+nonce))).toString('hex');
 return new Request('https://staging.example/functions/v1/dfs-schedule',{method:'POST',headers:{'x-dfs-time':stamp,'x-dfs-nonce':nonce,'x-dfs-signature':invalid?'0'.repeat(64):signature}});
}
function mock({claimed=true,runnerStatus=200,runnerThrows=false}={}){
 const calls=[];
 globalThis.fetch=async(url,options)=>{
  calls.push({url,options});
  if(url.endsWith('/rpc/dfs_private_cron_config'))return Response.json(config);
  if(url.endsWith('/rpc/dfs_claim_cron_nonce'))return Response.json(claimed);
  if(url===runner){if(runnerThrows)throw Error('transport failed');return Response.json({state:runnerStatus===200?'partial':'failed',slates:{NFL:{state:'waiting'}}},{status:runnerStatus});}
  return new Response(null,{status:204});
 };
 return calls;
}
test('expired scheduler proofs fail before privileged configuration access',async()=>{const calls=mock();assert.equal((await handler(await request({offset:-180}))).status,401);assert.equal(calls.length,0);});
test('invalid scheduler signatures cannot claim a nonce or start the runner',async()=>{const calls=mock();assert.equal((await handler(await request({invalid:true}))).status,401);assert.equal(calls.length,1);});
test('replayed scheduler nonce cannot invoke the runner',async()=>{const calls=mock({claimed:false});assert.equal((await handler(await request())).status,409);assert.ok(!calls.some(c=>c.url===runner));});
test('valid trigger authenticates only to the fixed preview and stores the actual partial receipt',async()=>{
 const calls=mock();assert.equal((await handler(await request())).status,202);await background;
 const invocation=calls.find(c=>c.url===runner);assert.equal(invocation.options.headers.Authorization,'Bearer test-runner-key');assert.equal(invocation.options.headers['x-vercel-protection-bypass'],'test-bypass-key');assert.equal(invocation.options.redirect,'error');assert.equal(invocation.options.body,'{}');
 const receipt=calls.find(c=>c.options.method==='PATCH');const saved=JSON.parse(receipt.options.body);assert.equal(saved.status,'completed');assert.equal(saved.receipt.slates.NFL.state,'waiting');
});
test('runner HTTP failure remains a failed refresh receipt',async()=>{const calls=mock({runnerStatus:503});await handler(await request());await background;assert.equal(JSON.parse(calls.find(c=>c.options.method==='PATCH').options.body).status,'failed');});
test('runner transport failure records failure without leaking credential values',async()=>{const calls=mock({runnerThrows:true});await handler(await request());await background;const saved=calls.find(c=>c.options.method==='PATCH').options.body;assert.equal(JSON.parse(saved).status,'failed');assert.ok(!saved.includes(config.runnerToken));assert.ok(!saved.includes(config.bypass));});
test.after(()=>{globalThis.fetch=nativeFetch;delete globalThis.Deno;delete globalThis.EdgeRuntime;});
