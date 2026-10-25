import test from 'node:test';
import assert from 'node:assert/strict';
import {safeHeadshotUrl,sizedHeadshotUrl,portrait,teamLogoUrl} from '../scripts/player-images.mjs';
const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;');
const p={name:'Test Player',team:'DET',position:'RB',headshotUrl:'https://static.www.nfl.com/image/upload/f_auto,q_auto/league/example'};
test('untrusted and malformed image URLs never reach image markup',()=>{
 for(const url of ['javascript:alert(1)','data:image/svg+xml,<svg/>','http://static.www.nfl.com/a','https://static.www.nfl.com.evil.test/a','https://user:pass@static.www.nfl.com/a','https://static.www.nfl.com:8443/a','https://evil.test/a',null]){
  assert.equal(safeHeadshotUrl(url),null);
  const html=portrait({...p,headshotUrl:url},esc);assert(!html.includes('data-image-kind="headshot"'));assert(html.includes(teamLogoUrl('DET')));
 }
});
test('main photos have descriptive alt text and reserved space; directory images are lazy and decorative',()=>{
 const main=portrait(p,esc),small=portrait(p,esc,{small:true});
 assert.match(main,/alt="Test Player headshot"/);assert.match(main,/width="160" height="160"/);assert.match(main,/loading="eager"/);assert.match(main,/referrerpolicy="no-referrer"/);assert.match(main,/data-fallback-src="https:\/\/a.espncdn.com/);
 assert.match(small,/loading="lazy"/);assert.match(small,/aria-hidden="true"/);assert.match(small,/alt=""/);
 const absent=portrait({...p,headshotUrl:null,team:'UNKNOWN'},esc);assert(!absent.includes('<img'));assert(absent.includes('UNKNOWN'));
});

test('NFL CDN sizes preserve the source identity and never crop the photo',()=>{
 assert.equal(sizedHeadshotUrl(p.headshotUrl,320),'https://static.www.nfl.com/image/upload/w_320,c_limit/f_auto,q_auto/league/example');
 assert.equal(sizedHeadshotUrl(p.headshotUrl.replace('/upload/','/private/'),112),'https://static.www.nfl.com/image/private/w_112,c_limit/f_auto,q_auto/league/example');
 assert.throws(()=>sizedHeadshotUrl(p.headshotUrl,5000),/Invalid headshot width/);
});
