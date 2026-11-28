import fs from 'node:fs';
import path from 'node:path';
import {stripeConfig} from '../../server/membership.mjs';
import {validateArtifact} from '../../server/domain.mjs';
import {optimize} from '../../server/optimizer.mjs';
// Run with the intended deployment environment. Secret values are never printed.
const root=path.resolve(process.argv[2]||'private-artifacts');
const checks=[];
async function check(name,fn){try{await fn();checks.push({name,ready:true});}catch(e){checks.push({name,ready:false,reason:e.code==='ENOENT'?'Required private artifact is missing.':e.message});}}
const read=p=>JSON.parse(fs.readFileSync(path.join(root,p),'utf8'));
await check('Verified email delivery',()=>{if(process.env.AUTH_EMAIL_READY!=='true')throw Error('Email sender, template and delivery must be verified.');});
await check('Current-plan Stripe configuration',()=>{const c=stripeConfig();if(c.prices.some(p=>!['monthly5_99usd','yearly60usd'].includes(p)))throw Error('Legacy or unapproved plans are configured.');if(!['monthly5_99usd','yearly60usd'].every(p=>c.prices.includes(p)))throw Error('Both current monthly and annual plans must be configured.');});
await check('Published NBA projections',()=>validateArtifact(read('nba/basic.json'),{kind:'projections',sport:'NBA'}));
await check('Published NBA distributions',()=>{const a=validateArtifact(read('nba/distributions.json'),{kind:'distributions',sport:'NBA'});if(a.draws!==10000)throw Error('10,000 established-model outcomes are required.');});
for(const sport of ['NBA','NFL'])await check(sport+' current advanced DFS slate',()=>{const catalog=read(sport.toLowerCase()+'/slates.json');const upcoming=(catalog.slates||[]).filter(s=>Date.parse(s.locksAt)>Date.now());if(!upcoming.length)throw Error('No upcoming slate is released.');let ready=false;for(const s of upcoming){if(!/^[-a-zA-Z0-9_]{1,80}$/.test(s.id))continue;try{const a=read(sport.toLowerCase()+'/slates/'+s.id+'.json');if(a.sport!==sport||a.slateId!==s.id)continue;optimize(a,{advanced:true,count:1});ready=true;break;}catch{}}if(!ready)throw Error('No upcoming slate passes model, eligibility, salary, joint-simulation and lineup checks.');});
// These require observed evidence; environment flags cannot stand in for them.
const evidencePath=path.join(root,'release-evidence.json');
let evidence={};try{evidence=JSON.parse(fs.readFileSync(evidencePath,'utf8'));}catch{}
for(const name of ['stripeOriginDelivery','authenticatedFreeAndPaidFlows','mobileAndDesktopReview'])await check(name,()=>{const e=evidence[name];if(!e||e.passed!==true||!e.commit||!e.receipt||!Number.isFinite(Date.parse(e.checkedAt)))throw Error('A dated successful test receipt tied to the release commit is required.');if(e.commit!==process.env.RELEASE_COMMIT)throw Error('Test evidence must match RELEASE_COMMIT.');});
console.log(JSON.stringify({ready:checks.every(c=>c.ready),checks},null,2));
process.exitCode=checks.every(c=>c.ready)?0:1;
