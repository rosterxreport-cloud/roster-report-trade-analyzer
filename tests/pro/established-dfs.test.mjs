import test from 'node:test';import assert from 'node:assert/strict';import crypto from 'node:crypto';
import {adaptWeeklyNFL} from '../../server/nfl-weekly-adapter.mjs';
import {selectGroup} from '../../scripts/pro/capture-current-salaries.mjs';
const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
function input(){
 const capturedAt='2026-11-16T19:00:00Z',validUntil='2026-11-17T00:00:00Z';
 const manifest={model_sha256:'c95ac28e53c2c9550827391269dcaff95127ee8397730b33072bc81d00441d6d',model_base:'Established structural v4 model, unchanged',forecast_week:10,as_of:capturedAt};
 const weekly={season:2026,week:10,source:'data/projections/2026_week10_league_v4_full.csv',updatedAt:capturedAt,players:[{Player:'Synthetic QB',Team:'ATL',Opponent:'BOS',Position:'QB',Pass_Att:30,Pass_Yds:300,Pass_TD:2,INT:1,Rush_Att:2,Rush_Yds:10,Rush_TD:0,Targets:0,Receptions:0,Rec_Yds:0,Rec_TD:0,Standard:19,Half_PPR:19,PPR:19}]};
 const evidence={season:2026,forecastWeek:10,capturedAt,validUntil,weeklySourceHash:hash(weekly),modelHash:manifest.model_sha256,publishApproved:true,source:'Synthetic existing-event fixture',players:[{id:'1',name:'Synthetic QB',team:'ATL',opponent:'BOS',position:'QB',gameId:'1',startsAt:validUntil,events:{Fumbles_Lost:1,Two_Point_Conversions:0,Return_TD:0,Offensive_Fumble_Recovery_TD:0,Pass_300_Probability:.6,Rush_100_Probability:0,Rec_100_Probability:0}}]};
 return {weekly,manifest,evidence};
}
const now=Date.parse('2026-11-16T20:00:00Z');
test('NFL DFS preserves weekly means and PPR while applying only explicit DK scoring',()=>{
 const a=input(),before=JSON.stringify(a.weekly),r=adaptWeeklyNFL(a.weekly,a.manifest,a.evidence,now);
 assert.equal(r.players[0].projection,20.8);assert.equal(r.players[0].fantasyPoints.PPR,19);
 assert.equal(r.players[0].statline.Pass_Yds,300);assert.equal(JSON.stringify(a.weekly),before);assert.equal(r.provenance.modelUnchanged,true);
});
test('NFL source replacement, stale evidence and missing events cannot be promoted',()=>{
 let a=input();a.manifest.model_sha256='experimental';assert.throws(()=>adaptWeeklyNFL(a.weekly,a.manifest,a.evidence,now),/established weekly/);
 a=input();delete a.evidence.players[0].events.Pass_300_Probability;assert.throws(()=>adaptWeeklyNFL(a.weekly,a.manifest,a.evidence,now),/Missing modeled/);
 a=input();a.weekly.players[0].Pass_Yds=900;assert.throws(()=>adaptWeeklyNFL(a.weekly,a.manifest,a.evidence,now),/exact established/);
 a=input();assert.throws(()=>adaptWeeklyNFL(a.weekly,a.manifest,a.evidence,now+86400000),/current/);
});
test('current salary discovery rejects locked, unsupported and single-game groups',()=>{
 const g=(id,GameCount,GameTypeId=70,StartDate='2026-11-17T00:00:00Z')=>({DraftGroupId:id,Sport:'NBA',GameCount,GameTypeId,StartDate});
 const lobby={DraftGroups:[g(1,12,70,'2026-11-16T00:00:00Z'),g(2,1),g(3,9,99),g(4,5),g(5,3)]};
 assert.equal(selectGroup(lobby,'NBA',now).DraftGroupId,4);
 assert.throws(()=>selectGroup({DraftGroups:[]},'NBA',now),/No upcoming/);
});
