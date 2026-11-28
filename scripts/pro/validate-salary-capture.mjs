import fs from 'node:fs';import path from 'node:path';import {parseArgs} from 'node:util';
import {validateOfficialCapture} from '../../server/draftkings-evidence.mjs';
const {values}=parseArgs({options:{directory:{type:'string'},sport:{type:'string'},group:{type:'string'},output:{type:'string'}}});
if(!values.directory||!values.sport||!values.group||!values.output)throw Error('Required: --directory DIR --sport NFL|NBA --group ID --output JSON');
const read=name=>fs.readFileSync(path.join(values.directory,name+'.response'),'utf8'),prefix=values.sport.toLowerCase();
const result=validateOfficialCapture({sport:values.sport,draftGroupId:values.group,salaryCsv:read(prefix+'-'+values.group+'-csv'),draftablesJson:read(prefix+'-'+values.group),lobbyJson:read(prefix+'-lobby'),rulesJson:read(prefix+'-rules'),captures:JSON.parse(fs.readFileSync(path.join(values.directory,'capture-report.json'))).captures});
fs.writeFileSync(values.output,JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({sport:result.sport,group:result.draftGroupId,salaryDataApproved:result.salaryDataApproved,modelReleaseApproved:result.publishApproved,...result.validation}));
