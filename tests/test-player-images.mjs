import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {teamLogo,teamLogoUrl} from '../scripts/player-images.mjs';
import {renderProfiles} from '../scripts/player-profiles.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;');
test('only allowlisted team logos render, regardless of a player-photo field',()=>{
 const p={name:'Test Player',team:'DET',position:'RB',headshotUrl:'https://static.www.nfl.com/image/upload/player-photo'};
 const html=teamLogo(p,esc);assert(html.includes(teamLogoUrl('DET')));assert(!html.includes('player-photo'));assert.match(html,/alt="DET team logo"/);assert.match(html,/width="112" height="112"/);
 const small=teamLogo(p,esc,{small:true});assert.match(small,/loading="lazy"/);assert.match(small,/aria-hidden="true"/);assert.match(small,/alt=""/);
 for(const team of ['UNKNOWN','javascript:alert(1)','https://evil.test/'])assert(!teamLogo({...p,team},esc).includes('<img'));
 assert.equal(teamLogoUrl('WAS'),'https://a.espncdn.com/i/teamlogos/nfl/500/wsh.png');
});
test('all built player pages and directory use team logos without any headshot URLs or Person images',()=>{
 const pages=[];const release=JSON.parse(fs.readFileSync(path.join(root,'data/player-profiles.json'),'utf8'));
 renderProfiles({release,page:(slug,title,description,body)=>pages.push({slug,body}),esc,write:()=>{},dateLabel:s=>s});
 assert.equal(pages.length,release.profiles.length+1);
 for(const {slug,body:s} of pages){assert(s.includes('data-team-logo-image'),slug);assert(!/headshot|static\.www\.nfl\.com\/image|data-player-image/.test(s),slug);
 for(const m of s.matchAll(/<script type="application\/ld\+json">(.*?)<\/script>/gs)){const d=JSON.parse(m[1]);if(d['@type']==='Person')assert(!d.image);}
 }
});
