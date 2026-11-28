import test from 'node:test';import assert from 'node:assert/strict';import {nflDetails} from '../../server/nfl-details.mjs';
const player=(name,targets,ppr)=>({Player:name,Team:'AAA',Opponent:'BBB',Position:'WR',Pass_Att:0,Pass_Yds:0,Pass_TD:0,INT:0,Rush_Att:0,Rush_Yds:0,Rush_TD:0,Targets:targets,Receptions:targets/2,Rec_Yds:targets*5,Rec_TD:0,Standard:ppr-targets/2,Half_PPR:ppr-targets/4,PPR:ppr});
test('premium workload and rank use published values without modifying the source',()=>{
 const w={season:2026,week:11,players:[player('One',8,20),player('Two',2,10)]},before=JSON.stringify(w);const result=nflDetails(w,{player:'One'}).players[0];assert.equal(result.positionRank,1);assert.equal(result.workload.teamTargetAllocation,.8);assert.equal(result.statline.PPR,20);assert.equal(result.efficiency.yardsPerCatch,10);assert.equal(JSON.stringify(w),before);
});
test('missing and ambiguous player releases fail explicitly',()=>{assert.throws(()=>nflDetails({players:[player('One',8,20)]},{player:'Other'}),/no published forecast/);assert.throws(()=>nflDetails({players:[player('One',8,20),player('One',2,10)]}),/identities/);});
