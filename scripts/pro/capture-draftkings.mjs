/** Read-only official salary capture. No login, contest entry, retries or publication. */
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import {parseCsv} from '../../server/slate-ingestion.mjs';
const out=process.argv[2];if(!out)throw Error('Supply an output directory');await fs.mkdir(out,{recursive:true});
const sources=[['nfl-lobby','https://www.draftkings.com/lobby/getcontests?sport=NFL'],['nba-lobby','https://www.draftkings.com/lobby/getcontests?sport=NBA'],['nfl-156416','https://api.draftkings.com/draftgroups/v1/draftgroups/156416/draftables'],['nba-156734','https://api.draftkings.com/draftgroups/v1/draftgroups/156734/draftables'],['nfl-156416-csv','https://www.draftkings.com/bulklineup/getdraftablecsv?draftGroupId=156416'],['nba-156734-csv','https://www.draftkings.com/bulklineup/getdraftablecsv?draftGroupId=156734'],['nfl-rules','https://api.draftkings.com/lineups/v1/gametypes/1/rules'],['nba-rules','https://api.draftkings.com/lineups/v1/gametypes/70/rules'],['nba-injury-20261115-1200','https://ak-static.cms.nba.com/referee/injury/Injury-Report_2026-11-15_12_00PM.pdf'],['nfl-inactives-20261115','https://www.nfl.com/news/nfl-week-10-inactives-players-ruled-out-sunday-2026-season']];
const report=[];
for(const [name,url] of sources){
 const capturedAt=new Date().toISOString();
 try{
  const response=await fetch(url,{signal:AbortSignal.timeout(20000),redirect:'error',headers:{Accept:name.endsWith('-csv')?'text/csv':'application/json'}});
  const bytes=Buffer.from(await response.arrayBuffer()),body=bytes.toString('utf8');const contentType=response.headers.get('content-type')||'';
  const record={name,url,capturedAt,receivedAt:new Date().toISOString(),status:response.status,contentType,bytes:bytes.length,sha256:crypto.createHash('sha256').update(bytes).digest('hex')};
  // Keep the original response for provenance. HTML failures never become salary data.
  await fs.writeFile(`${out}/${name}.response`,bytes);
  if(response.ok&&name.startsWith('nba-injury-')&&bytes.subarray(0,5).toString()==='%PDF-')record.documentValid=true;
  else if(response.ok&&name.startsWith('nfl-inactives-')&&contentType.includes('html'))record.htmlCaptured=true;
  else if(response.ok&&name.endsWith('-csv')){const rows=parseCsv(body);record.csvValid=true;record.salaryRows=rows.length;record.uniqueDraftKingsIds=new Set(rows.map(r=>r.ID)).size;}
  else if(!response.ok||!contentType.includes('json'))record.error='Response is not successful JSON; capture is not usable salary evidence.';
  else{const parsed=JSON.parse(body);record.topLevelKeys=Object.keys(parsed);if(Array.isArray(parsed.draftables))record.draftableRows=parsed.draftables.length;record.jsonValid=true;}
  report.push(record);
 }catch(error){report.push({name,url,capturedAt,error:error.name+': '+error.message});}
}
await fs.writeFile(`${out}/capture-report.json`,JSON.stringify({publishApproved:false,captures:report},null,2)+'\n');
console.log(JSON.stringify(report));
