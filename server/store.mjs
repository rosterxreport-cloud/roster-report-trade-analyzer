import {fail} from './domain.mjs';
export function config(){
 const env=process.env;
 if(!env.SUPABASE_URL||!env.SUPABASE_SERVICE_ROLE_KEY||!env.SUPABASE_ANON_KEY||!env.RATE_LIMIT_SECRET)fail(503,'Account services are awaiting secure configuration.');
 return env;
}
export async function supa(path,{method='GET',body,token,auth=false}={}){
 const env=config();const key=auth?env.SUPABASE_ANON_KEY:env.SUPABASE_SERVICE_ROLE_KEY;
 const response=await fetch(env.SUPABASE_URL+(auth?'/auth/v1/':'/rest/v1/')+path,{method,headers:{apikey:key,Authorization:'Bearer '+(token||key),'Content-Type':'application/json',Prefer:'return=representation'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(12000)});
 const data=await response.json().catch(()=>null);
 if(!response.ok)fail(auth?401:503,auth?'Sign-in could not be verified. Please try again.':'Account service is temporarily unavailable.');
 return data;
}
export async function rpc(name,args){return supa('rpc/'+name,{method:'POST',body:args});}
export async function modelArtifact(name){
 const env=config();const response=await fetch(`${env.SUPABASE_URL}/storage/v1/object/authenticated/${env.MODEL_BUCKET||'toolkit-private'}/${name}`,{headers:{Authorization:'Bearer '+env.SUPABASE_SERVICE_ROLE_KEY},signal:AbortSignal.timeout(15000)});
 if(!response.ok)fail(503,'Release-approved data is not available for this tool yet.');return response.json();
}
