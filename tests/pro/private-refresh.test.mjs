import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {refreshBundle,runCli} from '../../scripts/pro/refresh-dfs.mjs';

test('direct runner rejects incomplete output before credentials or storage are accessed',async()=>{
 let requests=0;
 await assert.rejects(refreshBundle({}, {}, {fetchImpl:async()=>{requests++;throw Error('Unexpected request');}}),/validated upcoming slate/);
 assert.equal(requests,0);
});
test('direct runner validation does not promote a historical or unapproved source',async()=>{
 for(const publishApproved of [false,true]){
  let requests=0;
  const bundle={slates:[{model:{sport:'NBA',publishApproved,capturedAt:'2020-01-01T00:00:00Z',validUntil:'2020-01-02T00:00:00Z'},manifest:{}}]};
  await assert.rejects(refreshBundle(bundle,{}, {validateOnly:true,fetchImpl:async()=>{requests++;}}));
  assert.equal(requests,0);
  assert.equal(bundle.slates[0].model.capturedAt,'2020-01-01T00:00:00Z');
  assert.equal(bundle.slates[0].model.publishApproved,publishApproved);
 }
});
test('local bundle CLI rejects unknown flags, directories and invalid JSON',async()=>{
 const dir=await mkdtemp(join(tmpdir(),'rr-refresh-'));
 try{
  await assert.rejects(runCli(['--bundle',dir,'--publish-anyway']),/Use --bundle/);
  await assert.rejects(runCli(['--bundle',dir]),/Invalid private refresh bundle/);
  const file=join(dir,'bundle.json');await writeFile(file,'{');
  await assert.rejects(runCli(['--bundle',file,'--validate-only']),SyntaxError);
  await writeFile(file,'{}');
  await assert.rejects(runCli(['--bundle',file,'--validate-only']),/validated upcoming slate/);
 }finally{await rm(dir,{recursive:true,force:true});}
});

const now=new Date('2026-11-16T20:00:00Z'),capturedAt='2026-11-16T19:59:00Z',validUntil='2026-11-16T21:00:00Z';
function fixture(){
 const slates=['NBA','NFL'].map(sport=>{
  const positions=sport==='NBA'?['PG','SG','SF','PF','C']:['QB','RB','WR','TE','DST'];
  const players=Array.from({length:20},(_,i)=>({id:String(i+1),name:'Synthetic '+i,team:i%2?'ATL':'BOS',opponent:i%2?'BOS':'ATL',gameId:String(Math.floor(i/10)),projection:20+i/10}));
  const model={schemaVersion:1,kind:'projections',sport,scoring:'DraftKings',publishApproved:true,capturedAt,validUntil,provenance:{modelHash:'fixture-model',sourceHash:'fixture-source'},players};
  const joint={...model,kind:'joint',draws:10000,joint:true,modelHash:'fixture-model',scores:Object.fromEntries(players.map(p=>[p.id,Array(10000).fill(p.projection)]))};
  const manifest={schemaVersion:1,sport,slateId:'synthetic',format:'DraftKings Classic',publishApproved:true,completeSalaryPool:true,salarySource:'synthetic test',injurySource:'synthetic test',scheduleSource:'synthetic test',salaryCapturedAt:capturedAt,injuryCapturedAt:capturedAt,scheduleCapturedAt:capturedAt,gameIds:['0','1'],playerMappings:players.map(p=>({dkId:p.id,modelId:p.id,team:p.team,opponent:p.opponent,gameId:p.gameId,status:'active',verifiedAt:capturedAt,startsAt:validUntil}))};
  const salaryCsv='ID,Name,Position,Salary,TeamAbbrev\n'+players.map((p,i)=>[p.id,p.name,positions[i%5],4000,p.team].join(',')).join('\n');
  return {model,joint,manifest,salaryCsv};
 });
 return {slates,nba:{basic:slates[0].model,distributions:{...slates[0].model,kind:'distributions',draws:10000}}};
}
const env={SUPABASE_URL:'https://storage.example',SUPABASE_SERVICE_ROLE_KEY:'synthetic-test-credential'};
test('complete direct bundle validates without any storage configuration or request',async()=>{
 let calls=0;const result=await refreshBundle(fixture(),{}, {now,validateOnly:true,fetchImpl:async()=>{calls++;}});
 assert.equal(result.published,0);assert.equal(result.validated,6);assert.equal(calls,0);
});
test('private writes use immutable slate paths and switch catalogs last',async()=>{
 const calls=[];await refreshBundle(fixture(),env,{now,fetchImpl:async(url,options)=>{calls.push({url,options});return {ok:true};}});
 assert.equal(calls.length,6);
 assert(calls.slice(-2).every(c=>c.url.endsWith('/slates.json')));
 assert(calls.filter(c=>c.url.includes('/slates/')).every(c=>c.options.headers['x-upsert']==='false'));
});
test('failed object upload stops before either catalog switch and conceals transport secrets',async()=>{
 const calls=[];
 await assert.rejects(refreshBundle(fixture(),env,{now,fetchImpl:async url=>{calls.push(url);if(calls.length===2)throw Error(env.SUPABASE_SERVICE_ROLE_KEY);return {ok:true};}}),e=>e.message==='Private artifact upload failed; refresh stopped.');
 assert.equal(calls.length,2);assert(!calls.some(url=>url.endsWith('/slates.json')));
});
test('expired complete bundle fails before any write and retains original source dates',async()=>{
 const bundle=fixture();let calls=0;
 await assert.rejects(refreshBundle(bundle,env,{now:new Date('2026-11-16T22:00:00Z'),fetchImpl:async()=>{calls++;}}));
 assert.equal(calls,0);assert.equal(bundle.slates[0].model.capturedAt,capturedAt);
});
