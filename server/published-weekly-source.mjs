import crypto from 'node:crypto';
const root='https://raw.githubusercontent.com/rosterxreport-cloud/roster-report-trade-analyzer/';
const hash=x=>crypto.createHash('sha256').update(x).digest('hex');
const fields=['Pass_Att','Pass_Yds','Pass_TD','INT','Rush_Att','Rush_Yds','Rush_TD','Targets','Receptions','Rec_Yds','Rec_TD','Standard','Half_PPR','PPR'];
function csvRows(text){
 const rows=[];let row=[],cell='',quoted=false;
 for(let i=0;i<text.length;i++){const c=text[i];if(c==='"'){if(quoted&&text[i+1]==='"'){cell+='"';i++;}else quoted=!quoted;}else if(!quoted&&(c===','||c==='\n')){row.push(cell.replace(/\r$/,''));cell='';if(c==='\n'){if(row.some(Boolean))rows.push(row);row=[];}}else cell+=c;}
 if(quoted)throw Error('Invalid weekly CSV quoting.');if(cell||row.length){row.push(cell.replace(/\r$/,''));rows.push(row);}
 const header=rows.shift();if(!header||new Set(header).size!==header.length)throw Error('Invalid weekly CSV header.');
 return rows.map(values=>{if(values.length!==header.length)throw Error('Invalid weekly CSV row.');return Object.fromEntries(header.map((k,i)=>[k,values[i]]));});
}
export function verifyPublishedWeekly(weekly,csv,commit,jsonBytes){
 if(!/^[a-f0-9]{40}$/.test(commit)||!/^data\/projections\/20\d{2}_week\d+_league_v4_full\.csv$/.test(weekly.source||''))throw Error('Invalid published weekly source identity.');
 const rows=csvRows(csv),key=p=>p.Player+'|'+p.Team+'|'+p.Position,byId=new Map(rows.map(p=>[key(p),p]));
 if(byId.size!==rows.length||rows.length!==weekly.players?.length||rows.length<100)throw Error('Final weekly projection pool mismatch.');
 const seen=new Set();
 for(const p of weekly.players){
  const id=key(p),row=byId.get(id);if(!row||seen.has(id)||row.Opponent!==p.Opponent)throw Error('Final weekly player identity mismatch.');seen.add(id);
  for(const field of fields)if(!Number.isFinite(p[field])||!Number.isFinite(Number(row[field]))||Math.abs(Number(row[field])-p[field])>1e-8)throw Error('Final weekly statline differs from the published master.');
 }
 return {commit,verifiedStatlines:true,players:rows.length,sourceCsvHash:hash(csv),sourceJsonHash:hash(jsonBytes)};
}
export async function fetchPublishedWeekly(fetchImpl=fetch,{ref:branch='main'}={}){
 if(!['main','feat/toolkit-pro-platform'].includes(branch))throw Error('Unsupported weekly source branch.');
 const ref=await fetchImpl('https://api.github.com/repos/rosterxreport-cloud/roster-report-trade-analyzer/git/ref/heads/'+branch,{headers:{Accept:'application/vnd.github+json'},redirect:'error',signal:AbortSignal.timeout(20000)});
 if(!ref.ok)throw Error('Published weekly commit is unavailable.');const commit=(await ref.json()).object?.sha;
 if(!/^[a-f0-9]{40}$/.test(commit||''))throw Error('Invalid weekly commit receipt.');
 async function get(path){const r=await fetchImpl(root+commit+'/'+path,{redirect:'error',signal:AbortSignal.timeout(25000)});if(!r.ok)throw Error('Published weekly source unavailable: '+path);return r.text();}
 const jsonBytes=await get('data/weekly-projections.json'),weekly=JSON.parse(jsonBytes);
 if(!/^data\/projections\/20\d{2}_week\d+_league_v4_full\.csv$/.test(weekly.source||''))throw Error('Unsupported weekly source path.');
 const csv=await get(weekly.source),finalSnapshotReceipt=verifyPublishedWeekly(weekly,csv,commit,jsonBytes);
 const manifest=JSON.parse(await get('data/projections/'+weekly.season+'_week'+weekly.week+'_run_manifest.json'));
 const generatorPath=manifest.generator_path||'scripts/projection_week'+weekly.week+'_league_v4.py';
 if(!/^scripts\/(projection_week\d+_league_v4\.py|pro\/create-weekly-nfl\.py)$/.test(generatorPath))throw Error('Unapproved weekly generator path.');
 const generator=await get(generatorPath),core=await get('scripts/projection_v4_backtest.py');
 return {weekly,manifest,finalSnapshotReceipt,generatorHash:hash(generator),coreHash:hash(core)};
}
