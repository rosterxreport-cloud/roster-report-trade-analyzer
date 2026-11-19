export const backendIdentity={owner:'the-roster-report',ownerId:'team_i1lZgAiJDqwdDqFDZ97qajZC',project:'roster-report-trade-analyzer',projectId:'prj_Yh4nqosEYTcKKgJmnXoVEVN16YR7',environment:'preview'};
export function trustedDeployment(p){const a=backendIdentity;return p.owner===a.owner&&p.owner_id===a.ownerId&&p.project===a.project&&p.project_id===a.projectId&&p.environment===a.environment&&p.sub===`owner:${a.owner}:project:${a.project}:environment:${a.environment}`;}
export function allowedBackendPath(path,method){
 if(typeof path!=='string'||path.length>4096||/[\r\n#]/.test(path))return false;
 const base=path.split('?')[0];
 if(method==='POST'&&/^rpc\/pro_(rate_limit|save_free|lease|set_entitlement|session_active)$/.test(base))return true;
 if(method==='GET'&&['pro_entitlements','pro_usage','pro_stripe_events'].includes(base))return true;
 if(method==='POST'&&base==='pro_stripe_events')return true;
 return method==='DELETE'&&base==='pro_sync_lease';
}
