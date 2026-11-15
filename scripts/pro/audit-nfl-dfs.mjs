import fs from 'node:fs';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
export function auditNFL(data){
 const rows=data.players||[],issues=[],teams=new Map(),identities=new Map();
 const stats=['Pass_Att','Pass_Yds','Pass_TD','INT','Rush_Att','Rush_Yds','Rush_TD','Targets','Receptions','Rec_Yds','Rec_TD'];
 let scoringFailures=0;
 for(const row of rows){
  if(stats.some(key=>!Number.isFinite(row[key])||row[key]<0)){issues.push({type:'invalid-statline',player:row.Player});continue;}
  const standard=.04*row.Pass_Yds+4*row.Pass_TD-2*row.INT+.1*(row.Rush_Yds+row.Rec_Yds)+6*(row.Rush_TD+row.Rec_TD);
  for(const [key,weight] of [['Standard',0],['Half_PPR',.5],['PPR',1]])if(!Number.isFinite(row[key])||Math.abs(row[key]-standard-weight*row.Receptions)>.11)scoringFailures++;
  if(row.Receptions>row.Targets+.01)issues.push({type:'catches-exceed-targets',player:row.Player});
  const team=teams.get(row.Team)||{passAttempts:0,targets:0};team.passAttempts+=row.Pass_Att;team.targets+=row.Targets;teams.set(row.Team,team);
  const names=identities.get(row.Player)||[];names.push(row.Team);identities.set(row.Player,names);
  if(/\bOUT\b|injured reserve|\bIR\b/i.test(row.note||'')&&row.PPR>0)issues.push({type:'positive-forecast-with-out-note',player:row.Player,team:row.Team,note:row.note});
 }
 for(const [team,total] of teams)if(total.targets>total.passAttempts+.2)issues.push({type:'targets-exceed-pass-attempts',team,passAttempts:+total.passAttempts.toFixed(2),targets:+total.targets.toFixed(2)});
 for(const [player,teams] of identities)if(teams.length>1)issues.push({type:'ambiguous-player-identity',player,teams});
 const required={lostFumbles:'Fumbles_Lost',passing300Probability:'Pass_300_Probability',rushing100Probability:'Rush_100_Probability',receiving100Probability:'Rec_100_Probability',twoPointConversions:'Two_Point_Conversions',returnTouchdowns:'Return_TD',offensiveRecoveryTouchdowns:'Offensive_Fumble_Recovery_TD'};
 const applies=(row,key)=>key==='Pass_300_Probability'?row.Pass_Att>0:key==='Rush_100_Probability'?row.Rush_Att>0:key==='Rec_100_Probability'?row.Targets>0:row.Pass_Att+row.Rush_Att+row.Targets>0;
 const missingDKInputs=Object.fromEntries(Object.entries(required).map(([name,key])=>[name,rows.filter(r=>r.Position!=='DST'&&applies(r,key)&&!Number.isFinite(r[key])).length]));
 const dst=rows.filter(r=>r.Position==='DST').length;
 const blockers=[...(issues.length?['Published statline integrity / identity / availability issues need review.']:[]),...(scoringFailures?['Published baseline scoring reconciliation failed.']:[]),...(Object.values(missingDKInputs).some(Boolean)?['Required DraftKings scoring inputs are not modeled in this feed.']:[]),...(!dst?['No Roster Report defense/special-teams projections are available.']:[]),'Complete official salaries, eligibility and pre-lock active status are not provided by this projection feed.','A release-approved correlated NFL simulation artifact is not supplied.'];
 return {publishApproved:false,season:data.season,week:data.week,updatedAt:data.updatedAt,players:rows.length,positions:Object.fromEntries([...new Set(rows.map(r=>r.Position))].map(p=>[p,rows.filter(r=>r.Position===p).length])),baselineScoringFailures:scoringFailures,missingDKInputs,dstProjections:dst,issues,blockers,limitations:['Read-only validation of the published RR model feed; no values or football assumptions were changed.','Rounding tolerance is 0.11 points across the rounded source statistics.','DraftKings uses -1 per interception plus nonlinear yardage bonuses and other events; generic PPR cannot stand in for DK scoring.','Missing inputs are not assigned zero and point projections are not converted into unsupported bonus probabilities.']};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 const [input,output]=process.argv.slice(2);if(!input||!output)throw Error('Usage: node scripts/pro/audit-nfl-dfs.mjs INPUT_JSON OUTPUT_JSON');
 const bytes=fs.readFileSync(input),result={...auditNFL(JSON.parse(bytes)),sourceHash:crypto.createHash('sha256').update(bytes).digest('hex')};fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result,null,2));
}
