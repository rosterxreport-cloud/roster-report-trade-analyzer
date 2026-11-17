import {fail} from './domain.mjs';
export function nflDetails(weekly,{player=null}={}){
 if(!weekly?.players?.length)fail(503,'Published weekly forecasts are unavailable.');
 const seen=new Set();for(const p of weekly.players){if(seen.has(p.Player))fail(503,'Weekly player identities require validation.');seen.add(p.Player);}
 const field=['Pass_Att','Pass_Yds','Pass_TD','INT','Rush_Att','Rush_Yds','Rush_TD','Targets','Receptions','Rec_Yds','Rec_TD','Standard','Half_PPR','PPR'];
 const teamTotals=new Map();
 for(const p of weekly.players){const t=teamTotals.get(p.Team)||{targets:0,carries:0};if(p.Position!=='QB')t.targets+=p.Targets||0;t.carries+=p.Rush_Att||0;teamTotals.set(p.Team,t);}
 const ranks=new Map();for(const pos of ['QB','RB','WR','TE'])weekly.players.filter(p=>p.Position===pos).sort((a,b)=>b.PPR-a.PPR||a.Player.localeCompare(b.Player)).forEach((p,i)=>ranks.set(p.Player,i+1));
 const players=weekly.players.filter(p=>!player||p.Player===player).map(p=>{
  const t=teamTotals.get(p.Team);return {name:p.Player,team:p.Team,opponent:p.Opponent,position:p.Position,positionRank:ranks.get(p.Player),statline:Object.fromEntries(field.map(k=>[k,p[k]])),workload:{targets:p.Targets,carries:p.Rush_Att,passAttempts:p.Pass_Att,teamTargetAllocation:t.targets?p.Targets/t.targets:null,teamCarryAllocation:t.carries?p.Rush_Att/t.carries:null},efficiency:{yardsPerCarry:p.Rush_Att?p.Rush_Yds/p.Rush_Att:null,yardsPerCatch:p.Receptions?p.Rec_Yds/p.Receptions:null,catchRate:p.Targets?p.Receptions/p.Targets:null},scoring:{passingYards:.04*p.Pass_Yds,passingTouchdowns:4*p.Pass_TD,interceptions:-2*p.INT,rushingYards:.1*p.Rush_Yds,rushingTouchdowns:6*p.Rush_TD,receivingYards:.1*p.Rec_Yds,receivingTouchdowns:6*p.Rec_TD,receptions:p.Receptions},availabilityNote:p.note||'Final game-day availability remains subject to updates.',starterNote:p.starterNote||null,snapStatus:p.snapStatus||null};
 });
 if(player&&!players.length)fail(404,'This player has no published forecast for this week.');
 return {season:weekly.season,week:weekly.week,throughWeek:weekly.throughWeek,capturedAt:weekly.updatedAt,source:weekly.source,players,method:'All values use the published RR weekly model. Allocation percentages describe projected team workload, not observed usage. Efficiency ratios are derived from the published statline. Scoring components use full PPR and four-point passing touchdowns; rounding may differ.',limitations:'No calibrated injury probabilities, simulation ranges or rest-of-season weekly forecasts are supplied.'};
}
