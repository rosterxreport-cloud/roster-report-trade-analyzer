import {createRemoteJWKSet,decodeJwt,jwtVerify} from 'npm:jose@6.1.3';
import {trustedDeployment,allowedBackendPath} from './gateway-policy.mjs';
import {forwardBackendResponse} from './gateway-response.mjs';
const issuers=['https://oidc.vercel.com/the-roster-report','https://oidc.vercel.com'];
const jwks=new Map(issuers.map(issuer=>[issuer,createRemoteJWKSet(new URL(issuer+'/.well-known/jwks'))]));
const json=(data:unknown,status=200)=>Response.json(data,{status,headers:{'Cache-Control':'no-store'}});
Deno.serve(async request=>{
 if(request.method!=='POST')return json({error:'Method not allowed'},405);
 try{
  const token=request.headers.get('Authorization')?.replace(/^Bearer /,'');if(!token)return json({error:'Unauthorized'},401);
  const issuer=decodeJwt(token).iss;if(!issuers.includes(issuer||''))return json({error:'Unauthorized'},401);
  const {payload}=await jwtVerify(token,jwks.get(issuer!)!,{issuer,audience:'https://vercel.com/the-roster-report',algorithms:['RS256'],maxTokenAge:'65m'});
  if(!trustedDeployment(payload))return json({error:'Deployment is outside staging scope'},403);
  const text=await request.text();if(text.length>1048576)return json({error:'Request too large'},413);
  const input=JSON.parse(text),method=input.method||'GET';
  const root=Deno.env.get('SUPABASE_URL')!,key=Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
  let url;
  if(input.storage){
   if(method!=='GET'||(input.storage!=='nba/roster-weekly.json'&&! /^(nba|nfl)\/(basic|distributions|slates|slates\/[-a-zA-Z0-9_]{1,80})\.json$/.test(input.storage)))return json({error:'Unsupported artifact'},403);
   url=root+'/storage/v1/object/authenticated/toolkit-private/'+input.storage;
  }else{
   if(!allowedBackendPath(input.path,method))return json({error:'Unsupported operation'},403);
   url=root+'/rest/v1/'+input.path;
  }
  const result=await fetch(url,{method,headers:{apikey:key,Authorization:'Bearer '+key,'Content-Type':'application/json',Prefer:'return=representation'},body:input.body===undefined?undefined:JSON.stringify(input.body)});
  return forwardBackendResponse(result);
 }catch{return json({error:'Backend authentication or request failed'},401);}
});
