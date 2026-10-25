import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
const root=path.resolve(import.meta.dirname,'..');
execFileSync(process.execPath,['scripts/build-seo.mjs'],{cwd:root});
const out=path.join(root,'dist'),read=p=>fs.readFileSync(path.join(out,p),'utf8');
const walk=d=>fs.readdirSync(d,{withFileTypes:true}).flatMap(e=>e.isDirectory()?walk(path.join(d,e.name)):[path.join(d,e.name)]);
const html=walk(out).filter(p=>p.endsWith('.html')&&!p.endsWith('/404.html'));
test('all canonical pages have unique metadata, one H1 and valid JSON-LD',()=>{
 const titles=new Set(),canonicals=new Set();
 for(const p of html){const s=fs.readFileSync(p,'utf8');const title=s.match(/<title>(.*?)<\/title>/)[1];assert(!titles.has(title),title);titles.add(title);
 const canonical=[...s.matchAll(/<link rel="canonical" href="([^"]+)"/g)];assert.equal(canonical.length,1,p);assert(!canonicals.has(canonical[0][1]),p);canonicals.add(canonical[0][1]);
 assert.equal([...s.matchAll(/<h1[ >]/g)].length,1,p);assert.match(s,/<meta name="description" content="[^"]+"/);assert.match(s,/<meta property="og:image"/);
 for(const m of s.matchAll(/<script type="application\/ld\+json">(.*?)<\/script>/gs))assert.equal(JSON.parse(m[1])['@context'],'https://schema.org');
 }
 assert.equal(html.length,270);
 const sitemap=read('sitemap.xml');for(const c of canonicals)assert(sitemap.includes(`<loc>${c}</loc>`),c);
});
test('every internal link and asset resolves to a real build output',()=>{
 for(const p of html){const s=fs.readFileSync(p,'utf8');for(const m of s.matchAll(/(?:href|src)="([^"]+)"/g)){
  const href=m[1];if(/^(https?:|#|mailto:)/.test(href))continue;
  const u=new URL(href,'https://www.rosterreport.app/'+path.relative(out,p));if(u.pathname.startsWith('/_vercel/'))continue;
  let target=path.join(out,decodeURIComponent(u.pathname));if(fs.existsSync(target)&&fs.statSync(target).isDirectory())target=path.join(target,'index.html');assert(fs.existsSync(target),`${p}: ${href}`);
 }}
});
test('data, calculations and interactive engine are copied byte-for-byte',()=>{
 for(const p of ['players.json','scoring-profiles.json','injury-adjustments.json','app.js','injury-layer.js','scoring-settings.js','team-needs.js','projections/model.mjs','projections/projections.mjs','data/weekly-projections.json'])assert.deepEqual(fs.readFileSync(path.join(out,p)),fs.readFileSync(path.join(root,p)),p);
});
test('published rows exist without JavaScript and every projected player is discoverable',()=>{
 const data=JSON.parse(read('data/weekly-projections.json'));
 for(const pos of ['QB','RB','WR','TE']){const s=read(`projections/${pos.toLowerCase()}/index.html`);for(const player of data.players.filter(p=>p.Position===pos))assert(s.includes(player.Player.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;')),player.Player);}
 assert.equal((read('index.html').match(/<th scope="row">/g)||[]).length,317);
 assert.equal((read('projections/index.html').match(/<th scope="row">/g)||[]).length,30);
});
test('build is deterministic and neither rewrites published inputs nor runs models',()=>{
 const before=new Map(walk(out).map(p=>[path.relative(out,p),fs.readFileSync(p)]));execFileSync(process.execPath,['scripts/build-seo.mjs'],{cwd:root});for(const [p,b]of before)assert.deepEqual(fs.readFileSync(path.join(out,p)),b,p);
});
test('slash normalization and robots rules preserve crawl resources',()=>{
 const cfg=JSON.parse(fs.readFileSync(path.join(root,'vercel.json')));assert.equal(cfg.trailingSlash,true);assert.equal(cfg.outputDirectory,'dist');assert(!read('robots.txt').includes('Disallow: /'));assert.match(read('robots.txt'),/Sitemap: https:\/\/www.rosterreport.app\/sitemap.xml/);
});

