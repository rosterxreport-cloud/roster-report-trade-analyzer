import {fail} from './domain.mjs';
// Max-weight starting lineup via exhaustive assignment over the small set of
// positions, with memoization by roster bitmask. Values remain the existing RR
// ROS trade index; a trade index is never represented as ROS fantasy points.
export function startingImpact(roster,slots,score){
 const available=roster.filter(p=>Number.isFinite(p[score]));
 if(available.length>24||slots.length>12)fail(400,'Roster or starting-slot limit exceeded.');
 const eligible=(p,s)=>p.pos===s||(s==='FLEX'&&['RB','WR','TE'].includes(p.pos))||(s==='SF'&&['QB','RB','WR','TE'].includes(p.pos));
 const cache=new Map();
 function solve(i,mask){if(i===slots.length)return {total:0,players:[]};const key=i+':'+mask;if(cache.has(key))return cache.get(key);let best=solve(i+1,mask);for(let j=0;j<available.length;j++)if(!(mask&(1<<j))&&eligible(available[j],slots[i])){const next=solve(i+1,mask|(1<<j)),total=available[j][score]+next.total;if(total>best.total)best={total,players:[{...available[j],slot:slots[i]},...next.players]};}cache.set(key,best);return best;}
 return solve(0,0);
}
export function tradeAnalysis({roster,give,receive,format='half',slots=['QB','RB','RB','WR','WR','TE','FLEX']},rankings,projections){
 if(!['half','ppr','standard'].includes(format)||![roster,give,receive,slots].every(Array.isArray)||slots.some(x=>!['QB','RB','WR','TE','FLEX','SF'].includes(x))||!give.length||!receive.length||give.length>8||receive.length>8||roster.length>24||new Set(roster).size!==roster.length||new Set(give).size!==give.length||new Set(receive).size!==receive.length||give.some(x=>!roster.includes(x))||receive.some(x=>roster.includes(x)))fail(400,'Provide a valid roster and distinct outgoing and incoming players.');
 const pointKey={half:'Half_PPR',ppr:'PPR',standard:'Standard'}[format];
 const byName=new Map(rankings[format].map(p=>{const matches=projections.players.filter(q=>q.Player===p.name);const sameTeam=matches.filter(q=>q.Team===p.team);const weekly=matches.length===1?matches[0]:sameTeam.length===1?sameTeam[0]:null;return [p.name,{...p,weekly:weekly?.[pointKey]}];}));
 if([...roster,...receive].some(x=>!byName.has(x)))fail(400,'Player is absent from the published rankings.');
 const before=roster.map(x=>byName.get(x)),after=[...before.filter(p=>!give.includes(p.name)),...receive.map(x=>byName.get(x))];
 const score=a=>a.reduce((s,p)=>s+p.value,0);
 const positions=a=>Object.fromEntries(['QB','RB','WR','TE'].map(pos=>[pos,score(a.filter(p=>p.pos===pos))]));
 const a=startingImpact(before,slots,'weekly'),b=startingImpact(after,slots,'weekly');
 const missing=[...new Set([...before,...after].filter(p=>!Number.isFinite(p.weekly)).map(p=>p.name))];
 return {format,rosValueIndex:{outgoing:score(give.map(x=>byName.get(x))),incoming:score(receive.map(x=>byName.get(x))),label:'Existing RR rest-of-season trade-value index, not projected fantasy points'},positionalStrength:{before:positions(before),after:positions(after)},weekly:{before:a,after:b,delta:missing.length?null:b.total-a.total,season:projections.season,week:projections.week,updatedAt:projections.updatedAt,missing},confidence:{calibrated:false,label:'No calibrated trade confidence interval is available. Weekly impact uses the current published week only; injuries, lineup slots and missing forecasts can change it.'}};
}
