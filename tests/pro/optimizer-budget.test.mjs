import test from 'node:test';import assert from 'node:assert/strict';import {optimize,SLOTS} from '../../server/optimizer.mjs';
test('basic search retains affordable completions when high scorers crowd the beam',()=>{
 const now=Date.parse('2026-11-17T15:00:00Z'),positions=['PG','SG','SF','PF','C'];
 const players=Array.from({length:38},(_,i)=>({id:String(i+1),name:'Synthetic '+i,team:i%2?'AAA':'BBB',opponent:i%2?'BBB':'AAA',gameId:String(i%2),positions,salary:i<30?9000:3000,projection:i<30?40:1,status:'active',startsAt:new Date(now+3600000).toISOString(),verifiedAt:new Date(now).toISOString()}));
 const slate={schemaVersion:1,kind:'slate',sport:'NBA',slateId:'synthetic-budget',format:'DraftKings Classic',salaryCap:50000,publishApproved:true,capturedAt:new Date(now).toISOString(),validUntil:new Date(now+60000).toISOString(),provenance:{modelHash:'synthetic',sourceHash:'synthetic',salarySource:'synthetic',injurySource:'synthetic',eligibilitySource:'synthetic'},players};
 const result=optimize(slate,{},now),lineup=result.lineups[0];assert.equal(lineup.players.length,SLOTS.NBA.length);assert.ok(lineup.salary<=50000);assert.equal(new Set(lineup.players.map(p=>p.id)).size,8);
});
