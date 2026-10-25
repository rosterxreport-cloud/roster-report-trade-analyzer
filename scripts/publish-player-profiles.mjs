import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {makeRelease} from './player-profiles.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const args=process.argv.slice(2),value=flag=>args.includes(flag)?args[args.indexOf(flag)+1]:undefined;
const evidencePath=value('--evidence'),auditPath=value('--ranking-evidence');
const {registry,release}=await makeRelease(root,{evidencePath,auditPath,requireFresh:args.includes('--require-fresh')});
// Validate the complete release before replacing either file. CI commits both together.
for(const [file,data] of [['player-registry.json',registry],['player-profiles.json',release]]){
 const target=path.join(root,'data',file),temp=target+'.tmp';fs.writeFileSync(temp,JSON.stringify(data,null,2)+'\n');fs.renameSync(temp,target);
}
if(evidencePath)fs.copyFileSync(path.join(root,evidencePath),path.join(root,'data/player-evidence.json'));
if(auditPath&&fs.existsSync(path.join(root,auditPath)))fs.copyFileSync(path.join(root,auditPath),path.join(root,'data/ranking-evidence.json'));
const exceptions=release.profiles.filter(p=>p.wordCount<200||p.wordCount>300).map(p=>`${p.name}: ${p.wordCount} words`);
console.log(`Validated ${release.profiles.filter(p=>p.active).length} active profiles; ${exceptions.length} evidence/length exceptions.\n${exceptions.join('\n')}`);
