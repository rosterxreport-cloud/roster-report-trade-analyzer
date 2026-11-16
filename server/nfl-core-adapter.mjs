import crypto from 'node:crypto';
export const NFL_CORE_HASH='2354d0e5af4a56784d0418bd392d3cde1942c4f50834be18a06ee9c2502e85b9';
export const CORE_NOTE='RR weekly offense projections with the DraftKings interception adjustment. Yardage bonuses, lost fumbles and other unmodeled events are omitted. Defense projections are separately sourced from dfsroto. These are core scoring estimates, not complete expected DraftKings scores.';
const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
export function adaptNFLCore({weekly,manifest,defenses,coreHash,generatorHash,finalSnapshotReceipt},now=Date.now()){
 if(coreHash!==NFL_CORE_HASH||generatorHash!==manifest.model_sha256||!/^[a-f0-9]{64}$/.test(generatorHash)||!manifest.model_base?.startsWith('Established structural v4 model'))throw Error('Verified established weekly NFL source code is required.');
 if(weekly.week!==manifest.forecast_week||weekly.week!==defenses.week||weekly.season!==defenses.season||weekly.source!=='data/projections/'+weekly.season+'_week'+weekly.week+'_league_v4_full.csv')throw Error('NFL weekly forecasts and current defense source do not match.');
 if(!finalSnapshotReceipt?.verifiedStatlines||!/^[a-f0-9]{40}$/.test(finalSnapshotReceipt.commit||'')||!finalSnapshotReceipt.sourceCsvHash||!finalSnapshotReceipt.sourceJsonHash)throw Error('Final published weekly JSON/CSV agreement is required.');
 const captured=Date.parse(weekly.updatedAt),defenseCaptured=Date.parse(defenses.capturedAt),expires=Date.parse(defenses.validUntil);
 if(!Number.isFinite(captured)||captured>now||now-captured>7*86400000||!Number.isFinite(defenseCaptured)||defenseCaptured>now||now-defenseCaptured>90*60000||!Number.isFinite(expires)||expires<=now||defenses.source!=='https://dfsroto.win/projections'||!defenses.sourceHash)throw Error('Current NFL source provenance is required.');
 const players=[],seen=new Set();
 for(const p of weekly.players||[]){
  const id=p.Player+'|'+p.Team;
  if(seen.has(id)||!['QB','RB','WR','TE'].includes(p.Position)||!Number.isFinite(p.PPR)||!Number.isFinite(p.INT)||p.PPR<0||p.INT<0)throw Error('Invalid established weekly offense row.');
  seen.add(id);
  players.push({id,name:p.Player,team:p.Team,opponent:p.Opponent,position:p.Position,projection:p.PPR+p.INT,statline:{...p},fantasyPoints:{Standard:p.Standard,Half_PPR:p.Half_PPR,PPR:p.PPR},source:'Roster Report established weekly model'});
 }
 for(const p of defenses.players||[]){
  if(!p.team||!p.opponent||!Number.isFinite(p.projection)||p.projection<0||seen.has('DST|'+p.team))throw Error('Invalid separately sourced defense forecast.');
  seen.add('DST|'+p.team);players.push({id:'DST|'+p.team,name:p.name,team:p.team,opponent:p.opponent,position:'DST',projection:p.projection,source:'dfsroto DST'});
 }
 if(!players.length)throw Error('Missing NFL forecasts.');
 return {schemaVersion:1,kind:'projections',sport:'NFL',scoring:'RR-DK-core',publishApproved:true,capturedAt:weekly.updatedAt,validUntil:defenses.validUntil,provenance:{modelHash:generatorHash,sourceHash:hash(weekly),weeklySource:weekly.source,weeklyManifestHash:hash(manifest),finalSnapshotReceipt,baselineManifestCapturedAt:manifest.as_of,coreModelHash:coreHash,verifiedGeneratorHash:generatorHash,modelFamily:'established_weekly_structural_v4',modelUnchanged:true,model:'RR established weekly structural v4',scoringMethod:'weekly-ppr-plus-interceptions',scoringNote:CORE_NOTE,defenseSource:defenses.source,defenseSourceHash:defenses.sourceHash,defenseCapturedAt:defenses.capturedAt},players};
}
