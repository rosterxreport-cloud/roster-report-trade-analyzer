import crypto from 'node:crypto';
import {Sandbox} from '@vercel/sandbox';
function authorized(value,expected){
 if(!expected||typeof value!=='string')return false;
 const a=Buffer.from(value),b=Buffer.from('Bearer '+expected);
 return a.length===b.length&&crypto.timingSafeEqual(a,b);
}
export function createRefreshHandler({SandboxClass=Sandbox,fetchImpl=fetch,env=process.env}={}){
 return async function handler(req,res){
  res.setHeader('Cache-Control','private, no-store');
  if(env.VERCEL_ENV!=='preview'){res.status(403).json({error:'This runner is restricted to staging.'});return;}
  if(req.method!=='POST'||!authorized(req.headers.authorization,env.DFS_RUNNER_TOKEN)){res.status(401).json({error:'Unauthorized.'});return;}
  if(!env.DFS_PUBLISH_URL||!env.DFS_PUBLISH_TOKEN||!env.DFS_SANDBOX_NAME){res.status(503).json({error:'Private runner is not configured.'});return;}
  const runId=crypto.randomUUID();
  async function coordinate(operation){
   const response=await fetchImpl(env.DFS_PUBLISH_URL,{method:'POST',headers:{Authorization:'Bearer '+env.DFS_PUBLISH_TOKEN,'Content-Type':'application/json'},body:JSON.stringify({operation,runId}),redirect:'error',signal:AbortSignal.timeout(15000)});
   if(!response.ok)throw Error('Runner coordination failed');return response.json();
  }
  const outcome=await (async()=>{
  let sandbox,lease=false;
  try{
   const state=await coordinate('acquire');
   if(!state.acquired)return {status:200,body:{state:'already-running'}};lease=true;
   // Source remains inside the existing private Vercel sandbox. No source-download endpoint exists.
   sandbox=await SandboxClass.get({name:env.DFS_SANDBOX_NAME});
   const commit=env.VERCEL_GIT_COMMIT_SHA;
   if(commit){
    if(!/^[a-f0-9]{40}$/.test(commit))throw Error('Invalid configured worker revision');
    const fetched=await sandbox.runCommand({cmd:'git',args:['fetch','origin',commit],cwd:'/vercel/toolkit'});
    if(fetched.exitCode!==0)throw Error('Worker revision retrieval failed');
    const checked=await sandbox.runCommand({cmd:'git',args:['reset','--hard',commit],cwd:'/vercel/toolkit'});
    if(checked.exitCode!==0)throw Error('Worker revision checkout failed');
   }
   const command=await sandbox.runCommand({cmd:'timeout',args:['240','/vercel/private-recovery/venv/bin/python','/vercel/toolkit/scripts/pro/run-private-dfs.py'],cwd:'/vercel/toolkit',env:{DFS_PUBLISH_URL:env.DFS_PUBLISH_URL,DFS_PUBLISH_TOKEN:env.DFS_PUBLISH_TOKEN,NFL_WEEKLY_FALLBACK_REF:'feat/toolkit-pro-platform'}});
   if(command.exitCode!==0){console.error('Established DFS refresh failed',{runId,exitCode:command.exitCode});return {status:503,body:{state:'failed',runId,error:'Established model refresh failed; prior artifacts retained.'}};}
   const text=await command.stdout();let result;
   try{result=JSON.parse(text.trim().split('\n').at(-1));}catch{throw Error('Invalid private runner receipt');}
   return {status:200,body:{runId,...result}};
  }catch(error){console.error('Private DFS runner unavailable',{runId,type:error.name});return {status:503,body:{state:'failed',runId,error:'Private refresh unavailable; existing artifact expiry remains enforced.'}};}
  finally{
   if(sandbox)try{await sandbox.stop();}catch{console.error('Private runner stop failed',{runId});}
   if(lease)try{await coordinate('release');}catch{console.error('Private runner lease release failed',{runId});}
  }
  })();
  // Hosting may freeze work after the response: finish cleanup before sending it.
  res.status(outcome.status).json(outcome.body);
 };
}
export default createRefreshHandler();
