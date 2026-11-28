import fs from 'node:fs';import path from 'node:path';import {backtestSlate} from '../../server/backtest.mjs';
const args=Object.fromEntries(process.argv.slice(2).map((v,i,a)=>v.startsWith('--')?[v.slice(2),a[i+1]]:null).filter(Boolean));
for(const key of ['slate','actuals','decision-at','output'])if(!args[key])throw Error('Required --'+key);
const json=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const result=backtestSlate({slate:json(args.slate),actuals:json(args.actuals),decisionAt:args['decision-at'],options:args.options?json(args.options):{},contest:args.contest?json(args.contest):null});
fs.mkdirSync(path.dirname(path.resolve(args.output)),{recursive:true});fs.writeFileSync(args.output,JSON.stringify(result,null,2));console.log(JSON.stringify({slate:result.slateId,projectionAudit:result.projectionAudit,lineupScores:result.lineups.map(l=>l.actual),verifiedCashRate:null,verifiedROI:null}));
