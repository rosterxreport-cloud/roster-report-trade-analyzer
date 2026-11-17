import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import {weeklyPlayers} from '../../server/weekly-player-identity.mjs';import {nflDetails} from '../../server/nfl-details.mjs';
test('actual archived weekly release omits only documented zero placeholder and preserves the forecast',()=>{
 const weekly=JSON.parse(fs.readFileSync(new URL('../../data/weekly-projections.json',import.meta.url))),before=JSON.stringify(weekly),r=weeklyPlayers(weekly);
 const conflicts=weekly.players.filter(p=>p.Player==='Kirk Cousins');
 if(conflicts.length>1){assert.ok(r.excluded.some(p=>p.name==='Kirk Cousins'&&p.team==='LV'));assert.deepEqual(r.players.find(p=>p.Player==='Kirk Cousins'),conflicts.find(p=>p.Team==='MIN'));}
 assert.equal(new Set(r.players.map(p=>p.Player)).size,r.players.length);assert.ok(nflDetails(weekly).players.length>100);assert.equal(JSON.stringify(weekly),before);
});
test('two actual forecasts or an undocumented zero row remain ambiguous',()=>{
 for(const rows of [[{Player:'Synthetic',PPR:1},{Player:'Synthetic',PPR:2}],[{Player:'Synthetic',PPR:0},{Player:'Synthetic',PPR:2}]])assert.throws(()=>weeklyPlayers({players:rows}),/Ambiguous/);
});
