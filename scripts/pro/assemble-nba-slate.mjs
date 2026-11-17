/** Join established forecasts to current official salary and injury evidence; no projection calculation. */
import fs from 'node:fs/promises';
import {refreshBundle} from './refresh-dfs.mjs';
const normalize=s=>String(s).normalize('NFKC').toLowerCase().replace(/[.\u2019']/g,'').replace(/\s+/g,' ').trim();
const aliases=new Map(Object.entries({'Alexandre Sarr':'Alex Sarr','Jimmy Butler':'Jimmy Butler III','Robert Williams':'Robert Williams III','Gregory Jackson':'GG Jackson'}).map(([a,b])=>[normalize(a),normalize(b)]));
const canonical=s=>aliases.get(normalize(s))||normalize(s);
export function assembleNBA({pool,salaryCsv,basic,joint,availability},now=Date.now()){
 if(pool.sport!=='NBA'||pool.salaryDataApproved!==true||!pool.validation?.allCsvRowsMatched||!pool.validation?.fullApiPlayerCoverage)throw Error('Complete verified NBA salaries are required.');
 if(!availability.source||!availability.sha256||!Number.isFinite(Date.parse(availability.reportAsOf))||Date.parse(availability.reportAsOf)>now||now-Date.parse(availability.reportAsOf)>90*60000||Date.parse(availability.capturedAt)>now)throw Error('Current official availability evidence is required.');
 const source=new Map(basic.players.map(p=>[canonical(p.name)+'|'+p.team,p]));
 if(source.size!==basic.players.length)throw Error('Ambiguous established forecast identities.');
 const salaryNames=new Map();
 for(const p of pool.players)salaryNames.set(canonical(p.name)+'|'+p.team,p);
 const teams={};
 for(const [team,report] of Object.entries(availability.teams)){
  const statuses=new Map();let verified=report.submitted===true;
  for(const row of report.players){
   const key=canonical(row.name)+'|'+team;
   if(!salaryNames.has(key))verified=false;
   if(statuses.has(key))throw Error('Duplicate official availability identity.');
   statuses.set(key,row.status);
  }
  teams[team]={verified,statuses};
 }
 const availabilitySummary={unverifiedTeams:[...new Set(pool.players.map(p=>p.team))].filter(t=>!teams[t]?.verified)};
 const adapted=new Map(basic.players.map(p=>[p.id,{...p}]));
 const mappings=[],joins=[];
 for(const player of pool.players){
  const key=canonical(player.name)+'|'+player.team,projected=source.get(key),team=teams[player.team];
  let status='unverified';
  if(team?.verified){
   const designation=team.statuses.get(key);
   status=({Out:'out',Questionable:'questionable',Doubtful:'doubtful',Probable:'probable',Available:'active'})[designation]||(designation?'unverified':'active');
  }
  const operator=String(player.sourceStatus||'').toLowerCase();
  if(player.sourceDisabled)status='inactive';
  else if(['o','out','ir','inactive','suspended'].includes(operator))status='out';
  else if(['q','questionable'].includes(operator)&&status==='active')status='questionable';
  else if(['d','doubtful'].includes(operator)&&status==='active')status='doubtful';
  else if(operator&&!['none','available','active','healthy','probable','p'].includes(operator)&&status==='active')status='unverified';
  if(projected){
   if(projected.opponent!==player.opponent||Date.parse(projected.startsAt)!==Date.parse(player.startsAt))throw Error('Established player forecast does not match the official scheduled game: '+player.name);
   const a=adapted.get(projected.id);a.sourceName=projected.name;a.name=player.name;a.sourceGameId=projected.gameId;a.gameId=player.gameId;
   joins.push({dkId:player.id,modelId:projected.id,sourceName:projected.name,salaryName:player.name,sourceGameId:projected.gameId,gameId:player.gameId});
  }
  mappings.push({dkId:player.id,modelId:projected?.id??'unmodeled:'+player.id,team:player.team,opponent:player.opponent,gameId:player.gameId,startsAt:player.startsAt,status,verifiedAt:availability.capturedAt,...(!projected?{projectionExclusion:{reason:'not-projected-by-established-model',sourceHash:basic.provenance.sourceHash}}:{})});
 }
 const model={...basic,players:[...adapted.values()]};
 const manifest={schemaVersion:1,sport:'NBA',slateId:'dk-'+pool.draftGroupId,format:'DraftKings Classic',name:'NBA DraftKings Classic · '+pool.games.length+' games',completeSalaryPool:true,publishApproved:true,excludeUnmodeled:true,gameIds:pool.games.map(g=>g.id),playerMappings:mappings,identityJoins:joins,salarySource:pool.sourceRecords.salaryCsv.url,salaryCapturedAt:pool.sourceRecords.salaryCsv.capturedAt,scheduleSource:pool.sourceRecords.draftables.url,scheduleCapturedAt:pool.sourceRecords.draftables.capturedAt,injurySource:availability.source,injuryCapturedAt:availability.capturedAt,injuryReportHash:availability.sha256,injuryReportAsOf:availability.reportAsOf,availabilitySummary};
 return {sports:['NBA'],slates:[{salaryCsv,manifest,model,joint}],nba:{basic,distributions:null}};
}
if(process.argv[1]?.endsWith('/assemble-nba-slate.mjs')){
 try{
  const [poolPath,csvPath,basicPath,jointPath,availabilityPath,distributionsPath]=process.argv.slice(2);
  const values=await Promise.all([poolPath,basicPath,jointPath,availabilityPath,distributionsPath].map(async p=>JSON.parse(await fs.readFile(p,'utf8'))));
  const [pool,basic,joint,availability,distributions]=values;
  const bundle=assembleNBA({pool,basic,joint,availability,salaryCsv:await fs.readFile(csvPath,'utf8')});bundle.nba.distributions=distributions;
  const result=await refreshBundle(bundle);
  console.log(JSON.stringify({state:'published',...result,salaryPlayers:pool.players.length,identityJoins:bundle.slates[0].manifest.identityJoins.length}));
 }catch(error){console.error(JSON.stringify({state:'blocked',reason:error.message,...(error.validation?{validation:error.validation}:{})}));process.exitCode=1;}
}
