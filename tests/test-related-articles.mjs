import {test} from 'node:test';
import assert from 'node:assert/strict';
import {relatedArticles} from '../scripts/related-articles.mjs';
const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
const p={name:'Colston Loveland',slug:'colston-loveland'};
const a=(title,date,type='mentioned',url='https://rosterxreport.substack.com/p/'+title)=>({title,date,url,players:{[p.name]:type}});
test('featured articles outrank passing mentions; dates order ties; maximum three',()=>{
 const html=relatedArticles(p,[a('mention','2026-10-25'),a('older','2026-10-20','featured'),a('newer','2026-10-22','featured'),a('extra','2026-10-19')],esc);
 assert.ok(html.indexOf('newer</a>')<html.indexOf('older</a>'));
 assert.ok(html.indexOf('older</a>')<html.indexOf('mention</a>'));
 assert.equal((html.match(/<li>/g)||[]).length,3);
 assert.ok(html.includes('utm_content=colston-loveland'));
});
test('no matches and untrusted URLs produce no section',()=>{
 assert.equal(relatedArticles({name:'Other'},[a('article','2026-10-22')],esc),'');
 assert.equal(relatedArticles(p,[a('bad','2026-10-22','featured','https://example.com/p/bad')],esc),'');
});
