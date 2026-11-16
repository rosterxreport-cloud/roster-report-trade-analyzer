/** Restore the original NFL optimizer scoring basis, with explicit attribution and omissions. */
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import {adaptNFLCore} from '../../server/nfl-core-adapter.mjs';
import {parseDefenses} from '../../server/nfl-defense-source.mjs';
import {fetchPublishedWeekly} from '../../server/published-weekly-source.mjs';
import {refreshBundle} from './refresh-dfs.mjs';
const origin='https://raw.githubusercontent.com/rosterxreport-cloud/roster-report-trade-analyzer/main/';
const team=s=>({LA:'LAR',WSH:'WAS'})[s]||s;
const name=s=>String(s).normalize('NFKC').toLowerCase().replace(/[.\u2019']/g,'').replace(/\s+/g,' ').trim();
async function get(path){const r=await fetch(origin+path,{redirect:'error',signal:AbortSignal.timeout(25000)});if(!r.ok)throw Error('Established weekly source unavailable: '+path);return r.text();}
export async function assembleNFL(pool,salaryCsv,{weekly,manifest,defenses,generatorHash,coreHash,finalSnapshotReceipt},now=Date.now()){
 if(pool.sport!=='NFL'||pool.salaryDataApproved!==true||!pool.validation?.allCsvRowsMatched||!pool.validation?.fullApiPlayerCoverage)throw Error('Complete official NFL salary coverage is required.');
 defenses={...defenses,validUntil:pool.locksAt};
 const raw=adaptNFLCore({weekly,manifest,defenses,generatorHash,coreHash,finalSnapshotReceipt},now);
 const index=new Map(raw.players.filter(p=>p.position!=='DST').map(p=>[name(p.name)+'|'+team(p.team)+'|'+p.position,p]));
 if(index.size!==raw.players.filter(p=>p.position!=='DST').length)throw Error('Ambiguous weekly player identity.');
 const dst=new Map(raw.players.filter(p=>p.position==='DST').map(p=>[team(p.team),p]));
 const players=raw.players.map(p=>({...p,team:team(p.team),opponent:team(p.opponent)})),byId=new Map(players.map(p=>[p.id,p]));
 const mappings=[];
 for(const p of pool.players){
  const position=p.positions[0],model=position==='DST'?dst.get(p.team):index.get(name(p.name)+'|'+p.team+'|'+position);
  const status=String(p.sourceStatus||'').toLowerCase();
  let availability=p.sourceDisabled?'inactive':({out:'out',o:'out',ir:'out',inactive:'inactive',q:'questionable',questionable:'questionable',d:'doubtful',doubtful:'doubtful',p:'probable',probable:'probable',none:'active',active:'active',available:'active','':'active'})[status]||'unverified';
  if(model){
   if(team(model.opponent)!==p.opponent)throw Error('Weekly NFL forecast belongs to a different matchup: '+p.name);
   const record=byId.get(model.id);record.sourceName=model.name;record.name=p.name;record.gameId=p.gameId;record.startsAt=p.startsAt;
   const designation=model.statline?.note?.match(/^(Out|Inactive|Questionable|Doubtful|Probable)\b/i)?.[1].toLowerCase();
   if(designation&&availability==='active')availability=designation;
  }
  mappings.push({dkId:p.id,modelId:model?.id??'unmodeled:'+p.id,team:p.team,opponent:p.opponent,gameId:p.gameId,startsAt:p.startsAt,status:availability,verifiedAt:pool.sourceRecords.draftables.capturedAt,...(!model?{projectionExclusion:{reason:'not-projected-by-established-model',sourceHash:raw.provenance.sourceHash}}:{})});
 }
 const model={...raw,players};
 const slateManifest={schemaVersion:1,sport:'NFL',slateId:'dk-'+pool.draftGroupId,format:'DraftKings Classic',name:'NFL DraftKings Classic · RR core projections',completeSalaryPool:true,publishApproved:true,excludeUnmodeled:true,gameIds:pool.games.map(g=>g.id),playerMappings:mappings,salarySource:pool.sourceRecords.salaryCsv.url,salaryCapturedAt:pool.sourceRecords.salaryCsv.capturedAt,scheduleSource:pool.sourceRecords.draftables.url,scheduleCapturedAt:pool.sourceRecords.draftables.capturedAt,injurySource:pool.sourceRecords.draftables.url+' (operator availability, with RR weekly exclusions)',injuryCapturedAt:pool.sourceRecords.draftables.capturedAt};
 return {sports:['NFL'],slates:[{salaryCsv,manifest:slateManifest,model}]};
}
if(process.argv[1]?.endsWith('/assemble-nfl-slate.mjs')){
 try{
  const [poolPath,csvPath]=process.argv.slice(2),pool=JSON.parse(await fs.readFile(poolPath,'utf8'));
  const published=await fetchPublishedWeekly();
  const r=await fetch('https://dfsroto.win/projections',{redirect:'error',signal:AbortSignal.timeout(25000)});if(!r.ok)throw Error('Original DST provider is unavailable.');
  const defenses=parseDefenses(await r.text());
  const bundle=await assembleNFL(pool,await fs.readFile(csvPath,'utf8'),{...published,defenses});
  const result=await refreshBundle(bundle);console.log(JSON.stringify({state:'published',...result,week:published.weekly.week,scoring:'RR-DK-core'}));
 }catch(error){console.error(JSON.stringify({state:/weekly forecasts and current defense source do not match/.test(error.message)?'waiting':'blocked',reason:error.message}));process.exitCode=1;}
}
