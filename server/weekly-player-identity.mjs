import {fail} from './domain.mjs';
const fields=['Pass_Att','Pass_Yds','Pass_TD','INT','Rush_Att','Rush_Yds','Rush_TD','Targets','Receptions','Rec_Yds','Rec_TD','Standard','Half_PPR','PPR'];
// A published zero-point "not projected starter" record is an explicit exclusion,
// not an alternative forecast. Preserve the raw release and omit only those
// documented placeholders when another single forecast exists for that player.
export function weeklyPlayers(weekly){
 const groups=new Map();for(const p of weekly.players||[]){const list=groups.get(p.Player)||[];list.push(p);groups.set(p.Player,list);}
 const players=[],excluded=[];
 for(const rows of groups.values()){
  if(rows.length===1){players.push(rows[0]);continue;}
  const placeholders=rows.filter(p=>/^Not projected starter(?: Week \d+)?$/i.test(p.note||'')&&fields.every(k=>p[k]===0));
  const forecasts=rows.filter(p=>!placeholders.includes(p));
  if(forecasts.length!==1||!placeholders.length)fail(503,'Ambiguous weekly player identities require validation.');
  players.push(forecasts[0]);excluded.push(...placeholders.map(p=>({name:p.Player,team:p.Team,reason:p.note})));
 }
 return {players,excluded};
}
