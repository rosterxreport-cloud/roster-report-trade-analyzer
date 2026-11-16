import {buildSlate} from '../../server/slate-ingestion.mjs';
import {validateSlate,optimize} from '../../server/optimizer.mjs';
import {validateArtifact} from '../../server/domain.mjs';
// Consumes the established private model feed; never fits or changes a model.
export async function prepareRefresh(bundle,now=new Date()){
 const decisionAt=now.toISOString(),artifacts=[];
 for(const sport of ['NBA','NFL']){
  const items=bundle.slates?.filter(s=>s.model?.sport===sport)||[];
  const catalog=[];
  for(const input of items){
   const {artifact,report}=buildSlate({...input,decisionAt});
   if(!report.releaseApproved)throw Error(sport+' slate failed release validation.');
   validateSlate(artifact,now.getTime());
   if(!/^[-a-zA-Z0-9_]{1,60}$/.test(artifact.slateId))throw Error('Invalid source slate identity.');
   optimize(artifact,{advanced:true,count:1},now.getTime());
   // Immutable paths prevent a failed refresh from replacing the previous slate.
   const version=artifact.slateId+'-'+now.getTime();artifact.slateId=version;
   artifacts.push({path:sport.toLowerCase()+'/slates/'+version+'.json',data:artifact});
   catalog.push({id:version,name:input.manifest.name||sport+' DraftKings Classic',locksAt:artifact.validUntil});
  }
  if(!catalog.length)throw Error(sport+' has no validated upcoming slate in the source feed.');
  artifacts.push({path:sport.toLowerCase()+'/slates.json',data:{capturedAt:decisionAt,slates:catalog}});
 }
 for(const [file,kind] of [['basic','projections'],['distributions','distributions']]){
  const data=bundle.nba?.[file];validateArtifact(data,{kind,sport:'NBA',now:now.getTime()});
  if(file==='distributions'&&(data.draws!==10000||data.scoring!=='DraftKings'))throw Error('NBA distribution release is incomplete.');
  artifacts.push({path:'nba/'+file+'.json',data});
 }
 return artifacts;
}
export async function refresh(env=process.env){
 for(const key of ['DFS_SOURCE_URL','DFS_SOURCE_TOKEN','SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY'])if(!env[key])throw Error('Missing '+key);
 if(new URL(env.DFS_SOURCE_URL).protocol!=='https:'||new URL(env.SUPABASE_URL).protocol!=='https:')throw Error('Refresh endpoints must use HTTPS.');
 const response=await fetch(env.DFS_SOURCE_URL,{headers:{Authorization:'Bearer '+env.DFS_SOURCE_TOKEN},redirect:'error',signal:AbortSignal.timeout(30000)});
 if(!response.ok)throw Error('Established-model source feed is unavailable.');
 const artifacts=await prepareRefresh(await response.json());
 // Upload all immutable slates before changing any discovery catalog.
 const ordered=[...artifacts.filter(a=>!a.path.endsWith('/slates.json')),...artifacts.filter(a=>a.path.endsWith('/slates.json'))];
 for(const a of ordered){const r=await fetch(env.SUPABASE_URL+'/storage/v1/object/'+(env.MODEL_BUCKET||'toolkit-private')+'/'+a.path,{method:'POST',headers:{Authorization:'Bearer '+env.SUPABASE_SERVICE_ROLE_KEY,apikey:env.SUPABASE_SERVICE_ROLE_KEY,'Content-Type':'application/json','x-upsert':'true'},body:JSON.stringify(a.data),redirect:'error',signal:AbortSignal.timeout(30000)});if(!r.ok)throw Error('Private artifact upload failed; refresh stopped.');}
 return {published:artifacts.length,capturedAt:new Date().toISOString()};
}
if(process.argv[1]?.endsWith('/refresh-dfs.mjs')){try{console.log(JSON.stringify(await refresh()));}catch{console.error('DFS refresh failed. Check source configuration, input validation and private storage access. No invalid slate was published.');process.exitCode=1;}}
