import test from 'node:test';
import assert from 'node:assert/strict';
import {optimize,validateLineup} from '../../server/optimizer.mjs';

test('a large multi-position NBA pool completes tournament search within its own budget',()=>{
 const now=Date.parse('2026-11-20T22:00:00Z');
 const players=Array.from({length:140},(_,i)=>({id:String(i+1),name:'Large-pool fixture '+i,team:i%2?'AAA':'BBB',opponent:i%2?'BBB':'AAA',gameId:String(i%4),positions:['PG','SG','SF','PF','C'],salary:3000+(i%60)*100,projection:15+(i%60)*.4,status:'active',startsAt:new Date(now+3600000).toISOString(),verifiedAt:new Date(now).toISOString()}));
 const slate={schemaVersion:1,kind:'slate',sport:'NBA',slateId:'large-pool-fixture',format:'DraftKings Classic',salaryCap:50000,publishApproved:true,capturedAt:new Date(now).toISOString(),validUntil:new Date(now+60000).toISOString(),provenance:{modelHash:'fixture',sourceHash:'fixture',salarySource:'fixture',injurySource:'fixture',eligibilitySource:'fixture'},players,simulations:{draws:10000,joint:true,scoring:'DraftKings',modelHash:'fixture',scores:Object.fromEntries(players.map((p,i)=>[p.id,Array.from({length:10000},(_,j)=>p.projection+Math.sin(j*.1+i)*8)]))}};
 const original=players.map(p=>p.projection),result=optimize(slate,{advanced:true,count:1},now),lineup=result.lineups[0];
 assert.equal(lineup.players.length,8);
 assert.ok(validateLineup(lineup.players.map(p=>players.find(q=>q.id===p.id)),'NBA'));
 assert.ok(Number.isFinite(lineup.simulation.p95));
 assert.deepEqual(players.map(p=>p.projection),original);
 assert.equal(slate.simulations.draws,10000);
});
