import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {matchupAnalysis,renderMatchup} from '../scripts/player-matchups.mjs';
const load=p=>JSON.parse(fs.readFileSync(new URL('../'+p,import.meta.url)));
const evidence=load('data/matchup-evidence.json'),profiles=load('data/player-profiles.json').profiles;
const eligible=position=>structuredClone(profiles.find(p=>p.position===position&&p.projection&&!p.editorial?.out));
test('each position uses measured defensive context without changing published forecasts',()=>{
 for(const position of ['QB','RB','WR','TE']){
  const p=eligible(position),before=JSON.stringify(p),r=matchupAnalysis(p,evidence);
  assert(r.text,p.name);assert(r.text.includes(p.projection.Opponent));assert(r.text.includes(p.projection.PPR.toFixed(1)+' PPR points'));
  assert.equal(JSON.stringify(p),before);
  assert(!/NaN|undefined|because|lowers our projection/.test(r.text));
 }
});
test('leading WR splits are attached only to the measured current leader',()=>{
 const leader=profiles.find(p=>p.position==='WR'&&p.projection&&!p.editorial?.out&&evidence.currentLeaders[p.projection.Team]===p.id&&evidence.leadingWR[p.projection.Opponent]?.games>=3);
 assert(leader);assert(matchupAnalysis(leader,evidence).text.includes('opposing leading receivers'));
 const p=structuredClone(leader);p.id='not-the-leader';assert(!matchupAnalysis(p,evidence).text.includes('opposing leading receivers'));
});
test('missing or misaligned evidence, outs, retained pages and missing forecasts withhold claims',()=>{
 const p=eligible('RB');
 for(const e of [null,{...evidence,season:2025},{...evidence,throughWeek:evidence.throughWeek-1},{...evidence,source:{url:evidence.source.url,sha256:'f'.repeat(64)}},{...evidence,source:{url:'https://example.com',sha256:'bad'}}])assert(matchupAnalysis(p,e).unavailable);
 for(const change of [{projection:null},{editorial:{out:'verified'}},{retained:true},{projectionWeek:99}])assert(matchupAnalysis({...p,...change},evidence).unavailable);
 const e=structuredClone(evidence);e.positions.RB[p.projection.Opponent].games=2;assert(matchupAnalysis(p,e).unavailable);
 e.positions.RB[p.projection.Opponent].games=6;delete e.positions.RB[p.projection.Opponent].perGame.receptions;assert(matchupAnalysis(p,e).unavailable);
});
test('rendered analysis provides a source, rank direction and methodology without JavaScript',()=>{
 const html=renderMatchup(eligible('RB'),evidence,s=>String(s).replaceAll('<','&lt;'),s=>s);
 assert(html.includes('<h2>Week '));assert(html.includes(evidence.source.sha256));assert(html.includes('Rank 1 allows the most'));assert(html.includes('not an individual player forecast'));assert(!html.includes('<script'));
});
