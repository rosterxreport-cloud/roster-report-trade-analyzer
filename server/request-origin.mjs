// Trust only origins supplied by deployment configuration, never request Host
// or forwarding headers, which are not an application origin allowlist.
export function allowedRequestOrigin(origin,env=process.env){
 if(typeof origin!=='string')return false;
 const configured=[env.APP_ORIGIN,...[env.VERCEL_URL,env.VERCEL_BRANCH_URL].filter(Boolean).map(host=>'https://'+host)];
 return configured.some(value=>{
  try{const u=new URL(value);return u.protocol==='https:'&&!u.username&&!u.password&&u.pathname==='/'&&!u.search&&!u.hash&&origin===u.origin;}
  catch{return false;}
 });
}
