import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {analysis,editorialContext} from '../scripts/player-analysis.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const data=JSON.parse(fs.readFileSync(path.join(root,'data/player-profiles.json'),'utf8'));
const find=name=>structuredClone(data.profiles.find(p=>p.name===name));
test('elite verdicts give a clear trade stance and explain the receiving contribution',()=>{
 const p=find('Jahmyr Gibbs'),text=analysis(p).map(x=>x.text).join(' ');
 assert.match(text,/elite RB1 asset/);assert.match(text,/Start him as an RB1/);assert.match(text,/Demand a premium return/);
 const rows=p.weekly.filter(w=>!w.statsMissing);const receiving=rows.reduce((s,w)=>s+w.receptions+w.receiving_yards/10,0)/rows.length;
 assert(text.includes(receiving.toFixed(1)+' PPR points per game before receiving touchdowns'));
 assert(!/do not guarantee|current relative assessment|not a guaranteed market/.test(text));
});
test('a verified weekly out overrides even an elite rank and an existing projection',()=>{
 const p=find('Jahmyr Gibbs');p.editorial.out='Jahmyr Gibbs — Week 7 Out, test report';
 const call=analysis(p)[2].text;assert.match(call,/Keep him out of Week 7 lineups/);assert(!call.includes('Start him'));assert.match(call,/elite RB1/);
 const smith=find('DeVonta Smith');assert(smith.editorial.out);assert.match(analysis(smith)[2].text,/Keep him out of Week 7 lineups/);
});
test('stale or mismatched manifest overrides cannot create an out designation',()=>{
 const p=find('DeVonta Smith'),projection={week:7,updatedAt:'2026-10-24T00:00:00Z',players:[]};
 const context=editorialContext(p,{evidence:{players:{}},adjusted:{half:[]},projection,manifest:{forecast_week:7,as_of:'2026-10-23T00:00:00Z',verified_out_overrides:{[p.id]:'Out'}}});assert.equal(context.out,null);
});
test('absence of a projection remains distinct from an out designation',()=>{
 const p=find('Jordyn Tyson');p.editorial.out=null;
 const call=analysis(p)[2].text;assert.match(call,/no Week 7 projection/);assert.match(call,/not a zero-point prediction or confirmation that he is out/);assert(!call.includes('Start him'));
});
test('historical return assumptions stay conditional despite a strong weekly forecast',()=>{
 const p=find('Josh Jacobs'),text=analysis(p).map(x=>x.text).join(' ');
 assert.match(text,/if active under the stated role assumption/);assert.match(text,/12 games in 2025/);assert(!text.includes('at user request'));
 assert.match(text,/FLEX option asset for rest-of-season trades/);
});
test('qualification minimums prevent tiny samples from earning an efficiency rank',()=>{
 const p=find('Jalen McMillan');assert.equal(p.editorial.efficiency,null);const text=analysis(p)[1].text;assert.match(text,/below our comparison minimum/);assert(!/Strong efficiency backs/.test(text));
});
