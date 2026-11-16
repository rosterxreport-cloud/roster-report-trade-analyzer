import test from 'node:test';import assert from 'node:assert/strict';
import {adaptNFLCore,NFL_CORE_HASH} from '../../server/nfl-core-adapter.mjs';
import {optimize} from '../../server/optimizer.mjs';
import {buildSlate} from '../../server/slate-ingestion.mjs';
const now=Date.parse('2026-11-16T20:00:00Z'),capturedAt='2026-11-16T19:50:00Z',validUntil='2026-11-16T21:00:00Z';
test('original NFL scoring copies RR means, adjusts interceptions and attributes defenses',()=>{
 const weekly={season:2026,week:11,source:'data/projections/2026_week11_league_v4_full.csv',updatedAt:capturedAt,players:[{Player:'Synthetic QB',Team:'DAL',Opponent:'TEN',Position:'QB',PPR:19,Half_PPR:19,Standard:19,INT:1,Pass_Yds:300}]};
 const manifest={forecast_week:11,as_of:capturedAt,model_sha256:'a'.repeat(64),model_base:'Established structural v4 model, fixture'};
 const defenses={season:2026,week:11,capturedAt,validUntil,source:'https://dfsroto.win/projections',sourceHash:'synthetic',players:[{name:'Synthetic DST',team:'DAL',opponent:'TEN',projection:7}]};
 const before=JSON.stringify(weekly),args={weekly,manifest,defenses,coreHash:NFL_CORE_HASH,generatorHash:manifest.model_sha256,finalSnapshotReceipt:{verifiedStatlines:true,commit:'a'.repeat(40),sourceCsvHash:'synthetic',sourceJsonHash:'synthetic'}},model=adaptNFLCore(args,now);
 assert.equal(model.scoring,'RR-DK-core');assert.equal(model.players[0].projection,20);assert.equal(model.players[0].statline.Pass_Yds,300);assert.equal(JSON.stringify(weekly),before);assert.equal(model.players[1].source,'dfsroto DST');assert.match(model.provenance.scoringNote,/omitted/);
 assert.throws(()=>adaptNFLCore({...args,defenses:{...defenses,week:12}},now),/do not match/);
 assert.throws(()=>adaptNFLCore({...args,coreHash:'replacement'},now),/established/);
});
test('NFL Pro projection controls do not fabricate simulations; NBA still requires real draws',()=>{
 const positions=['QB','RB','WR','TE','DST'];
 const players=Array.from({length:30},(_,i)=>({id:String(i+1),name:'Synthetic '+i,team:i%2?'A':'B',opponent:i%2?'B':'A',gameId:String(Math.floor(i/10)),startsAt:validUntil,verifiedAt:capturedAt,status:'active',positions:[positions[i%5]],salary:4000,projection:20+i/10}));
 const slate={schemaVersion:1,kind:'slate',sport:'NFL',slateId:'synthetic',format:'DraftKings Classic',salaryCap:50000,scoring:'RR-DK-core',publishApproved:true,capturedAt,validUntil,provenance:{modelHash:'synthetic',sourceHash:'synthetic',salarySource:'fixture',injurySource:'fixture',eligibilitySource:'fixture',scoringMethod:'weekly-ppr-plus-interceptions',scoringNote:'Synthetic core scoring fixture'},players};
 const result=optimize(slate,{advanced:true,count:2,stack:1,minUnique:1},now);
 assert.equal(result.lineups.length,2);assert(result.lineups.every(l=>l.simulation===null));assert.equal(result.mode,'Advanced RR projection controls');assert.equal(result.scoring,'RR-DK-core');
 assert.throws(()=>optimize({...slate,sport:'NBA'},{advanced:true},now),/joint simulation/);
});
function coverageInput(){
 const players=[{id:'1',name:'Synthetic One',team:'ATL',opponent:'BOS',gameId:'1',projection:30},{id:'2',name:'Synthetic Two',team:'NYK',opponent:'CHI',gameId:'2',projection:25}];
 const model={schemaVersion:1,kind:'projections',sport:'NBA',scoring:'DraftKings',publishApproved:true,capturedAt,validUntil,provenance:{modelHash:'fixture',sourceHash:'fixture-source'},players};
 const mappings=[...players.map(p=>({dkId:p.id,modelId:p.id,team:p.team,opponent:p.opponent,gameId:p.gameId})),{dkId:'3',modelId:'missing',team:'ATL',opponent:'BOS',gameId:'1',projectionExclusion:{reason:'not-projected-by-established-model',sourceHash:'fixture-source'}}].map(p=>({...p,status:'active',verifiedAt:capturedAt,startsAt:validUntil}));
 return {model,salaryCsv:'ID,Name,Position,Salary,TeamAbbrev\n1,Synthetic One,PG,5000,ATL\n2,Synthetic Two,C,5000,NYK\n3,Synthetic Unmodeled,SG,3000,ATL\n',decisionAt:new Date(now).toISOString(),manifest:{schemaVersion:1,sport:'NBA',slateId:'synthetic',format:'DraftKings Classic',publishApproved:true,completeSalaryPool:true,gameIds:['1','2'],playerMappings:mappings,salarySource:'fixture',injurySource:'fixture',scheduleSource:'fixture',salaryCapturedAt:capturedAt,injuryCapturedAt:capturedAt,scheduleCapturedAt:capturedAt}};
}
test('model coverage exclusions require an explicit source-bound policy and never add zero forecasts',()=>{
 let input=coverageInput(),result=buildSlate(input);assert.equal(result.report.releaseApproved,false);
 input.manifest.excludeUnmodeled=true;result=buildSlate(input);assert.equal(result.report.releaseApproved,true);assert.equal(result.artifact.players.length,2);assert.equal(result.artifact.coverage.excludedNoModel.length,1);assert(!result.artifact.players.some(p=>p.projection===0));
 input.manifest.playerMappings[2].projectionExclusion.sourceHash='different-model';assert.equal(buildSlate(input).report.releaseApproved,false);
});
