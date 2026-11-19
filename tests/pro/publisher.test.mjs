import test from 'node:test';import assert from 'node:assert/strict';import crypto from 'node:crypto';import fs from 'node:fs';
import {createPublisher,validatePublishedObject} from '../../server/dfs-publisher.mjs';
const raw=fs.readFileSync(new URL('../../config/nba-incumbent-release.json',import.meta.url)),policy=JSON.parse(raw),policyHash=crypto.createHash('sha256').update(raw).digest('hex');
const token='synthetic-publisher-test',expectedTokenHash=crypto.createHash('sha256').update(token).digest('hex');
const now=Date.parse('2026-11-16T20:00:00Z');
function artifact(){return {schemaVersion:1,kind:'projections',sport:'NBA',scoring:'DraftKings',publishApproved:true,capturedAt:'2026-11-16T19:00:00Z',validUntil:'2026-11-17T00:00:00Z',players:[{id:'1',name:'Synthetic',projection:30}],provenance:{modelHash:policy.modelFingerprint,sourceHash:'synthetic',model:policy.model,simulatorHash:policy.sourceFiles['simulate_slate.py'],releaseAuthorization:{policyHash}}};}
const request=(data,credential=token)=>new Request('https://publisher.example',{method:'POST',headers:{Authorization:'Bearer '+credential},body:JSON.stringify(data)});
test('publisher rejects invalid identity and arbitrary storage paths before storage access',async()=>{
 let calls=0;const handler=createPublisher({expectedTokenHash,root:'https://storage.example',key:'synthetic-key',now:()=>now,fetchImpl:async()=>{calls++;return new Response('{}');}});
 assert.equal((await handler(request({path:'nba/basic.json',data:artifact()},'invalid'))).status,401);
 assert.equal((await handler(request({path:'../source.zip',data:{}}))).status,403);assert.equal(calls,0);
});
test('publisher rejects stale or experimental projections without storage writes',async()=>{
 let calls=0;const handler=createPublisher({expectedTokenHash,root:'https://storage.example',key:'synthetic-key',now:()=>now,fetchImpl:async()=>{calls++;return new Response('{}');}});
 const a=artifact();a.validUntil='2020-01-01T00:00:00Z';assert.equal((await handler(request({path:'nba/basic.json',data:a}))).status,400);
 a.validUntil='2026-11-17T00:00:00Z';a.provenance.modelHash='candidate';assert.equal((await handler(request({path:'nba/basic.json',data:a}))).status,400);assert.equal(calls,0);
});
test('publisher writes only the fixed private bucket and returns a content receipt',async()=>{
 const calls=[];const handler=createPublisher({expectedTokenHash,root:'https://storage.example',key:'synthetic-key',now:()=>now,fetchImpl:async(url,options)=>{calls.push({url,options});return new Response('{}');}});
 const r=await handler(request({path:'nba/basic.json',data:artifact()}));assert.equal(r.status,200);
 const receipt=await r.json();assert.equal(receipt.sha256.length,64);assert.equal(calls[0].url,'https://storage.example/storage/v1/object/toolkit-private/nba/basic.json');
 assert(!JSON.stringify(receipt).includes('synthetic-key'));
});
test('catalog cannot switch to absent objects',async()=>{
 const calls=[];const handler=createPublisher({expectedTokenHash,root:'https://storage.example',key:'synthetic-key',now:()=>now,fetchImpl:async(url,options)=>{calls.push({url,options});return new Response('{}',{status:404});}});
 const r=await handler(request({path:'nba/slates.json',data:{capturedAt:'2026-11-16T19:00:00Z',slates:[{id:'missing',name:'Synthetic',locksAt:'2026-11-17T00:00:00Z'}]}}));
 assert.equal(r.status,400);assert.equal(calls.length,1);assert.equal(calls[0].options.method,undefined);
});
