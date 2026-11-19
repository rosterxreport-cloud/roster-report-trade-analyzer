import fs from 'node:fs';import path from 'node:path';
export function stageResearchPreview(out,{environment,sample}){
 const target=path.join(out,'platform/research-sample.json');
 if(environment!=='preview'){fs.rmSync(target,{force:true});return '';}
 if(sample.schemaVersion!==1||sample.researchOnly!==true||sample.publishApproved!==false||sample.draws!==10000||sample.scoring!=='DraftKings'||!Array.isArray(sample.players)||sample.players.length!==3||!Number.isFinite(Date.parse(sample.capturedAt)))throw Error('Research preview must contain exactly three dated, explicitly unapproved examples.');
 const fields=['id','name','team','opponent','minutes','projection','availability','mean','median','p10','p90','p95','histogram','probabilityAtLeast','statline'];
 const data={schemaVersion:1,researchOnly:true,publishApproved:false,draws:10000,scoring:'DraftKings',capturedAt:sample.capturedAt,players:sample.players.map(p=>{
  if(!p.name||p.name.length>100||!Array.isArray(p.histogram)||p.histogram.length>30||p.histogram.reduce((s,b)=>s+b.count,0)!==10000||p.histogram.some(b=>!Number.isInteger(b.count)||b.count<0||!Number.isFinite(b.from)||!Number.isFinite(b.to)||b.to<=b.from)||['mean','median','p10','p90','p95','projection','minutes'].some(k=>!Number.isFinite(p[k]))||p.p10>p.median||p.median>p.p90)throw Error('Invalid research sample distribution.');
  const result=Object.fromEntries(fields.map(k=>[k,p[k]]));
  result.statline=Object.fromEntries(['MIN','PTS','REB','AST','STL','BLK','TOV','FGA','FG3A','FTA','FGM','FG3M','FTM'].filter(k=>Number.isFinite(p.statline?.[k])).map(k=>[k,p.statline[k]]));
  result.histogram=p.histogram.map(({count,from,to})=>({count,from,to}));
  result.probabilityAtLeast=Object.fromEntries(Object.entries(p.probabilityAtLeast||{}).filter(([key,value])=>/^\d+$/.test(key)&&Number.isFinite(value)&&value>=0&&value<=1));
  return result;
 })};
 fs.mkdirSync(path.dirname(target),{recursive:true});fs.writeFileSync(target,JSON.stringify(data));
 return '<section class="pro-panel research-review" id="researchSample"><p class="eyebrow">DATED RESEARCH PREVIEW</p><h2>Inside the Roster Report model</h2><p class="fine">Three experimental examples from the November 15 research candidate. These estimates await release validation and availability checks.</p><label>Explore a sample player<select id="researchPlayer"><option>Loading model examples…</option></select></label><div id="researchData" aria-live="polite"></div><p class="fine">This limited preview is separate from the full Pro analysis. Simulated outcomes describe model possibilities; they are not observed results or contest recommendations.</p></section>';
}
