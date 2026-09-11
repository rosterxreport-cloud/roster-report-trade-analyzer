import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const context={};vm.createContext(context);vm.runInContext(fs.readFileSync(new URL('../scoring-settings.js',import.meta.url),'utf8'),context);
const defaults=vm.runInContext('SCORING_DEFAULTS',context);
const players=[{name:'Volume QB',pos:'QB',value:80,rank:1},{name:'Low QB',pos:'QB',value:70,rank:2},{name:'High TE',pos:'TE',value:65,rank:3},{name:'Low TE',pos:'TE',value:55,rank:4},{name:'WR',pos:'WR',value:60,rank:5},{name:'No Long TD',pos:'WR',value:50,rank:6}];
const profiles={
 'Volume QB':{baselinePoints:340,passingTds:40,passingYards:5000,rushingTds:3},'Low QB':{baselinePoints:250,passingTds:15,passingYards:2800,rushingTds:1},
 'High TE':{baselinePoints:220,receptions:90,receivingTds:7,receivingFirstDowns:55,longTds40:3,longTds50:2},'Low TE':{baselinePoints:130,receptions:30,receivingTds:7,receivingFirstDowns:15,longTds40:0,longTds50:0},
 'WR':{baselinePoints:250,receptions:80,receivingTds:8,receivingFirstDowns:60,longTds40:4,longTds50:2},'No Long TD':{baselinePoints:180,receptions:60,receivingFirstDowns:35}
};
const apply=s=>context.applyCustomScoring(players,profiles,s),by=(list,n)=>list.find(p=>p.name===n);
assert.strictEqual(apply({}),players,'defaults must return the exact live list');
let out=apply({passTd:6});assert(by(out,'Volume QB').value>80);assert.equal(by(out,'High TE').value,65);assert(Math.abs(by(out,'Volume QB').customScoringImpact)<=.10);
out=apply({passYard:.05});assert(by(out,'Volume QB').value/80>by(out,'Low QB').value/70);
out=apply({tePremium:.5});assert(by(out,'High TE').value-65>by(out,'Low TE').value-55);assert.equal(by(out,'WR').value,60);
out=apply({receiveFirstDown:.25});assert(by(out,'WR').value>60);assert(by(out,'High TE').value>65);
out=apply({longTdBonus:2,longTdThreshold:50});assert(by(out,'WR').value>60);assert.equal(by(out,'No Long TD').value,50);
out=apply(defaults);assert.strictEqual(out,players,'reset defaults must restore exact values and ranks');
console.log('League scoring adjustment tests passed');
