import {fail,validateArtifact} from './domain.mjs';
export const SLOTS={NBA:['PG','SG','SF','PF','C','G','F','UTIL'],NFL:['QB','RB','RB','WR','WR','WR','TE','FLEX','DST']};
const eligible=(p,s)=>p.positions.some(x=>x===s||(s==='G'&&['PG','SG'].includes(x))||(s==='F'&&['SF','PF'].includes(x))||(s==='UTIL'&&['PG','SG','SF','PF','C'].includes(x))||(s==='FLEX'&&['RB','WR','TE'].includes(x)));
const quantile=(a,q)=>{const b=[...a].sort((x,y)=>x-y);return b[Math.floor((b.length-1)*q)];};
export function validateSlate(artifact,now=Date.now()){
 const a=validateArtifact(artifact,{kind:'slate',sport:artifact?.sport,now});
 if(!SLOTS[a.sport]||a.format!=='DraftKings Classic'||a.salaryCap!==50000||!a.slateId||a.players.length>600)fail(503,'Unsupported or incomplete DraftKings slate.');
 if(!a.provenance.salarySource||!a.provenance.injurySource||!a.provenance.eligibilitySource)fail(503,'Salary, injury or eligibility evidence is missing.');
 const ids=new Set();
 for(const p of a.players){
  if(!/^\d+$/.test(p.id)||ids.has(p.id)||!p.name||!p.team||!p.opponent||!p.gameId||!Number.isInteger(p.salary)||p.salary<100||p.salary>50000||!Array.isArray(p.positions)||!p.positions.length||!Number.isFinite(p.projection)||p.projection<0||!Number.isFinite(Date.parse(p.startsAt))||!Number.isFinite(Date.parse(p.verifiedAt))||Date.parse(p.verifiedAt)>now||now-Date.parse(p.verifiedAt)>90*60000)fail(503,'Slate contains invalid or stale player evidence.');
  if(p.ownership!=null&&(!Number.isFinite(p.ownership)||p.ownership<0||p.ownership>1||!a.provenance.ownershipSource))fail(503,'Ownership lacks reliable provenance.');
  ids.add(p.id);
 }
 return a;
}
export function validateLineup(players,sport,{cap=50000,locks=[],excludes=[],stack=0,bringBack=false}={}){
 if(players.length!==SLOTS[sport].length||new Set(players.map(p=>p.id)).size!==players.length||players.reduce((s,p)=>s+p.salary,0)>cap||players.some((p,i)=>!eligible(p,SLOTS[sport][i]))||locks.some(id=>!players.some(p=>p.id===id))||players.some(p=>excludes.includes(p.id))||new Set(players.map(p=>p.gameId)).size<2)return false;
 if(sport==='NFL'){
  const qb=players[0];if(players.filter(p=>p.team===qb.team&&p.positions.some(x=>['WR','TE'].includes(x))).length<stack)return false;
  if(bringBack&&!players.some(p=>p.team===qb.opponent&&p.positions.some(x=>['RB','WR','TE'].includes(x))))return false;
 }
 return true;
}
function matrixValid(slate){
 const m=slate.simulations;
 if(!m||m.draws!==10000||!m.modelHash||m.modelHash!==slate.provenance.modelHash||!m.joint||m.scoring!=='DraftKings')return false;
 return slate.players.every(p=>Array.isArray(m.scores?.[p.id])&&m.scores[p.id].length===10000&&m.scores[p.id].every(Number.isFinite));
}
// Bounded beam search: returns validated feasible candidates, never claims a
// mathematical optimum. Joint draw indexes preserve recovered model correlations.
export function optimize(artifact,options={},now=Date.now()){
 const slate=validateSlate(artifact,now),sport=slate.sport;
 const {advanced=false,count=1,locks=[],excludes=[],maxExposure=1,stack=0,bringBack=false}=options;
 if(!Number.isInteger(count)||count<1||count>20||!Array.isArray(locks)||!Array.isArray(excludes)||new Set(locks).size!==locks.length||new Set(excludes).size!==excludes.length||locks.some(x=>excludes.includes(x))||locks.length>SLOTS[sport].length||!Number.isFinite(maxExposure)||maxExposure<=0||maxExposure>1||!Number.isInteger(stack)||stack<0||stack>3)fail(400,'Invalid lineup controls.');
 if(!advanced&&(count!==1||locks.length||excludes.length||maxExposure!==1||stack||bringBack))fail(403,'Advanced controls require Roster Report Pro.');
 if(advanced&&!matrixValid(slate))fail(503,'A release-approved 10,000-draw joint simulation is required for advanced optimization.');
 const pool=slate.players.filter(p=>p.status==='active'&&Date.parse(p.startsAt)>now&&!excludes.includes(p.id));
 if([...locks,...excludes].some(id=>!slate.players.some(p=>p.id===id))||locks.some(id=>!pool.some(p=>p.id===id)))fail(400,'A lock or exclusion is not eligible for this active slate.');
 const exposureMax=Math.floor(count*maxExposure+1e-8);
 if(exposureMax<1||(locks.length&&exposureMax<count))fail(400,'Exposure cap conflicts with the requested lineup count or locks.');
 const used=new Map(),seen=new Set(),lineups=[];
 const samples=advanced?slate.simulations.scores:null;
 const cap=50000;
 for(let n=0;n<count;n++){
  const available=pool.filter(p=>(used.get(p.id)||0)<exposureMax);
  const candidates=new Map();
  const attempts=advanced?12:1;
  for(let attempt=0;attempt<attempts;attempt++){
   const weight=p=>!advanced?p.projection:(.30*p.projection+.70*samples[p.id][(attempt*787+n*1237)%5000]);
   const weights=new Map(available.map(p=>[p.id,weight(p)]));
   let beam=[{players:[],ids:new Set(),salary:0,score:0}];
   for(const slot of SLOTS[sport]){
    const choices=available.filter(p=>eligible(p,slot)).sort((a,b)=>weights.get(b.id)-weights.get(a.id));
    const next=[],unique=new Set();
    for(const b of beam)for(const p of choices){
     if(b.ids.has(p.id)||b.salary+p.salary>cap)continue;
     const ids=new Set([...b.ids,p.id]),left=SLOTS[sport].length-ids.size;
     if(locks.filter(x=>!ids.has(x)).length>left)continue;
     const key=[...ids].sort().join(',');if(unique.has(key))continue;unique.add(key);
     next.push({players:[...b.players,p],ids,salary:b.salary+p.salary,score:b.score+weights.get(p.id)});
    }
    next.sort((a,b)=>b.score-a.score);beam=next.slice(0,300);
    if(!beam.length)break;
   }
   for(const b of beam){
    const key=[...b.ids].sort().join(',');
    if(seen.has(key)||!validateLineup(b.players,sport,{locks,excludes,stack,bringBack}))continue;
    candidates.set(key,b);
   }
  }
  let best;
  // Evaluate held-out joint draws, separate from the candidate-search draws.
  for(const [key,candidate] of candidates){
   let score=candidate.score,summary;
   if(advanced){
    const scores=Array.from({length:1000},(_,i)=>candidate.players.reduce((s,p)=>s+samples[p.id][5000+i*5],0));
    summary={mean:scores.reduce((a,b)=>a+b,0)/scores.length,p10:quantile(scores,.1),median:quantile(scores,.5),p90:quantile(scores,.9),p95:quantile(scores,.95),basis:'1,000 held-out draws from joint model; simulated, not historical'};
    const hasOwnership=candidate.players.every(p=>p.ownership!=null);
    const leverage=hasOwnership?Math.min(5,-candidate.players.reduce((s,p)=>s+Math.log(Math.max(.01,p.ownership)),0)*.2):0;
    score=.2*summary.mean+.8*summary.p95+leverage;
   }
   if(!best||score>best.score)best={...candidate,key,score,summary};
  }
  if(!best)fail(422,'No feasible portfolio was found within the search budget. Relax locks, stacking or exposure limits.');
  seen.add(best.key);best.players.forEach(p=>used.set(p.id,(used.get(p.id)||0)+1));
  lineups.push({players:best.players.map((p,i)=>({slot:SLOTS[sport][i],id:p.id,name:p.name,team:p.team,salary:p.salary,projection:p.projection,ownership:p.ownership??null})),salary:best.salary,projected:best.players.reduce((s,p)=>s+p.projection,0),simulation:best.summary||null});
 }
 return {sport,slateId:slate.slateId,mode:advanced?'Tournament upside':'Basic projection',algorithm:'Bounded beam search; feasible solutions, global optimality not guaranteed',lineups,exposures:Object.fromEntries([...used].map(([id,num])=>[id,num/count])),csv:[SLOTS[sport].join(','),...lineups.map(l=>l.players.map(p=>p.id).join(','))].join('\r\n'),exportFormat:'DraftKings Classic player-ID columns; import using the matching slate template',provenance:slate.provenance};
}
