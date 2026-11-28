import test from 'node:test';import assert from 'node:assert/strict';import {startingImpact,tradeAnalysis} from '../../server/trade.mjs';
test('lineup assignment handles FLEX without double-counting',()=>{const r=startingImpact([{name:'a',pos:'RB',weekly:20},{name:'b',pos:'RB',weekly:15},{name:'c',pos:'WR',weekly:18}],['RB','WR','FLEX'],'weekly');assert.equal(r.total,53);assert.equal(r.players.length,3);});
test('trade reuses published values and weekly projections, rejects invented player IDs',()=>{const ranks={half:[{name:'a',pos:'RB',value:40},{name:'b',pos:'RB',value:50}]},p={season:2026,week:10,updatedAt:'now',players:[{Player:'a',Half_PPR:15},{Player:'b',Half_PPR:20}]};const r=tradeAnalysis({roster:['a'],give:['a'],receive:['b'],slots:['RB']},ranks,p);assert.equal(r.weekly.delta,5);assert.equal(r.rosValueIndex.incoming,50);assert(!r.confidence.calibrated);assert.throws(()=>tradeAnalysis({roster:['a'],give:['a'],receive:['made up']},ranks,p));});
test('duplicate names use the ranked team and unresolved identities withhold weekly impact',()=>{
 const ranks={half:[{name:'Same Name',team:'MIN',pos:'QB',value:40},{name:'Other',team:'NYJ',pos:'QB',value:30}]};
 const p={season:2026,week:10,players:[{Player:'Same Name',Team:'LV',Half_PPR:0},{Player:'Same Name',Team:'MIN',Half_PPR:15},{Player:'Other',Team:'NYJ',Half_PPR:10}]};
 const request={roster:['Same Name'],give:['Same Name'],receive:['Other'],slots:['QB']};
 assert.equal(tradeAnalysis(request,ranks,p).weekly.before.total,15);
 ranks.half[0].team='UNKNOWN';const result=tradeAnalysis(request,ranks,p);
 assert(result.weekly.missing.includes('Same Name'));assert.equal(result.weekly.before.total,0);assert.equal(result.weekly.delta,null);
});
