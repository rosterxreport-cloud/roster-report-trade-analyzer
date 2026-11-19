import fs from 'node:fs';import path from 'node:path';import {buildSlate} from '../../server/slate-ingestion.mjs';
const args=Object.fromEntries(process.argv.slice(2).map((v,i,a)=>v.startsWith('--')?[v.slice(2),a[i+1]]:null).filter(Boolean));
for(const key of ['salaries','manifest','model','decision-at','output'])if(!args[key])throw Error('Required --'+key);
const json=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const result=buildSlate({salaryCsv:fs.readFileSync(args.salaries,'utf8'),manifest:json(args.manifest),model:json(args.model),joint:args.joint?json(args.joint):null,decisionAt:args['decision-at']});
fs.mkdirSync(path.dirname(path.resolve(args.output)),{recursive:true});fs.writeFileSync(args.output,JSON.stringify(result.artifact));fs.writeFileSync(args.output+'.report.json',JSON.stringify(result.report,null,2));
console.log(JSON.stringify(result.report,null,2));
