/** Retrieve and cross-check current official Classic salaries; never grants model/availability approval. */
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {validateOfficialCapture} from '../../server/draftkings-evidence.mjs';
export function selectGroup(lobby,sport,now=Date.now()){
 const gameType=sport==='NBA'?70:sport==='NFL'?1:null;
 if(!gameType)throw Error('Unsupported DFS sport.');
 const horizon=now+(sport==='NBA'?48:8*24)*3600000;
 let groups=(lobby.DraftGroups||[]).filter(g=>g.Sport===sport&&g.GameTypeId===gameType&&g.GameCount>=2&&/^\d+$/.test(String(g.DraftGroupId))&&Date.parse(g.StartDate)>now&&Date.parse(g.StartDate)<=horizon);
 if(sport==='NBA'&&groups.length){const date=new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'});const first=[...new Set(groups.map(g=>date.format(new Date(g.StartDate))))].sort()[0];groups=groups.filter(g=>date.format(new Date(g.StartDate))===first);}
 groups.sort((a,b)=>b.GameCount-a.GameCount||Date.parse(a.StartDate)-Date.parse(b.StartDate)||Number(a.DraftGroupId)-Number(b.DraftGroupId));
 if(!groups.length)throw Error('No upcoming supported Classic slate is listed.');
 return groups[0];
}
export async function captureCurrent(sport,out,{fetchImpl=fetch,now=()=>Date.now()}={}){
 const captures=[],bytes={};await fs.mkdir(out,{recursive:true,mode:0o700});
 async function capture(name,url){
  const capturedAt=new Date(now()).toISOString();
  const response=await fetchImpl(url,{redirect:'error',signal:AbortSignal.timeout(30000)});
  if(!response.ok)throw Error('Official salary retrieval failed: '+name+' HTTP '+response.status);
  const buffer=Buffer.from(await response.arrayBuffer());
  captures.push({name,url,capturedAt,receivedAt:new Date(now()).toISOString(),status:response.status,sha256:crypto.createHash('sha256').update(buffer).digest('hex')});
  bytes[name]=buffer;await fs.writeFile(out+'/'+name+'.response',buffer,{mode:0o600});return buffer.toString('utf8');
 }
 const prefix=sport.toLowerCase(),lobbyJson=await capture(prefix+'-lobby','https://www.draftkings.com/lobby/getcontests?sport='+sport);
 const group=String(selectGroup(JSON.parse(lobbyJson),sport,now()).DraftGroupId);
 const draftablesJson=await capture(prefix+'-'+group,'https://api.draftkings.com/draftgroups/v1/draftgroups/'+group+'/draftables');
 const salaryCsv=await capture(prefix+'-'+group+'-csv','https://www.draftkings.com/bulklineup/getdraftablecsv?draftGroupId='+group);
 const rulesJson=await capture(prefix+'-rules','https://api.draftkings.com/lineups/v1/gametypes/'+(sport==='NBA'?70:1)+'/rules');
 const pool=validateOfficialCapture({sport,draftGroupId:group,salaryCsv,draftablesJson,lobbyJson,rulesJson,captures,now:now()});
 await fs.writeFile(out+'/capture-report.json',JSON.stringify({publishApproved:false,captures},null,2)+'\n',{mode:0o600});
 await fs.writeFile(out+'/salary-pool.json',JSON.stringify(pool)+'\n',{mode:0o600});
 return pool;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 try{
  if(process.argv.length!==4)throw Error('Supply NBA or NFL and a private output directory.');
  const pool=await captureCurrent(process.argv[2],process.argv[3]);
  console.log(JSON.stringify({sport:pool.sport,draftGroupId:pool.draftGroupId,players:pool.players.length,locksAt:pool.locksAt,salaryDataApproved:true,modelApproved:false}));
 }catch(e){console.error(e.message);process.exitCode=1;}
}
