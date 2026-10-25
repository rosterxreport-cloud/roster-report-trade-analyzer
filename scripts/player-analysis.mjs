/** Editorial rules interpret published model outputs; they never change the model. */
export function fantasyTier(position,rank){
 if(position==='QB')return rank<=3?'elite QB1':rank<=12?'QB1':rank<=24?'QB2':'quarterback depth';
 if(position==='TE')return rank<=3?'elite TE1':rank<=12?'TE1':rank<=24?'TE2':'tight-end depth';
 if(position==='RB')return rank<=6?'elite RB1':rank<=12?'RB1':rank<=24?'RB2':rank<=36?'FLEX option':'bench stash';
 return rank<=6?'elite WR1':rank<=12?'WR1':rank<=24?'WR2':rank<=36?'WR3/FLEX option':'bench stash';
}
function tierAction(position,rank){
 if(position==='QB')return rank<=12?'Start him as a QB1':rank<=24?'Use him in two-QB or Superflex lineups':'Keep him on the bench in standard one-QB leagues';
 if(position==='TE')return rank<=12?'Start him as a TE1':rank<=18?'Use him as a streaming option':'Keep him on the bench in standard one-TE leagues';
 return rank<=12?`Start him as ${position==='RB'?'an':'a'} ${position}1`:rank<=24?`Start him as ${position==='RB'?'an':'a'} ${position}2`:rank<=36?'Use him in the FLEX':'Keep him out of standard starting lineups';
}
function poolEfficiency(position,weekly){
 const rows=weekly.filter(w=>!w.statsMissing);if(rows.length<3)return null;
 const stat=position==='QB'?['passing_yards','attempts',50]:position==='RB'?['rushing_yards','carries',30]:['receiving_yards','targets',20];
 const attempts=rows.reduce((s,w)=>s+w[stat[1]],0),yards=rows.reduce((s,w)=>s+w[stat[0]],0);
 return attempts>=stat[2]?{rate:yards/attempts,denominator:attempts}:null;
}
export function editorialContext(p,{evidence,adjusted,projection,manifest}){
 const measured=poolEfficiency(p.position,p.weekly);
 const cohort=Object.values(evidence.players).filter(e=>e.position===p.position).map(e=>poolEfficiency(p.position,e.weekly)).filter(Boolean);
 const efficiency=measured?{...measured,rank:1+cohort.filter(e=>e.rate>measured.rate).length,count:cohort.length}:null;
 const forecastRank=p.projection?1+projection.players.filter(q=>q.Position===p.position&&q.PPR>p.projection.PPR).length:null;
 const peers=adjusted.half.filter(q=>q.pos===p.position&&q.name!==p.name).sort((a,b)=>Math.abs(a.value-p.rankings.half.value)-Math.abs(b.value-p.rankings.half.value)||a.name.localeCompare(b.name)).slice(0,2).map(q=>({name:q.name,value:q.value,posRank:q.posRank}));
 const out=manifest?.forecast_week===projection.week&&manifest.as_of===projection.updatedAt?manifest.verified_out_overrides?.[p.id]||null:null;
 return {efficiency,forecastRank,peers,out};
}
export function analysis(p){
 const number=(n,d=1)=>Number(n).toFixed(d),out=[];
 const add=(heading,text,evidenceRefs)=>out.push({heading,text,evidenceRefs});
 const rows=p.weekly.filter(w=>!w.statsMissing),n=rows.length,r=p.rankings.half,pos=p.position,ctx=p.editorial||{};
 const sum=(list,k)=>list.reduce((s,w)=>s+w[k],0),t=Object.fromEntries(['attempts','completions','passing_yards','passing_tds','passing_interceptions','rushing_yards','rushing_tds','carries','targets','receptions','receiving_yards','receiving_tds','fantasy_points_ppr'].map(k=>[k,sum(rows,k)]));
 const tier=fantasyTier(pos,r.posRank),overall=r.rank===999?'His overall rank is currently unassigned.':`He is No. ${r.rank} overall in Half PPR.`;
 let lead=`${p.name} is ${/^(elite|RB)/.test(tier)?'an':'a'} ${tier} asset for rest-of-season trades. ${overall}`;
 if(n){
  if(pos==='QB')lead+=` In ${n} recorded game${n===1?'':'s'} through Week ${p.throughWeek}, he has thrown for ${number(t.passing_yards,0)} yards and ${t.passing_tds} touchdowns against ${t.passing_interceptions} interceptions, adding ${number(t.rushing_yards,0)} rushing yards and ${t.rushing_tds} rushing touchdown${t.rushing_tds===1?'':'s'}.`;
  else if(pos==='RB')lead+=` Through Week ${p.throughWeek}, his ${n}-game sample includes ${t.carries} carries for ${number(t.rushing_yards,0)} yards and ${t.rushing_tds} rushing touchdowns, plus ${t.receptions} catches for ${number(t.receiving_yards,0)} yards.`;
  else lead+=` In ${n} recorded game${n===1?'':'s'} through Week ${p.throughWeek}, he has turned ${t.targets} target${t.targets===1?'':'s'} into ${t.receptions} catches, ${number(t.receiving_yards,0)} yards and ${t.receiving_tds} touchdowns.`;
  lead+=` That is ${number(t.fantasy_points_ppr/n)} PPR points per game.`;
 }else lead+=` There is no verified offensive counting-stat sample through Week ${p.throughWeek}. Price him from the published rankings and availability evidence. An upgrade needs a verified role, not assumed current-season production.`;
 add('Fantasy verdict',lead,['rankings.half','weekly']);
 let usage='';
 if(n){
  const window=n>=4?Math.min(3,Math.floor(n/2)):Math.min(3,n),recent=rows.slice(-window),prior=n>=4?rows.slice(-window*2,-window):[];
  const metric=pos==='QB'?'attempts':pos==='RB'?'carries':'targets',label={attempts:'pass attempts',carries:'carries',targets:'targets'}[metric];
  const current=sum(recent,metric)/window,old=prior.length?sum(prior,metric)/prior.length:null;
  usage=`His latest ${window} appearance${window===1?'':'s'} produced ${number(current)} ${label} per game`;
  if(old!==null){usage+=`, versus ${number(old)} in the preceding ${prior.length}.`;const relative=old?current/old-1:current>0?1:0;
   if(relative>=.2&&current-old>=(pos==='QB'?3:1))usage+=' Opportunity is expanding.';
   else if(relative<=-.2&&old-current>=(pos==='QB'?3:1))usage+=' Opportunity is contracting; lower the volume expectation.';
   else usage+=' The workload is holding near its recent baseline.';
  }else usage+='.';
  if(['WR','TE'].includes(pos)){const denominator=rows.reduce((s,w)=>s+(w.teamPassAttempts||0),0);if(denominator>0)usage+=` His targets equal ${number(t.targets/denominator*100)}% of team pass attempts in those games.`;}
  if(pos==='RB')usage+=t.receptions?` His ${number(t.receptions/n)} catches per game add reception-based scoring alongside the rushing workload.`:' He has added no reception points in this sample.';
  if(pos==='QB')usage+=` Rushing has supplied ${number((t.rushing_yards*.1+t.rushing_tds*6)/n)} fantasy points per game before turnovers.`;
  const snaps=p.weekly.filter(w=>w.snapShare!=null).slice(-3);
  if(snaps.length){const share=snaps.reduce((s,w)=>s+w.snapShare,0)/snaps.length;usage+=` Across ${snaps.length} recent snap records, he averaged ${number(share*100)}% of offensive snaps.`;}
  if(pos==='RB'&&(t.receptions||t.receiving_yards))usage+=` Catches and receiving yards alone contributed ${number((t.receptions+t.receiving_yards*.1)/n)} PPR points per game before receiving touchdowns.`;
  else if(pos==='QB'&&t.attempts)usage+=` He completed ${number(t.completions/t.attempts*100)}% of passes; interceptions cost ${number(t.passing_interceptions*2/n)} points per game under the run's scoring.`;
  else if(t.fantasy_points_ppr>0){const tdShare=(t.rushing_tds+t.receiving_tds)*6/t.fantasy_points_ppr;if(tdShare>=0&&tdShare<=1)usage+=` Touchdowns supplied ${number(tdShare*100)}% of his PPR points; ${tdShare>=.4?'his scoring pace needs continued touchdown production.':'yardage and catches carry most of his production.'}`;}
  const efficiency=ctx.efficiency,metricLabel=pos==='QB'?'yards per pass attempt':pos==='RB'?'yards per carry':'yards per target';
  if(efficiency){
   const qualifier=pos==='QB'?'50 pass attempts':pos==='RB'?'30 carries':'20 targets';
   usage+=` His ${number(efficiency.rate)} ${metricLabel} rank ${efficiency.rank} of ${efficiency.count} qualifying ${pos}s in our pool (three games and ${qualifier}).`;
   const percentile=(efficiency.count-efficiency.rank)/Math.max(1,efficiency.count-1);
   usage+=percentile>=.75?' Strong efficiency backs up the workload.':percentile<=.25?' Low efficiency leaves him more dependent on volume and touchdowns.':' Volume remains the stronger distinction than efficiency.';
  }else{
   const denom=pos==='QB'?t.attempts:pos==='RB'?t.carries:t.targets,yards=pos==='QB'?t.passing_yards:pos==='RB'?t.rushing_yards:t.receiving_yards;
   if(denom>0)usage+=` He has ${number(yards/denom)} ${metricLabel}, but the sample is below our comparison minimum. Do not price that rate as a proven efficiency edge.`;
   else usage+=' The sample does not support an efficiency comparison.';
  }
 }else{
  const adjustment=r.injuryAdjustment;
  if(adjustment?.status)usage+=`The availability snapshot lists ${adjustment.status.toLowerCase()}. ${adjustment.expectedReturn==='Unconfirmed'?'His return date is unconfirmed. ':''}`;
  if(p.calculation?.seasonWeight===0&&!p.calculation.hasLiveSignal)usage+='The current calculation puts no weight on a new-season production signal; his price rests on prior and context inputs. ';
  usage+='There is no measured carry, target or passing-volume trend to support a role upgrade. Treat him as a speculative roster asset until participation and workload are documented. ';
  usage+=`His PPR positional rank is ${pos}${p.rankings.ppr.posRank}, compared with ${pos}${p.rankings.standard.posRank} in Standard; match that format before valuing him.`;
 }
 if(n>0&&t.attempts+t.carries+t.targets===0)usage+=' No carries, targets or pass attempts means this sample provides no demonstrated path to weekly counting stats.';
 if(n>0&&n<3)usage+=` Only ${n} recorded game${n===1?'':'s'} support${n===1?'s':''} this sample. Require more participation before calling a role change or an efficiency breakout.`;
 if(n>0&&r.injuryAdjustment?.status)usage+=` The availability snapshot lists ${r.injuryAdjustment.status.toLowerCase()}; check the documented return status before using him.`;
 if(!n&&r.preInjuryValue!=null)usage+=` The availability adjustment takes his Half-PPR value from ${number(r.preInjuryValue)} to ${number(r.value)}, a ${number(r.preInjuryValue-r.value)}-point reduction that directly limits his current trade price.`;
 add('Role and efficiency',usage,['weekly','editorial.efficiency','rankings','calculation']);
 const proj=p.projection;let outlook='';
 if(ctx.out)outlook=`Keep him out of Week ${p.projectionWeek} lineups. The verified override in this run lists ${ctx.out.replace(/^.*?[—–]\s*/,'').replace(/[. ]+$/,'')}. His rest-of-season trade tier remains ${tier}; the weekly absence does not erase that longer-term ranking.`;
 else if(proj){
  const note=[proj.starterNote,proj.note].filter(Boolean).filter(s=>s!=='No current injury report designation').join(' ').replace(/ at user request/g,'').replace(/[. ]+$/,'');
  const conditional=/conditional|assum|questionable|limited participation|doubtful|if active|expected/i.test(note);
  outlook=`Week ${p.projectionWeek}: ${tierAction(pos,ctx.forecastRank||999)}${conditional?' if active under the stated role assumption':''}. His ${number(proj.PPR)}-point PPR forecast ranks ${pos}${ctx.forecastRank||'—'} in this run`;
  outlook+=pos==='QB'?`, with ${number(proj.Pass_Att)} pass attempts, ${number(proj.Pass_Yds)} passing yards and ${number(proj.Rush_Yds)} rushing yards.`:pos==='RB'?`, built on ${number(proj.Rush_Att)} carries, ${number(proj.Rush_Yds)} rushing yards and ${number(proj.Targets)} targets.`:`, built on ${number(proj.Targets)} targets, ${number(proj.Receptions)} catches and ${number(proj.Rec_Yds)} receiving yards.`;
  outlook+=` The matchup is against ${proj.Opponent}.`;
  if(n){const gap=proj.PPR-t.fantasy_points_ppr/n;outlook+=` This forecast is ${number(Math.abs(gap))} points ${gap>=0?'above':'below'} his observed PPR average.`;}
  if(note)outlook+=` Run availability: ${note}.`;
 }else{
  outlook=`There is no Week ${p.projectionWeek} projection for ${p.name} in this run. Keep his weekly lineup decision separate from his ${tier} rest-of-season trade tier. Missing forecast coverage is not a zero-point prediction or confirmation that he is out.`;
 }
 add('Weekly lineup call',outlook,['projection','editorial.forecastRank','editorial.out','rankings.half']);
 let trade=`Half-PPR trade value: ${number(r.value)}. `;
 if(ctx.peers?.length)trade+=`Same-position model prices: ${ctx.peers.map(q=>`${q.name} (${pos}${q.posRank}, value ${number(q.value)})`).join(' and ')}. `;
 const elite=r.posRank<=(['QB','TE'].includes(pos)?3:6),starter=r.posRank<=(['QB','TE'].includes(pos)?12:24);
 trade+=elite?'Demand a premium return; reject depth-only packages for this top-tier asset.':starter?'Use that tier as the negotiation anchor; trade him to address a clear starting-lineup need.':'Price him as a secondary asset in rest-of-season deals; do not upgrade his trade tier on a single weekly forecast.';
 trade+=` PPR value is ${number(p.rankings.ppr.value)}; Standard is ${number(p.rankings.standard.value)}.`;
 if(p.change){const delta=p.change.previousRank-r.rank;if(delta)trade+=` Since the last model update, he ${delta>0?'rose':'fell'} ${Math.abs(delta)} overall spot${Math.abs(delta)===1?'':'s'} (${p.change.previousRank} to ${r.rank}).`;else trade+=` His overall rank held at ${r.rank}.`;
  if(p.change.scoreDelta!==null&&p.change.scoreDelta!==undefined&&Math.abs(p.change.scoreDelta)>=.05)trade+=` His own ranking score changed ${p.change.scoreDelta>0?'+':''}${number(p.change.scoreDelta,2)}.`;
 }
 if(p.calculationChange){const c=p.calculationChange;if(Math.abs(c.liveSignal-c.previousLiveSignal)>=.05)trade+=` Recorded current-season signal: ${number(c.previousLiveSignal,2)} to ${number(c.liveSignal,2)}.`;if(Math.abs(c.roleMultiplier-c.previousRoleMultiplier)>=.005)trade+=` Recorded role multiplier: ${number(c.previousRoleMultiplier,2)} to ${number(c.roleMultiplier,2)}.`;}
 add('Trade stance',trade,['rankings','editorial.peers','change','calculationChange']);
 // Keep shared methodology/caveats in source notes, not in every player's analysis.
 if(out.reduce((s,p)=>s+p.text.split(/\s+/).length,0)>300){
  out[1].text=out[1].text.replace(/ \(three games and [^)]+\)/,'').replace(' The workload is holding near its recent baseline.',' Workload is stable.').replace(' Volume remains the stronger distinction than efficiency.','Volume drives this profile.');
 }
 return out;
}
