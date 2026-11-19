import test from 'node:test';import assert from 'node:assert/strict';import {verifyPublishedWeekly} from '../../server/published-weekly-source.mjs';
const fields=['Pass_Att','Pass_Yds','Pass_TD','INT','Rush_Att','Rush_Yds','Rush_TD','Targets','Receptions','Rec_Yds','Rec_TD','Standard','Half_PPR','PPR'];
function fixture(){
 const players=Array.from({length:100},(_,i)=>({Player:'Synthetic '+i,Team:'DAL',Opponent:'TEN',Position:'WR',...Object.fromEntries(fields.map(k=>[k,k==='PPR'?20:0]))}));
 const header=['Player','Team','Opponent','Position',...fields],csv=header.join(',')+'\n'+players.map(p=>header.map(k=>p[k]).join(',')).join('\n');
 return {weekly:{source:'data/projections/2026_week11_league_v4_full.csv',players},csv};
}
test('final weekly source requires complete JSON/CSV statline agreement at one commit',()=>{
 const {weekly,csv}=fixture(),receipt=verifyPublishedWeekly(weekly,csv,'a'.repeat(40),JSON.stringify(weekly));assert.equal(receipt.players,100);assert.equal(receipt.verifiedStatlines,true);assert.equal(receipt.sourceCsvHash.length,64);
 weekly.players[0].PPR=0;assert.throws(()=>verifyPublishedWeekly(weekly,csv,'a'.repeat(40),JSON.stringify(weekly)),/differs/);
});
test('partial or mismatched published snapshots cannot replace the final weekly source',()=>{
 const {weekly,csv}=fixture();assert.throws(()=>verifyPublishedWeekly(weekly,csv.split('\n').slice(0,-1).join('\n'),'a'.repeat(40),JSON.stringify(weekly)),/pool mismatch/);
 weekly.players[0].Opponent='OTHER';assert.throws(()=>verifyPublishedWeekly(weekly,csv,'a'.repeat(40),JSON.stringify(weekly)),/identity mismatch/);
});

import {selectGroup} from '../../scripts/pro/capture-current-salaries.mjs';
test('NBA discovery keeps the earliest available game day before considering a larger future slate',()=>{const now=Date.parse('2026-11-16T20:00:00Z'),group=(id,count,start)=>({Sport:'NBA',GameTypeId:70,DraftGroupId:id,GameCount:count,StartDate:start});assert.equal(selectGroup({DraftGroups:[group(1,4,'2026-11-17T00:00:00Z'),group(2,9,'2026-11-18T00:00:00Z')]},'NBA',now).DraftGroupId,1);});

test('duplicate player names across teams and stale position totals cannot enter DFS',()=>{
 const {weekly,csv}=fixture();
 weekly.counts={QB:0,RB:0,WR:99,TE:0};
 assert.throws(()=>verifyPublishedWeekly(weekly,csv,'a'.repeat(40),JSON.stringify(weekly)),/position counts/);
 delete weekly.counts;
 weekly.players[1].Player=weekly.players[0].Player;weekly.players[1].Team='NYG';
 assert.throws(()=>verifyPublishedWeekly(weekly,csv,'a'.repeat(40),JSON.stringify(weekly)),/Ambiguous/);
});
