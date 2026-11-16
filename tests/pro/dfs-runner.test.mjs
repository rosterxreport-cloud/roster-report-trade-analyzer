import test from 'node:test';import assert from 'node:assert/strict';
import {createRefreshHandler} from '../../api/dfs-refresh.mjs';
const env={VERCEL_ENV:'preview',DFS_RUNNER_TOKEN:'synthetic-runner',DFS_PUBLISH_TOKEN:'synthetic-publisher',DFS_PUBLISH_URL:'https://publisher.example',DFS_SANDBOX_NAME:'private-test'};
function response(){return {code:null,value:null,setHeader(){},status(code){this.code=code;return this;},json(value){this.value=value;return this;}};}
test('runner denies unverified callers and all production invocations before creating compute',async()=>{
 let calls=0;const SandboxClass={get:async()=>{calls++;throw Error('Unexpected compute');}};
 for(const custom of [env,{...env,VERCEL_ENV:'production'}]){
  const res=response();await createRefreshHandler({SandboxClass,env:custom})({method:'POST',headers:{authorization:'invalid'}},res);assert([401,403].includes(res.code));
 }assert.equal(calls,0);
});
test('runner avoids overlapping jobs when persistent lease is taken',async()=>{
 let computes=0;const res=response();
 await createRefreshHandler({env,SandboxClass:{get:async()=>{computes++;}},fetchImpl:async()=>Response.json({acquired:false})})({method:'POST',headers:{authorization:'Bearer synthetic-runner'}},res);
 assert.equal(res.value.state,'already-running');assert.equal(computes,0);
});
test('runner executes only the fixed private worker and releases resources after success',async()=>{
 const ops=[];let stopped=0;
 const SandboxClass={get:async({name})=>{assert.equal(name,'private-test');return {runCommand:async options=>{assert.deepEqual(options.args,['240','/vercel/private-recovery/venv/bin/python','/vercel/toolkit/scripts/pro/run-private-dfs.py']);return {exitCode:0,stdout:async()=>JSON.stringify({state:'partial',nba:{state:'published'}})};},stop:async()=>{stopped++;}};}};
 const fetchImpl=async(_,options)=>{const op=JSON.parse(options.body).operation;ops.push(op);return Response.json(op==='acquire'?{acquired:true}:{released:true});};
 const res=response();await createRefreshHandler({env,SandboxClass,fetchImpl})({method:'POST',headers:{authorization:'Bearer synthetic-runner'}},res);
 assert.equal(res.code,200);assert.equal(res.value.nba.state,'published');assert.equal(stopped,1);assert.deepEqual(ops,['acquire','release']);assert(!JSON.stringify(res.value).includes('synthetic-publisher'));
});
test('failed private execution retains artifacts, stops compute and releases lease',async()=>{
 const ops=[];let stopped=0;const res=response();
 await createRefreshHandler({env,SandboxClass:{get:async()=>({runCommand:async()=>({exitCode:1}),stop:async()=>{stopped++;}})},fetchImpl:async(_,options)=>{const op=JSON.parse(options.body).operation;ops.push(op);return Response.json(op==='acquire'?{acquired:true}:{released:true});}})({method:'POST',headers:{authorization:'Bearer synthetic-runner'}},res);
 assert.equal(res.code,503);assert.equal(stopped,1);assert.deepEqual(ops,['acquire','release']);
});
