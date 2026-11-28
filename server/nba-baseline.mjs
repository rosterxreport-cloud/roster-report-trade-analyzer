import {fail} from './domain.mjs';
const fields=['MIN','PTS','REB','AST','STL','BLK','TOV','FGA','FG3A','FTA','FGM','FG3M','FTM'];
export function existingModelPreview(a,environment){
 if(environment!=='preview')fail(503,'Approved NBA projections are not available yet.');
 if(a?.schemaVersion!==1||a.purpose!=='existing-model-preview'||a.modelUnchanged!==true||!a.model||!Number.isFinite(Date.parse(a.capturedAt))||!/^[a-f0-9]{64}$/.test(a.sourceHash||'')||!Array.isArray(a.players)||!a.players.length)fail(503,'Existing-model snapshot is invalid.');
 const seen=new Set();
 const players=a.players.map(p=>{
  if(!/^\d+$/.test(p.id)||seen.has(p.id)||!p.name||!p.team||!p.opponent||!Number.isFinite(p.minutes)||!Number.isFinite(p.projection)||fields.some(k=>!Number.isFinite(p.statline?.[k])))fail(503,'Existing-model player data is invalid.');
  if(p.fantasyPoints&&['DraftKings','Yahoo','ESPN'].some(k=>!Number.isFinite(p.fantasyPoints[k])))fail(503,'Invalid fantasy scoring values.');
  seen.add(p.id);return {id:p.id,name:p.name,team:p.team,opponent:p.opponent,minutes:p.minutes,projection:p.projection,fantasyPoints:p.fantasyPoints?Object.fromEntries(['DraftKings','Yahoo','ESPN'].map(k=>[k,p.fantasyPoints[k]])):{DraftKings:p.projection},statline:Object.fromEntries(fields.map(k=>[k,p.statline[k]])),availability:'Unverified'};
 });
 return {capturedAt:a.capturedAt,model:a.model,previewOnly:true,label:'Dated Roster Report projections. Availability is unverified; this snapshot is not an eligible DFS slate.',players};
}
