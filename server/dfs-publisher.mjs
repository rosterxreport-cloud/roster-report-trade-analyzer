import {Buffer} from 'node:buffer';
import crypto from 'node:crypto';
import {validateArtifact} from './domain.mjs';
import {validateSlate} from './optimizer.mjs';
import {validateModelLineage} from './model-lineage.mjs';
const hash=body=>crypto.createHash('sha256').update(body).digest('hex');
export function validatePublishedObject(path,data,now=Date.now()){
 if(typeof path!=='string'||! /^(nba|nfl)\/(basic|distributions|slates\/[-a-zA-Z0-9_]{1,80})\.json$/.test(path))throw Error('Unsupported publication path.');
 const sport=path.split('/')[0].toUpperCase();
 if(data?.sport!==sport)throw Error('Publication sport mismatch.');
 validateModelLineage(data);
 if(path.includes('/slates/')){
  validateSlate(data,now);
  if(!path.endsWith('/'+data.slateId+'.json'))throw Error('Slate identity mismatch.');
 }else{
  validateArtifact(data,{kind:path.endsWith('/basic.json')?'projections':'distributions',sport,now});
  if(!(data.scoring==='DraftKings'||(sport==='NFL'&&data.kind==='projections'&&data.scoring==='RR-DK-core'))||(data.kind==='distributions'&&data.draws!==10000))throw Error('Incomplete scoring or distributions.');
 }
 return data;
}
export function createPublisher({expectedTokenHash,root,key,fetchImpl=fetch,now=Date.now}){
 const reply=(body,status=200)=>Response.json(body,{status,headers:{'Cache-Control':'no-store'}});
 return async request=>{
  if(request.method!=='POST')return reply({error:'Method not allowed'},405);
  const token=request.headers.get('Authorization')?.replace(/^Bearer /,'')||'';
  const digest=hash(token);
  if(!/^[a-f0-9]{64}$/.test(expectedTokenHash)||!crypto.timingSafeEqual(Buffer.from(digest),Buffer.from(expectedTokenHash)))return reply({error:'Unauthorized'},401);
  try{
   const text=await request.text();if(text.length>64*1024*1024)return reply({error:'Request too large'},413);
   const input=JSON.parse(text),path=input.path;
   const authHeaders={Authorization:'Bearer '+key,apikey:key,'Content-Type':'application/json'};
   if(['acquire','release'].includes(input.operation)){
    if(!/^[0-9a-f-]{36}$/i.test(input.runId||''))return reply({error:'Invalid run identity'},400);
    const rpc=input.operation==='acquire'?'dfs_acquire_runner':'dfs_release_runner';
    const r=await fetchImpl(root+'/rest/v1/rpc/'+rpc,{method:'POST',headers:authHeaders,body:JSON.stringify({p_owner:input.runId}),redirect:'error'});
    if(!r.ok)return reply({error:'Runner coordination unavailable'},502);
    return reply({[input.operation==='acquire'?'acquired':'released']:await r.json()});
   }
   const catalog=typeof path==='string'&&/^(nba|nfl)\/slates\.json$/.test(path);
   const object=typeof path==='string'&&/^(nba|nfl)\/(basic|distributions|slates\/[-a-zA-Z0-9_]{1,80})\.json$/.test(path);
   if(!catalog&&!object)return reply({error:'Unsupported publication path'},403);
   const headers={Authorization:'Bearer '+key,apikey:key};
   const url=root+'/storage/v1/object/toolkit-private/'+path;
   if(input.inspect===true){
    const r=await fetchImpl(root+'/storage/v1/object/authenticated/toolkit-private/'+path,{headers,redirect:'error'});
    if(!r.ok)return reply({error:'Published object unavailable'},404);
    const body=await r.text();return reply({path,sha256:hash(body),bytes:Buffer.byteLength(body)});
   }
   const data=input.data;
   if(catalog){
    const sport=path.split('/')[0].toUpperCase();
    if(!Array.isArray(data?.slates)||!data.slates.length||data.slates.length>40||!Number.isFinite(Date.parse(data.capturedAt))||Date.parse(data.capturedAt)>now())throw Error('Invalid slate catalog.');
    const ids=new Set();
    for(const row of data.slates){
     if(!/^[-a-zA-Z0-9_]{1,80}$/.test(row.id)||ids.has(row.id)||!row.name||Date.parse(row.locksAt)<=now())throw Error('Invalid catalog entry.');
     ids.add(row.id);
     const objectPath=path.split('/')[0]+'/slates/'+row.id+'.json';
     const r=await fetchImpl(root+'/storage/v1/object/authenticated/toolkit-private/'+objectPath,{headers,redirect:'error'});
     if(!r.ok)throw Error('Catalog references an unpublished slate.');
     const artifact=await r.json();validatePublishedObject(objectPath,artifact,now());
     if(artifact.sport!==sport||artifact.validUntil!==row.locksAt)throw Error('Catalog does not match its slate.');
    }
   }else validatePublishedObject(path,data,now());
   const body=JSON.stringify(data);
   const r=await fetchImpl(url,{method:'POST',headers:{...headers,'Content-Type':'application/json','x-upsert':path.includes('/slates/')?'false':'true'},body,redirect:'error'});
   if(!r.ok)return reply({error:'Private publication failed'},r.status===409?409:502);
   return reply({path,sha256:hash(body),bytes:Buffer.byteLength(body)});
  }catch{return reply({error:'Publication rejected; no invalid catalog or object was accepted'},400);}
 };
}
