import fs from 'node:fs/promises';
import {adaptWeeklyNFL} from '../../server/nfl-weekly-adapter.mjs';
const args=process.argv.slice(2);
if(args.length!==4)throw Error('Supply weekly JSON, run manifest, existing-model DK evidence JSON and private output path.');
const [weekly,manifest,evidence]=await Promise.all(args.slice(0,3).map(async p=>JSON.parse(await fs.readFile(p,'utf8'))));
const artifact=adaptWeeklyNFL(weekly,manifest,evidence);
await fs.writeFile(args[3],JSON.stringify(artifact)+'\n',{mode:0o600});
console.log(JSON.stringify({players:artifact.players.length,modelUnchanged:true,capturedAt:artifact.capturedAt}));
