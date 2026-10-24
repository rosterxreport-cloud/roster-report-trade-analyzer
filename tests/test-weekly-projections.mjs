import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {points,selectPlayers,pageRows,statline} from '../projections/model.mjs';
const data=JSON.parse(fs.readFileSync(new URL('../data/weekly-projections.json',import.meta.url)));
test('source snapshot covers every position with unique finite rows',()=>{
 assert.equal(data.players.length,Object.values(data.counts).reduce((a,b)=>a+b,0));
 assert.equal(new Set(data.players.map(p=>p.Player)).size,data.players.length);
 for(const p of data.players){for(const f of ['Pass_TD','Receptions','PPR','Half_PPR','Standard'])assert.ok(Number.isFinite(p[f]));}
});
test('scoring uses exact baseline values; 6-point passing TD changes QBs only',()=>{
 for(const p of data.players){assert.equal(points(p,'ppr',4),p.PPR);assert.equal(points(p,'half',4),p.Half_PPR);assert.equal(points(p,'standard',4),p.Standard);
 assert.ok(Math.abs(points(p,'ppr',6)-p.PPR-(p.Position==='QB'?2*p.Pass_TD:0))<1e-8);}
 const fixture={Position:'QB',PPR:10,Half_PPR:10,Standard:10,Pass_TD:2};assert.equal(points(fixture,'ppr',6),14);
});
test('combined filters, case-insensitive search, empty result and pagination',()=>{
 const sample=data.players.find(p=>p.Position==='RB');
 const rows=selectPlayers(data.players,{position:'RB',team:sample.Team,search:sample.Player.toUpperCase()});assert.equal(rows.length,1);assert.equal(rows[0].Player,sample.Player);
 assert.equal(selectPlayers(data.players,{search:'no such player xyz'}).length,0);
 const all=selectPlayers(data.players);assert.equal(pageRows(all,1,30).length,30);assert.equal(pageRows(all,2,30)[0],all[30]);assert.equal(new Set([...pageRows(all,1,30),...pageRows(all,2,30)].map(p=>p.Player)).size,60);
});
test('numeric sorting and scoring reranking do not mutate source records',()=>{
 const snapshot=JSON.stringify(data.players);
 for(const dir of ['asc','desc']){const rows=selectPlayers(data.players,{sort:'Rush_Yds',direction:dir});for(let i=1;i<rows.length;i++)assert.ok(dir==='asc'?rows[i].Rush_Yds>=rows[i-1].Rush_Yds:rows[i].Rush_Yds<=rows[i-1].Rush_Yds);}
 const fixtures=[{Player:'Runner',Position:'RB',PPR:13,Half_PPR:13,Standard:13,Pass_TD:0},{Player:'Passer',Position:'QB',PPR:10,Half_PPR:10,Standard:10,Pass_TD:2}];
 assert.equal(selectPlayers(fixtures,{passTD:4})[0].Player,'Runner');assert.equal(selectPlayers(fixtures,{passTD:6})[0].Player,'Passer');assert.equal(JSON.stringify(data.players),snapshot);
});
test('full statlines retain RB rushing and receiving, QB passing and rushing',()=>{
 assert.match(statline(data.players.find(p=>p.Position==='RB')),/carries.*rush yds.*rush TD\nt.*|carries.*rush yds.*rush TD\n.*targets.*catches.*rec yds/s);
 assert.match(statline(data.players.find(p=>p.Position==='QB')),/pass yds.*pass TD.*INT\n.*carries/);
});
