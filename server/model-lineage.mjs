import fs from 'node:fs';
import crypto from 'node:crypto';
const bytes=fs.readFileSync(new URL('../config/nba-incumbent-release.json',import.meta.url));
const nba=JSON.parse(bytes),policyHash=crypto.createHash('sha256').update(bytes).digest('hex');
export const weeklyNFLModelHash='c95ac28e53c2c9550827391269dcaff95127ee8397730b33072bc81d00441d6d';
export function validateModelLineage(model){
 const p=model?.provenance;
 if(model?.sport==='NBA'){
  if(nba.approved!==true||p?.modelHash!==nba.modelFingerprint||p?.model!==nba.model||p?.simulatorHash!==nba.sourceFiles['simulate_slate.py']||p?.releaseAuthorization?.policyHash!==policyHash)throw Error('NBA publication requires the authorized unchanged incumbent model.');
 }else if(model?.sport==='NFL'){
  const verifiedCore=model.scoring==='RR-DK-core'&&p?.coreModelHash==='2354d0e5af4a56784d0418bd392d3cde1942c4f50834be18a06ee9c2502e85b9'&&p?.verifiedGeneratorHash===p?.modelHash&&/^[a-f0-9]{64}$/.test(p?.modelHash||'')&&p?.modelFamily==='established_weekly_structural_v4'&&p?.scoringMethod==='weekly-ppr-plus-interceptions'&&p?.defenseSource==='https://dfsroto.win/projections'&&p?.scoringNote;
  if((p?.modelHash!==weeklyNFLModelHash&&!verifiedCore)||p?.modelUnchanged!==true||!/^data\/projections\/\d{4}_week\d+_league_v4_full\.csv$/.test(p?.weeklySource||'')||!p?.weeklyManifestHash)throw Error('NFL publication requires the established weekly RR model.');
 }else throw Error('Unsupported model lineage.');
}
