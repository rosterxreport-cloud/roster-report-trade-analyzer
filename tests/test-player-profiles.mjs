import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {analysis,makeRelease,hash,renderProfiles,weeklyStatProjection} from '../scripts/player-profiles.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const read=f=>fs.readFileSync(path.join(root,f),'utf8'),load=f=>JSON.parse(read(f));
const saved=load('data/player-profiles.json');
function fixture(){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'rr-profiles-'));
 for(const f of [load('data/weekly-projections.json').source.replace('_league_v4_full.csv','_run_manifest.json'),'app.js','scoring-settings.js','injury-layer.js','injury-adjustments.json','players.json','data/player-profiles.json','data/player-evidence.json','data/player-registry.json','data/weekly-projections.json']){const p=path.join(dir,f);fs.mkdirSync(path.dirname(p),{recursive:true});fs.copyFileSync(path.join(root,f),p);}
 return dir;
}
const write=(dir,file,d)=>fs.writeFileSync(path.join(dir,file),JSON.stringify(d));
test('250 active profiles have stable unique identities, evidence and validated analysis length',()=>{
 assert.equal(saved.profiles.filter(p=>p.active).length,250);
 assert.equal(new Set(saved.profiles.map(p=>p.id)).size,saved.profiles.length);
 assert.equal(new Set(saved.profiles.map(p=>p.slug)).size,saved.profiles.length);
 for(const p of saved.profiles){
  assert.equal(JSON.stringify(p.paragraphs),JSON.stringify(analysis(p)));assert(p.wordCount>=180&&p.wordCount<=340,p.name+' '+p.wordCount);
  assert.equal(p.paragraphs.length,4);assert(p.sources.every(s=>s.url.startsWith('https://github.com/nflverse/')&&/^[a-f0-9]{64}$/.test(s.sha256)));
  assert(p.paragraphs.every(x=>x.evidenceRefs.length));
 }
});
test('rebuilding uses exactly the published injury and RB adjusted values, preserves data and is deterministic',async()=>{
 const before=['players.json','app.js','injury-adjustments.json','data/weekly-projections.json'].map(f=>[f,hash(read(f))]);
 const a=await makeRelease(root),b=await makeRelease(root);assert.equal(JSON.stringify(a),JSON.stringify(b));
 for(const p of a.release.profiles){assert(Number.isFinite(p.rankings.half.value));assert.equal(p.paragraphs[0].text.includes(p.name),true);}
 for(const [f,h] of before)assert.equal(hash(read(f)),h,f);
});
test('missing offensive samples and forecasts never become zeros or invented trends',()=>{
 const p=saved.profiles.find(p=>!p.weekly.length&&!p.projection);assert(p);
 const text=p.paragraphs.map(x=>x.text).join(' ');assert.match(text,/no verified offensive counting-stat sample/);assert.match(text,/not a zero-point prediction/);assert(!text.includes('averaged 0'));
 const copy=structuredClone(p);copy.weekly=[{week:6,statsMissing:true,snapShare:.5}];assert.match(analysis(copy)[1].text,/no measured carry, target or passing-volume trend/);
});
test('verified numerical formulas use appearances and observed denominators',()=>{
 const p=structuredClone(saved.profiles.find(p=>p.position==='WR'&&p.weekly.length>=6));assert(p);
 const rows=p.weekly.filter(w=>!w.statsMissing),t=rows.reduce((s,w)=>s+w.targets,0),y=rows.reduce((s,w)=>s+w.receiving_yards,0);
 const text=analysis(p).map(x=>x.text).join(' ');assert(text.includes((y/t).toFixed(1)+' yards per target'));
 const denom=rows.reduce((s,w)=>s+w.teamPassAttempts,0);assert(text.includes((t/denom*100).toFixed(1)+'% of team pass attempts'));
});
test('unsupported causal explanations are withheld; recorded calculation changes are explicit',()=>{
 const p=structuredClone(saved.profiles[0]);p.change={previousRank:p.rankings.half.rank+5,scoreDelta:1.25};
 let text=analysis(p).at(-1).text;assert.match(text,/rose 5 overall spots/);assert(!/because|injury caused|due to/.test(text));
 p.calculationChange={previousLiveSignal:70,liveSignal:75,previousRoleMultiplier:.8,roleMultiplier:.9};text=analysis(p).at(-1).text;assert(text.includes('70.00 to 75.00'));assert(text.includes('0.80 to 0.90'));
});
test('a player leaving Top 250 retains their permanent URL',async()=>{
 const dir=fixture();try{
 const db=JSON.parse(fs.readFileSync(path.join(dir,'players.json')));const selected=saved.profiles[0];const outside=db.half.filter(p=>['QB','RB','WR','TE'].includes(p.pos)).sort((a,b)=>a.rank-b.rank).at(-1);
 const inside=db.half.find(p=>p.name===selected.name);outside.rank=inside.rank;inside.rank=1001;write(dir,'players.json',db);
 const r=(await makeRelease(dir)).release;assert.equal(r.profiles.filter(p=>p.active).length,250);const retained=r.profiles.find(p=>p.id===selected.id);assert(!retained.active);assert.equal(retained.slug,selected.slug);assert(r.profiles.length>=saved.profiles.length);for(const old of saved.profiles)assert(r.profiles.some(p=>p.id===old.id));
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
test('invalid identities and stale evidence fail without changing the last good release',async()=>{
 const dir=fixture();try{
 const original=fs.readFileSync(path.join(dir,'data/player-profiles.json'),'utf8');const ev=JSON.parse(fs.readFileSync(path.join(dir,'data/player-evidence.json')));ev.players={};write(dir,'data/player-evidence.json',ev);
 await assert.rejects(makeRelease(dir),/Missing identity/);assert.equal(fs.readFileSync(path.join(dir,'data/player-profiles.json'),'utf8'),original);
 ev.capturedAt='2020-01-01T00:00:00Z';write(dir,'data/player-evidence.json',ev);await assert.rejects(makeRelease(dir,{requireFresh:true}),/older than seven days/);
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
test('retained snapshots display a clear stale banner and all profiles render without JavaScript',()=>{
 const pages=[];renderProfiles({release:saved,stale:true,page:(slug,title,desc,body)=>pages.push({slug,title,desc,body}),esc:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),write:()=>{},dateLabel:s=>s});
 assert.equal(pages.length,saved.profiles.length+1);for(const p of saved.profiles){const page=pages.find(x=>x.slug==='players/'+p.slug);assert(page.body.includes('last validated profile snapshot'));assert(page.body.includes(p.paragraphs[0].text));assert(page.body.includes('href="/#analyzer"'));}
});

test('weekly stat cards preserve published statlines, all scoring formats and availability safeguards',()=>{
 const esc=s=>String(s).replace(/</g,'&lt;'),date=s=>s;
 for(const position of ['QB','RB','WR','TE']){
  const p=structuredClone(saved.profiles.find(p=>p.position===position&&p.projection&&!p.editorial?.out));
  const html=weeklyStatProjection(p,esc,date);
  assert(html.includes('Rushing yards'));assert(html.includes('Standard points'));assert(html.includes('Half-PPR points'));assert(html.includes('PPR points'));
  assert(html.includes(p.projection.PPR.toFixed(1)));
  assert.equal(html.includes('Passing yards'),position==='QB');assert.equal(html.includes('Receiving yards'),position!=='QB');
  p.projection.Rush_Yds=null;assert(weeklyStatProjection(p,esc,date).includes('Unavailable'));
  p.editorial={out:{reason:'out'}};assert(!weeklyStatProjection(p,esc,date).includes('weekly-stat-projections'));
  p.editorial={};p.projection=null;assert(weeklyStatProjection(p,esc,date).includes('not a zero-point forecast'));
 }
});
