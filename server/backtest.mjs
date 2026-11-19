import crypto from 'node:crypto';
import {fail} from './domain.mjs';
import {optimize} from './optimizer.mjs';
const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
export function backtestSlate({slate,decisionAt,actuals,options={},contest=null}){
 const decision=Date.parse(decisionAt);
 if(!Number.isFinite(decision)||!/(Z|[+-]\d{2}:\d{2})$/.test(decisionAt)||Date.parse(slate.capturedAt)>decision)fail(400,'Backtest requires a frozen pre-decision snapshot.');
 if(!slate.provenance?.salaryHash||!slate.provenance?.manifestHash)fail(400,'Backtest requires hashed salary and availability evidence.');
 if(actuals.slateId!==slate.slateId||actuals.sport!==slate.sport||actuals.scoring!=='DraftKings'||!Number.isFinite(Date.parse(actuals.capturedAt))||!/(Z|[+-]\d{2}:\d{2})$/.test(actuals.capturedAt||'')||actuals.complete!==true||!actuals.source||!Array.isArray(actuals.players)||Date.parse(actuals.capturedAt)<=Math.max(...slate.players.map(p=>Date.parse(p.startsAt))))fail(400,'Complete, dated final DraftKings results are required.');
 const actualById=new Map(actuals.players.map(p=>[String(p.id),p]));if(actualById.size!==actuals.players.length)fail(400,'Duplicate actual-result IDs.');
 for(const p of slate.players){const a=actualById.get(p.id);if(!a||a.gameId!==p.gameId||!Number.isFinite(a.points)||!['final','DNP'].includes(a.status)||(a.status==='DNP'&&a.points!==0))fail(400,'Missing or invalid final result for '+p.name);}
 // Only frozen model/slate evidence enters optimize; actuals are used afterward.
 const result=optimize(slate,options,decision);
 const errors=slate.players.map(p=>p.projection-actualById.get(p.id).points);
 let benchmark=null;
 if(contest){
  if(contest.verified!==true||contest.slateId!==slate.slateId||contest.sport!==slate.sport||!contest.source||!Number.isFinite(contest.lastPaidScore)||!Number.isFinite(contest.winningScore)||contest.winningScore<contest.lastPaidScore)fail(400,'Contest benchmark is unverified or does not match the slate.');
  benchmark={source:contest.source,lastPaidScore:contest.lastPaidScore,winningScore:contest.winningScore};
 }
 const lineups=result.lineups.map((l,i)=>{const score=l.players.reduce((sum,p)=>sum+actualById.get(p.id).points,0);return {lineup:i+1,salary:l.salary,projected:l.projected,actual:score,projectionError:l.projected-score,players:l.players.map(p=>({id:p.id,name:p.name,slot:p.slot,actual:actualById.get(p.id).points})),...(benchmark?{marginToReportedPaidLine:score-benchmark.lastPaidScore,marginToWinningScore:score-benchmark.winningScore}:{})};});
 return {sport:slate.sport,slateId:slate.slateId,decisionAt,algorithm:result.algorithm,modelHash:slate.provenance.modelHash,slateHash:hash(slate),actualsHash:hash(actuals),actualSource:actuals.source,projectionAudit:{n:errors.length,mae:errors.reduce((s,e)=>s+Math.abs(e),0)/errors.length,bias:errors.reduce((s,e)=>s+e,0)/errors.length},lineups,benchmark,verifiedCashRate:null,verifiedROI:null,limitations:['Retrospective replay; no proof of actual contest entry.','Reported score cutoffs do not establish payouts or returns.','Validation does not eliminate model selection bias; use frozen prospective tests.']};
}
