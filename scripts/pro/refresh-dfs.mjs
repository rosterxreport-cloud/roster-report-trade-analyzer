import {validateModelLineage} from '../../server/model-lineage.mjs';
import {adaptWeeklyNFL} from '../../server/nfl-weekly-adapter.mjs';
import {buildSlate} from '../../server/slate-ingestion.mjs';
import {validateSlate,optimize} from '../../server/optimizer.mjs';
import {validateArtifact} from '../../server/domain.mjs';
// Consumes the established private model feed; never fits or changes a model.
export async function prepareRefresh(bundle,now=new Date()){
 const decisionAt=now.toISOString(),artifacts=[];
 const sports=bundle.sports??['NBA','NFL'];
 if(!Array.isArray(sports)||!sports.length||new Set(sports).size!==sports.length||sports.some(s=>!['NBA','NFL'].includes(s)))throw Error('Explicit refresh sports must be NBA and/or NFL.');
 if(bundle.slates?.some(s=>!sports.includes(s.weekly?'NFL':s.model?.sport)))throw Error('Source contains a slate outside the selected refresh sports.');
 for(const sport of sports){
  const items=bundle.slates?.filter(s=>(s.weekly?'NFL':s.model?.sport)===sport)||[];
  const catalog=[];
  for(const source of items){
   const input=source.weekly?{...source,model:adaptWeeklyNFL(source.weekly,source.weeklyManifest,source.scoringEvidence,now.getTime())}:source;
   validateModelLineage(input.model);
   const {artifact,report}=buildSlate({...input,decisionAt});
   if(!report.releaseApproved)throw Error(sport+' slate failed release validation.');
   validateSlate(artifact,now.getTime());
   if(!/^[-a-zA-Z0-9_]{1,60}$/.test(artifact.slateId))throw Error('Invalid source slate identity.');
   optimize(artifact,{advanced:!!input.joint,count:1},now.getTime());
   // Immutable paths prevent a failed refresh from replacing the previous slate.
   const version=artifact.slateId+'-'+now.getTime();artifact.slateId=version;
   artifacts.push({path:sport.toLowerCase()+'/slates/'+version+'.json',data:artifact});
   catalog.push({id:version,name:input.manifest.name||sport+' DraftKings Classic',locksAt:artifact.validUntil});
  }
  if(!catalog.length)throw Error(sport+' has no validated upcoming slate in the source feed.');
  artifacts.push({path:sport.toLowerCase()+'/slates.json',data:{capturedAt:decisionAt,slates:catalog}});
 }
 if(sports.includes('NBA'))for(const [file,kind] of [['basic','projections'],['distributions','distributions']]){
  const data=bundle.nba?.[file];validateModelLineage(data);validateArtifact(data,{kind,sport:'NBA',now:now.getTime()});
  if(file==='distributions'&&(data.draws!==10000||data.scoring!=='DraftKings'))throw Error('NBA distribution release is incomplete.');
  artifacts.push({path:'nba/'+file+'.json',data});
 }
 return artifacts;
}
function storageConfig(env){
 for(const key of ['SUPABASE_URL','SUPABASE_SERVICE_ROLE_KEY'])if(!env[key])throw Error('Missing '+key);
 const endpoint=new URL(env.SUPABASE_URL);
 if(endpoint.protocol!=='https:'||endpoint.username||endpoint.password||endpoint.search||endpoint.hash)throw Error('Private storage endpoint must use credential-free HTTPS.');
 const bucket=env.MODEL_BUCKET||'toolkit-private';
 if(!/^[-a-zA-Z0-9_]+$/.test(bucket))throw Error('Invalid private model bucket.');
 return {endpoint:endpoint.origin,bucket};
}
// Direct private scheduled runners can publish locally generated output without a feed service.
// Validation completes for the entire bundle before the first storage request.
export async function refreshBundle(bundle,env=process.env,{now=new Date(),fetchImpl=fetch,validateOnly=false}={}){
 const artifacts=await prepareRefresh(bundle,now);
 if(validateOnly)return {validated:artifacts.length,published:0,decisionAt:now.toISOString()};
 const {endpoint,bucket}=storageConfig(env);
 const ordered=[...artifacts.filter(a=>!a.path.endsWith('/slates.json')),...artifacts.filter(a=>a.path.endsWith('/slates.json'))];
 let published=0;
 for(const a of ordered){
  let response;
  try{response=await fetchImpl(endpoint+'/storage/v1/object/'+bucket+'/'+a.path,{method:'POST',headers:{Authorization:'Bearer '+env.SUPABASE_SERVICE_ROLE_KEY,apikey:env.SUPABASE_SERVICE_ROLE_KEY,'Content-Type':'application/json','x-upsert':a.path.includes('/slates/')?'false':'true'},body:JSON.stringify(a.data),redirect:'error',signal:AbortSignal.timeout(30000)});}
  catch{throw Error('Private artifact upload failed; refresh stopped.');}
  if(!response.ok)throw Error('Private artifact upload failed; refresh stopped.');
  published++;
 }
 return {published,decisionAt:now.toISOString()};
}
export async function refresh(env=process.env,options={}){
 for(const key of ['DFS_SOURCE_URL','DFS_SOURCE_TOKEN'])if(!env[key])throw Error('Missing '+key);
 storageConfig(env);
 const source=new URL(env.DFS_SOURCE_URL);
 if(source.protocol!=='https:'||source.username||source.password)throw Error('Source endpoint must use credential-free HTTPS.');
 let response;
 try{response=await (options.fetchImpl||fetch)(env.DFS_SOURCE_URL,{headers:{Authorization:'Bearer '+env.DFS_SOURCE_TOKEN},redirect:'error',signal:AbortSignal.timeout(30000)});}
 catch{throw Error('Established-model source feed is unavailable.');}
 if(!response.ok)throw Error('Established-model source feed is unavailable.');
 return refreshBundle(await response.json(),env,options);
}
export async function runCli(args=process.argv.slice(2),env=process.env){
 if(!args.length)return refresh(env);
 if(args[0]!=='--bundle'||!args[1]||args.length>3||(args[2]&&args[2]!=='--validate-only'))throw Error('Use --bundle /private/refresh-bundle.json [--validate-only].');
 const {readFile,stat}=await import('node:fs/promises');
 const info=await stat(args[1]);
 if(!info.isFile()||info.size>128*1024*1024)throw Error('Invalid private refresh bundle file.');
 const bundle=JSON.parse(await readFile(args[1],'utf8'));
 return refreshBundle(bundle,env,{validateOnly:args[2]==='--validate-only'});
}
if(process.argv[1]?.endsWith('/refresh-dfs.mjs')){
 try{console.log(JSON.stringify(await runCli()));}
 catch{console.error('DFS refresh failed. Check source configuration, input validation and private storage access. Publication may be partial after a storage failure; inspect catalogs before retrying.');process.exitCode=1;}
}
