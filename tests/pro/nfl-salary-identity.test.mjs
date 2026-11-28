import test from 'node:test';
import assert from 'node:assert/strict';
import {assembleNFL} from '../../scripts/pro/assemble-nfl-slate.mjs';
import {NFL_CORE_HASH} from '../../server/nfl-core-adapter.mjs';

const now=Date.parse('2026-11-19T19:00:00Z'),stamp=new Date(now).toISOString(),lock=new Date(now+3600000).toISOString();
function fixture(){
 const player={Player:'James Cook',Team:'BUF',Opponent:'NYJ',Position:'RB',PPR:20,INT:0};
 const weekly={season:2026,week:11,updatedAt:stamp,source:'data/projections/2026_week11_league_v4_full.csv',players:[player]};
 const source={weekly,manifest:{forecast_week:11,model_sha256:'a'.repeat(64),model_base:'Established structural v4 model fixture'},generatorHash:'a'.repeat(64),coreHash:NFL_CORE_HASH,finalSnapshotReceipt:{verifiedStatlines:true,commit:'b'.repeat(40),sourceCsvHash:'c'.repeat(64),sourceJsonHash:'d'.repeat(64)},defenses:{season:2026,week:11,capturedAt:stamp,validUntil:lock,source:'https://dfsroto.win/projections',sourceHash:'e'.repeat(64),players:[]}};
 const pool={sport:'NFL',salaryDataApproved:true,validation:{allCsvRowsMatched:true,fullApiPlayerCoverage:true},locksAt:lock,draftGroupId:'fixture',games:[{id:'game'}],sourceRecords:{draftables:{capturedAt:stamp,url:'https://example.test/draftables'},salaryCsv:{capturedAt:stamp,url:'https://example.test/salaries'}},players:[{id:'11',name:'James Cook III',team:'BUF',opponent:'NYJ',positions:['RB'],gameId:'game',startsAt:lock,sourceStatus:'active'}]};
 return {source,pool};
}
test('operator suffix variants keep the exact RR forecast after team, position and matchup checks',async()=>{
 for(const suffix of ['III','Jr.','Sr.']){
  const {source,pool}=fixture(),before=JSON.stringify(source.weekly);pool.players[0].name='James Cook '+suffix;
  const bundle=await assembleNFL(pool,'fixture',source,now),slate=bundle.slates[0];
  assert.equal(slate.manifest.playerMappings[0].modelId,'James Cook|BUF');
  assert.equal(slate.model.players[0].projection,20);
  assert.equal(slate.model.players[0].name,pool.players[0].name);
  assert.equal(JSON.stringify(source.weekly),before);
 }
});
test('name normalization cannot cross teams or ignore a matchup mismatch',async()=>{
 let {source,pool}=fixture();pool.players[0].team='NE';
 let b=await assembleNFL(pool,'fixture',source,now);assert.match(b.slates[0].manifest.playerMappings[0].modelId,/^unmodeled:/);
 ({source,pool}=fixture());pool.players[0].opponent='MIA';
 await assert.rejects(assembleNFL(pool,'fixture',source,now),/different matchup/);
});
test('ambiguous source aliases and duplicate operator identities fail closed',async()=>{
 let {source,pool}=fixture();source.weekly.players.push({...source.weekly.players[0],Player:'James Cook Jr.'});
 await assert.rejects(assembleNFL(pool,'fixture',source,now),/Ambiguous weekly/);
 ({source,pool}=fixture());pool.players.push({...pool.players[0],id:'12',name:'James Cook'});
 await assert.rejects(assembleNFL(pool,'fixture',source,now),/Multiple operator identities/);
});
