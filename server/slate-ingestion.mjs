import crypto from 'node:crypto';
import {fail} from './domain.mjs';
const hash=x=>crypto.createHash('sha256').update(x).digest('hex');
const positions={NBA:new Set(['PG','SG','SF','PF','C']),NFL:new Set(['QB','RB','WR','TE','DST'])};
const normalize=s=>String(s).normalize('NFKC').trim().replace(/\s+/g,' ').toLowerCase();
const time=value=>{if(typeof value!=='string'||!/(Z|[+-]\d{2}:\d{2})$/.test(value)||!Number.isFinite(Date.parse(value)))fail(400,'Every evidence timestamp needs an explicit timezone.');return Date.parse(value);};
export function parseCsv(text){
 const rows=[];let row=[],cell='',quoted=false;
 text=String(text).replace(/^\uFEFF/,'');
 for(let i=0;i<text.length;i++){const c=text[i];if(c==='"'){if(quoted&&text[i+1]==='"'){cell+='"';i++;}else if(!cell||quoted)quoted=!quoted;else fail(400,'Malformed CSV quoting.');}else if(!quoted&&(c===','||c==='\n')){row.push(cell.replace(/\r$/,''));cell='';if(c==='\n'){if(row.some(x=>x!==''))rows.push(row);row=[];}}else cell+=c;}
 if(quoted)fail(400,'Unclosed CSV quote.');if(cell||row.length){row.push(cell.replace(/\r$/,''));rows.push(row);}if(rows.length<2)fail(400,'Salary CSV contains no player rows.');
 const [headers,...data]=rows;if(new Set(headers).size!==headers.length)fail(400,'Duplicate salary CSV headers.');
 for(const h of ['ID','Name','Position','Salary','TeamAbbrev'])if(!headers.includes(h))fail(400,'Missing salary CSV column: '+h);
 return data.map(values=>{if(values.length!==headers.length)fail(400,'Salary CSV row width mismatch.');return Object.fromEntries(headers.map((h,i)=>[h,values[i]]));});
}
export function buildSlate({salaryCsv,manifest,model,joint=null,decisionAt}){
 const now=time(decisionAt),sport=manifest.sport;
 if(!positions[sport]||manifest.schemaVersion!==1||!/^[-a-zA-Z0-9_]{1,80}$/.test(manifest.slateId||'')||manifest.format!=='DraftKings Classic')fail(400,'Unsupported slate manifest.');
 if(model.sport!==sport||model.kind!=='projections'||model.scoring!=='DraftKings'||!model.provenance?.modelHash||!Array.isArray(model.players))fail(400,'A matching RR DraftKings projection artifact is required.');
 for(const key of ['salaryCapturedAt','injuryCapturedAt','scheduleCapturedAt'])if(time(manifest[key])>now)fail(400,'Evidence captured after the decision cannot enter this build.');
 if(time(model.capturedAt)>now)fail(400,'Projection snapshot was created after the decision.');
 for(const key of ['salarySource','injurySource','scheduleSource'])if(!manifest[key])fail(400,'Missing '+key);
 if(!Array.isArray(manifest.gameIds)||new Set(manifest.gameIds).size<2||!Array.isArray(manifest.playerMappings))fail(400,'Slate games and explicit player mappings are required.');
 const models=new Map(model.players.map(p=>[String(p.id),p]));if(models.size!==model.players.length)fail(400,'Duplicate model IDs.');
 const mappings=new Map(manifest.playerMappings.map(p=>[String(p.dkId),p]));if(mappings.size!==manifest.playerMappings.length)fail(400,'Duplicate DraftKings mappings.');
 const rows=parseCsv(salaryCsv),ids=new Set(),players=[],issues=[];
 for(const row of rows){
  const id=row.ID;if(!/^\d+$/.test(id)||ids.has(id))fail(400,'Salary IDs must be unique DraftKings player IDs.');ids.add(id);
  const salary=Number(row.Salary),pos=row.Position.split('/');if(!Number.isInteger(salary)||salary<100||salary>50000||!pos.length||pos.some(x=>!positions[sport].has(x)))fail(400,'Invalid salary or position for '+id);
  const map=mappings.get(id);if(!map){issues.push({id,reason:'missing identity / injury mapping'});continue;}
  if(!['active','out','questionable','doubtful','inactive'].includes(map.status))fail(400,'Unrecognized availability for '+id);
  const verified=time(map.verifiedAt),start=time(map.startsAt);if(verified>now||start<=now||!manifest.gameIds.includes(map.gameId)||map.team!==row.TeamAbbrev)fail(400,'Player evidence does not match the selected pre-lock slate: '+id);
  if(now-verified>90*60000)issues.push({id,reason:'stale player availability'});
  if(map.status!=='active')continue;
  const projected=models.get(String(map.modelId));if(!projected){issues.push({id,reason:'active player lacks an RR projection'});continue;}
  if(projected.team!==map.team||projected.gameId!==map.gameId||normalize(projected.name)!==normalize(row.Name)||!Number.isFinite(projected.projection)||projected.projection<0||!map.opponent||projected.opponent!==map.opponent)fail(400,'Explicit identity does not match the RR player, team and game: '+id);
  const player={id,name:row.Name,team:map.team,opponent:map.opponent,gameId:map.gameId,startsAt:map.startsAt,verifiedAt:map.verifiedAt,status:map.status,salary,positions:pos,projection:projected.projection,modelId:String(map.modelId)};
  if(map.ownership!=null){if(!Number.isFinite(map.ownership)||map.ownership<0||map.ownership>1||!manifest.ownershipSource||time(manifest.ownershipCapturedAt)>now)fail(400,'Ownership requires a dated reliable source.');player.ownership=map.ownership;}
  players.push(player);
 }
 for(const id of mappings.keys())if(!ids.has(id))issues.push({id,reason:'mapping is outside the salary pool'});
 if(manifest.completeSalaryPool!==true)issues.push({reason:'complete official salary pool has not been verified'});
 if(new Set(players.map(p=>p.gameId)).size<2)issues.push({reason:'fewer than two playable games'});
 let simulations;
 if(joint){
  if(joint.sport!==sport||joint.draws!==10000||joint.scoring!=='DraftKings'||joint.joint!==true||joint.modelHash!==model.provenance.modelHash||joint.provenance?.sourceHash!==model.provenance.sourceHash||joint.capturedAt!==model.capturedAt)fail(400,'Joint simulation is not from the same projection snapshot.');
  const scores={};for(const p of players){const series=joint.scores?.[p.modelId];if(!Array.isArray(series)||series.length!==10000||!series.every(Number.isFinite))fail(400,'Incomplete joint draws for '+p.name);scores[p.id]=series;}
  simulations={draws:10000,joint:true,scoring:'DraftKings',modelHash:joint.modelHash,scores};
 }
 const approved=model.publishApproved===true&&manifest.publishApproved===true&&(!joint||joint.publishApproved===true)&&!issues.length;
 const validUntil=new Date(Math.min(...(!players.length?[now]:[]),...players.map(p=>Date.parse(p.startsAt)),...players.map(p=>Date.parse(p.verifiedAt)+90*60000))).toISOString();
 const provenance={...model.provenance,salarySource:manifest.salarySource,injurySource:manifest.injurySource,eligibilitySource:manifest.salarySource,scheduleSource:manifest.scheduleSource,salaryHash:hash(salaryCsv),manifestHash:hash(JSON.stringify(manifest)),sourceHash:hash(JSON.stringify({projection:model.provenance.sourceHash,salary:hash(salaryCsv),manifest:hash(JSON.stringify(manifest))})),...(manifest.ownershipSource?{ownershipSource:manifest.ownershipSource}:{}),decisionAt};
 return {artifact:{schemaVersion:1,kind:'slate',sport,slateId:manifest.slateId,format:'DraftKings Classic',salaryCap:50000,publishApproved:approved,capturedAt:decisionAt,validUntil,provenance,players,...(simulations?{simulations}:{})},report:{slateId:manifest.slateId,salaryRows:rows.length,matchedActivePlayers:players.length,excludedAvailability:rows.length-players.length,releaseApproved:approved,advancedSimulationAvailable:!!simulations,issues}};
}
