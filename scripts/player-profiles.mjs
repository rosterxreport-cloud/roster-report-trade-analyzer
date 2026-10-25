import {relatedArticles} from './related-articles.mjs';
import {renderMatchup} from './player-matchups.mjs';
/** Evidence-only profile generation. No model fitting, network calls or invented commentary. */
import fs from 'node:fs';
import {analysis,editorialContext} from './player-analysis.mjs';
export {analysis} from './player-analysis.mjs';
import {teamLogo,imageCss,imageClient} from './player-images.mjs';
import path from 'node:path';
import crypto from 'node:crypto';
import vm from 'node:vm';
export const hash=s=>crypto.createHash('sha256').update(s).digest('hex');
export const key=s=>String(s||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/\b(jr|sr|ii|iii|iv)\.?\b/g,'').replace(/[^a-z0-9]/g,'');
const core=new Set(['QB','RB','WR','TE']);
const number=(n,d=1)=>Number(n).toFixed(d);
const formats={half:'Half PPR',ppr:'PPR',standard:'Standard'};
export async function adjustedPlayers(root){
 const read=p=>fs.readFileSync(path.join(root,p),'utf8');
 const c={console,Response,document:{getElementById:()=>null},localStorage:{},fetch:async p=>new Response(read(p))};c.window=c;vm.createContext(c);
 for(const f of ['scoring-settings.js','injury-layer.js'])vm.runInContext(read(f),c);
 vm.runInContext(read('app.js').replace(/init\(\)\.catch\([\s\S]*$/,''),c);
 const db=await(await c.fetch('players.json')).json();
 return Object.fromEntries(Object.entries(db).map(([f,rows])=>[f,c.applyRbPremium(rows)]));
}
const countWords=s=>s.trim().split(/\s+/).length;
export async function makeRelease(root,options={}){
 const read=p=>fs.readFileSync(path.join(root,p),'utf8'),load=p=>JSON.parse(read(p));
 const raw=load('players.json'),ev=load(options.evidencePath||'data/player-evidence.json'),projection=load('data/weekly-projections.json');
 if(ev.schemaVersion!==1||!ev.sources?.length||ev.throughWeek<1)throw Error('Invalid evidence snapshot');
 const injuries=load('injury-adjustments.json');
 const manifestPath=projection.source.replace('_league_v4_full.csv','_run_manifest.json');
 const manifest=fs.existsSync(path.join(root,manifestPath))?load(manifestPath):null;
 if(ev.throughWeek<Number(projection.throughWeek))throw Error('Statistics are behind the published projection inputs');
 if(options.requireFresh&&Date.now()-Date.parse(ev.capturedAt)>7*86400000)throw Error('Statistical snapshot is older than seven days');
 const adjusted=await adjustedPlayers(root);
 const previous=fs.existsSync(path.join(root,'data/player-profiles.json'))?load('data/player-profiles.json'):null;
 const auditPath=options.auditPath||'data/ranking-evidence.json';
 const audit=fs.existsSync(path.join(root,auditPath))?load(auditPath):null;
 const auditMatches=audit&&JSON.stringify(audit.published)===JSON.stringify(raw);
 const registry=fs.existsSync(path.join(root,'data/player-registry.json'))?load('data/player-registry.json'):{};
 const byName=new Map();for(const e of Object.values(ev.players)){if(byName.has(key(e.name)))throw Error('Ambiguous player identity');byName.set(key(e.name),e);}
 const selected=raw.half.filter(p=>core.has(p.pos)).sort((a,b)=>a.rank-b.rank).slice(0,250);
 if(selected.length!==250)throw Error('Expected 250 selected players');
 const selectedNames=new Set(selected.map(p=>key(p.name)));
 // Retain existing URLs after a player exits the selected set, including if removed from the model.
 const names=[...selected,...Object.values(registry).filter(p=>!selectedNames.has(key(p.name))).map(p=>raw.half.find(r=>key(r.name)===key(p.name))||p)];
 const profiles=[];
 for(const source of names){
  const e=byName.get(key(source.name));const old=previous?.profiles.find(p=>p.id===(e?.id||source.id));
  if(!e){if(old){profiles.push({...old,active:false,retained:true});continue;}throw Error('Missing identity '+source.name);}
  let entry=registry[e.id];if(!entry)entry=registry[e.id]={id:e.id,name:source.name,slug:source.name.normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/['’]/g,'').replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'')};
  if(Object.values(registry).some(r=>r.id!==e.id&&r.slug===entry.slug))throw Error('Duplicate permanent slug');
  const rankings=Object.fromEntries(Object.keys(formats).map(f=>[f,adjusted[f].find(p=>key(p.name)===key(source.name))]));
  if(Object.values(rankings).some(v=>!v)){if(old){profiles.push({...old,active:false,retained:true});continue;}throw Error('Missing scoring format');}
  const matches=projection.players.filter(p=>key(p.Player)===key(source.name));if(matches.length>1)throw Error('Ambiguous projection');
  const p={id:e.id,name:source.name,slug:entry.slug,team:source.team,position:e.position,active:selectedNames.has(key(source.name)),throughWeek:ev.throughWeek,season:ev.season,statisticsAsOf:ev.capturedAt,rankingsAsOf:auditMatches?audit.capturedAt:null,projectionAsOf:projection.updatedAt,projectionWeek:projection.week,projectionStatus:projection.status,projectionUpdateNote:projection.updateNote,projection:matches[0]||null,weekly:e.weekly,rankings,sources:ev.sources,calculation:auditMatches?audit.formats.half.calculations?.[source.name]||null:null};
  if(old&&old.rankings.half.rank!==999&&source.rank!==999&&previous.inputHashes.players!==hash(read('players.json')))p.change={previousRank:old.rankings.half.rank,scoreDelta:source.rankingScore!=null&&old.rankings.half.rankingScore!=null?Number((source.rankingScore-old.rankings.half.rankingScore).toFixed(2)):null};
  else if(old?.change)p.change=old.change;
  if(auditMatches&&p.calculation){
   const prior=audit.previousCalculations?.half?.[source.name];
   if(prior)p.calculationChange={previousLiveSignal:prior.liveSignal,liveSignal:p.calculation.liveSignal,previousRoleMultiplier:prior.roleMultiplier,roleMultiplier:p.calculation.roleMultiplier};
  }
  p.editorial=editorialContext(p,{evidence:ev,adjusted,projection,manifest});
  p.paragraphs=analysis(p);p.wordCount=countWords(p.paragraphs.map(x=>x.text).join(' '));
  if(p.wordCount>340||p.wordCount<180)throw Error('Profile length outside safety range: '+p.name+' '+p.wordCount);
  profiles.push(p);
 }
 const texts=new Set(profiles.map(p=>p.paragraphs.map(x=>x.text).join(' ')));if(texts.size!==profiles.length)throw Error('Duplicate analysis');
 return {registry,release:{schemaVersion:1,editorialVersion:2,selection:'Published Half-PPR QB/RB/WR/TE top 250',statisticsAsOf:ev.capturedAt,throughWeek:ev.throughWeek,inputHashes:{players:hash(read('players.json')),injuries:hash(read('injury-adjustments.json')),projections:hash(read('data/weekly-projections.json')),evidence:hash(read(options.evidencePath||'data/player-evidence.json')),app:hash(read('app.js')),injuryLayer:hash(read('injury-layer.js'))},profiles}};
}
export function weeklyStatProjection(p,esc,dateLabel){
 const heading=`<h2>Week ${esc(p.projectionWeek)} stat projections</h2>`;
 if(p.editorial?.out)return `${heading}<p class="projection-notice">Ruled out for this week. No playable weekly projection is shown.</p>`;
 const q=p.projection;
 if(!q)return `${heading}<p>No published projection for this player in this weekly run. This is not a zero-point forecast or an inactive designation.</p>`;
 const passing=[['Pass_Att','Pass attempts'],['Pass_Yds','Passing yards'],['Pass_TD','Passing TDs'],['INT','Interceptions']];
 const rushing=[['Rush_Att','Carries'],['Rush_Yds','Rushing yards'],['Rush_TD','Rushing TDs']];
 const receiving=[['Targets','Targets'],['Receptions','Receptions'],['Rec_Yds','Receiving yards'],['Rec_TD','Receiving TDs']];
 const fields=[...(p.position==='QB'?passing:[]),...rushing,...(p.position==='QB'?[]:receiving),['Standard','Standard points'],['Half_PPR','Half-PPR points'],['PPR','PPR points']];
 const stats=fields.map(([key,label])=>`<div><dt>${label}</dt><dd>${typeof q[key]==='number'&&Number.isFinite(q[key])?number(q[key]):'Unavailable'}</dd></div>`).join('');
 const notes=[q.starterNote,q.note].filter(Boolean).map(n=>esc(String(n).replace(/at user request/gi,'under the published workload assumption'))).join(' · ');
 return `${heading}<p>${esc(q.Opponent?'Opponent: '+q.Opponent:'Opponent unavailable')} · ${esc(p.projectionStatus)} · Updated ${dateLabel(p.projectionAsOf)}</p><dl class="player-summary weekly-stat-projections">${stats}</dl><p class="data-meta">Published model estimates, rounded to one decimal. Fantasy points use the published default scoring, including 4-point passing TDs.</p>${notes?`<p class="projection-notice">${notes}</p>`:''}`;
}
export function renderProfiles({release,page,esc,write,dateLabel,stale=false,matchupEvidence=null,articles=[]}){
 const active=release.profiles.filter(p=>p.active);
 if(active.length!==250)throw Error('Release does not contain 250 active profiles');
 write('player-images.js',imageClient);
 write('player-profiles.css',imageCss+` .player-summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin:24px 0}.player-summary div{border:1px solid #46556a;border-radius:10px;padding:12px}.player-summary dt{font-size:.85rem;color:#b8c7d9}.player-summary dd{margin:6px 0 0;font-weight:700}.player-directory{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;padding:0;list-style:none}.player-directory a{display:block;padding:14px;border:1px solid #46556a;border-radius:8px}.player-directory small{display:block;color:#b8c7d9}.player-analysis p{line-height:1.8;overflow-wrap:anywhere}.player-analysis details{margin:20px 0}.profile-search{padding:12px;font:inherit;width:100%;max-width:460px;margin:12px 0}.player-directory [hidden]{display:none}.player-analysis summary{cursor:pointer}.player-analysis code{overflow-wrap:anywhere}.player-analysis :focus-visible,.profile-search:focus-visible{outline:3px solid #f9d84a;outline-offset:4px}`);
 write('player-directory.js',`const search=document.getElementById('playerSearch');search?.addEventListener('input',()=>{const q=search.value.trim().toLowerCase();let n=0;document.querySelectorAll('.player-directory li').forEach(li=>{li.hidden=!li.textContent.toLowerCase().includes(q);if(!li.hidden)n++});document.getElementById('playerCount').textContent=n+' matching players';});`);
 const assets='<link rel="stylesheet" href="/player-profiles.css"><script defer src="/player-images.js"></script>';
 page('players','Fantasy Football Player Trade Values and Outlooks','Explore 250 player profiles with verified NFL production, usage, fantasy rankings, trade values and weekly projections from The Roster Report.',`${assets}${stale?'<p class="projection-notice">Profiles retain the last successful snapshot while a newer data update awaits profile validation. Use the analyzer for current values.</p>':''}<p class="lede">Individual analysis from verified statistics and published model outputs. Select a player to compare production, usage and scoring formats.</p><label for="playerSearch">Find a player, team or position</label><br><input id="playerSearch" class="profile-search" type="search" placeholder="Search players"><p id="playerCount" role="status">${active.length} players</p><ul class="player-directory">${active.map(p=>`<li><a href="/players/${esc(p.slug)}/">${teamLogo(p,esc,{small:true})}<span>${esc(p.name)}<small>${esc(p.team)} · ${p.position} · Half-PPR ${p.rankings.half.rank===999?'unranked':'rank '+p.rankings.half.rank}</small></span></a></li>`).join('')}</ul><script defer src="/player-directory.js"></script>`);
 for(const p of release.profiles){
  const title=`${p.name} Fantasy Outlook, Projections & Trade Value`;
  const description=`${p.name} fantasy analysis: ${p.position}${p.rankings.half.posRank} in Half PPR, trade values, verified ${p.season} production through Week ${p.throughWeek}, usage and weekly projections.`;
  const r=p.rankings;
  const status=p.retained?'This player is no longer in the current published model. This page retains the last verified profile.':!p.active?'This player is outside the current profile Top 250. The permanent page remains available.':'';
  const personSchema=JSON.stringify({'@context':'https://schema.org','@type':'Person',name:p.name,identifier:p.id,url:'https://www.rosterreport.app/players/'+p.slug+'/'}).replace(/</g,'\\u003c');
  const body=`<script type="application/ld+json">${personSchema}</script>${assets}<div class="player-analysis">${stale?'<p class="projection-notice">This is the last validated profile snapshot. Newer model or projection inputs are available; <a href="/">open the analyzer for current values</a>.</p>':''}<p><a href="/players/">All player profiles</a> / ${esc(p.name)}</p><div class="player-hero">${teamLogo(p,esc)}<p class="lede">${esc(p.team)} · ${p.position} · ${p.season} redraft outlook</p></div><p class="data-meta">12-team baseline · Half-PPR trade tiers · PPR weekly calls with 4-point passing TDs</p>${status?`<p class="projection-notice">${status}</p>`:''}<dl class="player-summary"><div><dt>Half-PPR rank</dt><dd>${p.position}${r.half.posRank} · ${r.half.rank===999?'Unranked overall':'#'+r.half.rank}</dd></div><div><dt>Half-PPR trade value</dt><dd>${number(r.half.value)}</dd></div><div><dt>PPR trade value</dt><dd>${number(r.ppr.value)}</dd></div><div><dt>Standard trade value</dt><dd>${number(r.standard.value)}</dd></div></dl><p class="data-meta">Observed statistics through Week ${p.throughWeek} · Source snapshot ${dateLabel(p.statisticsAsOf)}.<br>Rankings: ${p.rankingsAsOf?dateLabel(p.rankingsAsOf):'published repository snapshot; original model-run time unavailable'}.<br>Week ${p.projectionWeek} projections: ${dateLabel(p.projectionAsOf)} · ${esc(p.projectionStatus)}.</p>${weeklyStatProjection(p,esc,dateLabel)}${renderMatchup(p,matchupEvidence,esc,dateLabel)}${relatedArticles(p,articles,esc)}${p.paragraphs.map(x=>`<h2>${x.heading}</h2><p>${esc(x.text)}</p>`).join('')}<p><a class="seo-cta" href="/#analyzer">Compare ${esc(p.name)} in the Trade Analyzer →</a></p><p><a href="/rankings/${p.position.toLowerCase()}/">${p.position} rankings</a> · <a href="/projections/${p.position.toLowerCase()}/">${p.position} projections</a> · <a href="/methodology/">Model methodology</a></p><details><summary>Sources and calculation notes</summary><p>Automatically generated by The Roster Report from source-linked statistics and published calculations. Fantasy tiers use a 12-team, one-QB baseline; lineup calls use the player’s rank within the published PPR forecast. Trade stances are editorial interpretations of model tiers, not market-price claims. Efficiency comparisons require three recorded games and at least 50 pass attempts for QBs, 30 carries for RBs, or 20 targets for WRs/TEs within the analyzer’s player pool. These editorial rules do not change model scores or rankings. No manual player writeups. Model neutral defaults are excluded from observed-stat claims. Recorded games can include injury-shortened appearances. Recent comparisons use appearances, not missed-game zeros.</p><ul>${p.sources.map(s=>`<li><a href="${esc(s.url)}">nflverse ${esc(s.file)}</a> · snapshot SHA-256 <code>${s.sha256}</code></li>`).join('')}</ul><p>Default-league values include the analyzer’s existing availability and RB adjustments. Custom scoring, Superflex and package premiums are evaluated inside the analyzer. No market discount or buy/sell recommendation is inferred without supporting market data.</p><p>Projection run assumptions: ${esc(p.projectionUpdateNote||'Read the published availability notes before setting a lineup.')}</p></details><p><a href="/players/">Browse all 250 profiles</a></p></div>`;
  // Do not claim a new model/statistical date on a presentation-only rebuild.
  page('players/'+p.slug,title,description,body);
 }
}
