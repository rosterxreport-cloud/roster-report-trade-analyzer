import crypto from 'node:crypto';
import {scoreNFLProjection,scoreNFLDefense} from './nfl-scoring.mjs';
const incumbent='c95ac28e53c2c9550827391269dcaff95127ee8397730b33072bc81d00441d6d';
const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
const fields=['Pass_Att','Pass_Yds','Pass_TD','INT','Rush_Att','Rush_Yds','Rush_TD','Targets','Receptions','Rec_Yds','Rec_TD'];
const time=x=>{if(typeof x!=='string'||!/(Z|[+-]\d{2}:\d{2})$/.test(x)||!Number.isFinite(Date.parse(x)))throw Error('Source timestamp needs an explicit timezone.');return Date.parse(x);};
// Scoring/identity adapter only. Weekly means are copied, never refit or rescaled.
export function adaptWeeklyNFL(weekly,manifest,evidence,now=Date.now()){
 if(manifest.model_sha256!==incumbent||!manifest.model_base?.startsWith('Established structural v4 model'))throw Error('NFL source is not the established weekly RR model.');
 const expectedSource='data/projections/'+weekly.season+'_week'+weekly.week+'_league_v4_full.csv';
 if(weekly.source!==expectedSource||weekly.week!==manifest.forecast_week||weekly.updatedAt!==manifest.as_of||evidence.forecastWeek!==weekly.week||evidence.season!==weekly.season)throw Error('Weekly forecast, manifest and slate evidence do not match.');
 const captured=time(weekly.updatedAt),expires=time(evidence.validUntil);
 if(captured>now||expires<=now||time(evidence.capturedAt)>now||expires<=captured)throw Error('NFL forecast or evidence is not current for this slate.');
 if(evidence.weeklySourceHash!==hash(weekly)||evidence.modelHash!==incumbent||evidence.publishApproved!==true||!evidence.source)throw Error('DraftKings supplements must reference the exact established weekly output.');
 const original=new Map();
 for(const p of weekly.players||[]){
  const key=p.Player+'|'+p.Team;
  if(original.has(key)||fields.some(k=>!Number.isFinite(p[k])))throw Error('Invalid weekly player source.');
  original.set(key,p);
 }
 const players=[],seen=new Set();
 for(const e of evidence.players||[]){
  const p=original.get(e.name+'|'+e.team);
  if(!p||p.Position!==e.position||p.Opponent!==e.opponent||!e.gameId||!e.id||seen.has(String(e.id)))throw Error('Explicit NFL identity does not match the weekly source.');
  if(time(e.startsAt)<=now||expires>time(e.startsAt))throw Error('NFL source cannot remain valid after game lock.');
  seen.add(String(e.id));
  const statline=Object.fromEntries(fields.map(k=>[k,p[k]]));
  const scored=scoreNFLProjection({...e.events,...statline,Position:p.Position});
  players.push({id:String(e.id),name:p.Player,team:p.Team,opponent:p.Opponent,gameId:e.gameId,startsAt:e.startsAt,projection:scored.projection,statline,fantasyPoints:{Standard:p.Standard,Half_PPR:p.Half_PPR,PPR:p.PPR},scoringComponents:scored.components});
 }
 // DST comes only from supplied existing RR event forecasts; there is no fallback model.
 for(const d of evidence.defenses||[]){
  if(!d.id||seen.has(String(d.id))||!d.name||!d.team||!d.opponent||!d.gameId||time(d.startsAt)<=now||expires>time(d.startsAt)||d.establishedSource!==true||!d.sourceHash)throw Error('Verified existing RR defense inputs are required.');
  seen.add(String(d.id));const scored=scoreNFLDefense({...d.events,Position:'DST'});
  players.push({id:String(d.id),name:d.name,team:d.team,opponent:d.opponent,gameId:d.gameId,startsAt:d.startsAt,projection:scored.projection,scoringComponents:scored.components});
 }
 if(!players.length)throw Error('No matched weekly projections were supplied.');
 return {schemaVersion:1,kind:'projections',sport:'NFL',scoring:'DraftKings',publishApproved:true,capturedAt:weekly.updatedAt,validUntil:evidence.validUntil,provenance:{modelHash:incumbent,sourceHash:hash(weekly),weeklySource:weekly.source,weeklyManifestHash:hash(manifest),supplementHash:hash(evidence),scoringSource:evidence.source,model:'RR established weekly structural v4',modelUnchanged:true},players};
}
