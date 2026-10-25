/** Real source-linked images only. URLs do not establish image reuse permission. */
const HEADSHOT_HOSTS=new Set(['static.www.nfl.com','static.clubs.nfl.com','a.espncdn.com']);
export function safeHeadshotUrl(value){
 if(typeof value!=='string')return null;
 try{const u=new URL(value);return u.protocol==='https:'&&HEADSHOT_HOSTS.has(u.hostname)&&!u.username&&!u.password&&!u.port&&u.pathname!=='/'?u.href:null;}catch{return null;}
}
// Ask the existing NFL image CDN to limit resolution without cropping the photo.
export function sizedHeadshotUrl(value,width){
 const url=safeHeadshotUrl(value);if(!url)return null;
 const u=new URL(url);
 if(!Number.isInteger(width)||width<16||width>640)throw Error('Invalid headshot width');
 if(['static.www.nfl.com','static.clubs.nfl.com'].includes(u.hostname)&&/^\/image\/(upload|private)\//.test(u.pathname))u.pathname=u.pathname.replace(/^\/image\/(upload|private)\//,`/image/$1/w_${width},c_limit/`);
 return u.href;
}
// URLs verified against ESPN's official teams endpoint on 2026-10-25:
// https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams
const TEAMS=new Set('ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LV LAC LAR MIA MIN NE NO NYG NYJ PHI PIT SF SEA TB TEN WAS'.split(' '));
export function teamLogoUrl(team){
 const code=String(team||'').toUpperCase();if(!TEAMS.has(code))return null;
 return `https://a.espncdn.com/i/teamlogos/nfl/500/${code==='WAS'?'wsh':code.toLowerCase()}.png`;
}
export function portrait(p,esc,{small=false}={}){
 const photo=safeHeadshotUrl(p.headshotUrl),logo=teamLogoUrl(p.team),src=photo?sizedHeadshotUrl(photo,small?112:320):logo;
 const alt=small?'':photo?`${p.name} headshot`:`${p.team} team logo`;
 return `<span class="player-portrait${small?' player-portrait-small':''}" data-player-portrait${small?' aria-hidden="true"':''}><span class="portrait-badge" ${src?'hidden ':''}aria-label="${esc(p.team||p.position)} team badge">${esc(p.team||p.position)}</span>${src?`<img data-player-image data-image-kind="${photo?'headshot':'team'}" data-team="${esc(p.team)}"${photo&&logo?` data-fallback-src="${esc(logo)}"`:''} src="${esc(src)}" alt="${esc(alt)}" width="${small?56:160}" height="${small?56:160}" loading="${small?'lazy':'eager'}" decoding="async"${small?'':' fetchpriority="high"'} referrerpolicy="no-referrer">`:''}</span>`;
}
export const imageCss=`.player-hero{display:flex;align-items:center;gap:20px;margin:20px 0}.player-hero .lede{margin:0}.player-portrait{display:inline-flex;position:relative;flex:none;align-items:center;justify-content:center;width:160px;height:160px;border:1px solid #46556a;border-radius:12px;background:#10283d;overflow:hidden}.player-portrait img{display:block;width:100%;height:100%;object-fit:contain}.player-portrait-small{width:56px;height:56px;border-radius:8px}.portrait-badge{font-size:1.4rem;font-weight:800;color:#f9d84a}.portrait-badge[hidden],.player-portrait img[hidden]{display:none}.player-directory a{display:flex;align-items:center;gap:12px}.player-directory .portrait-badge{font-size:.9rem}.image-credit{font-size:.78rem;color:#b8c7d9;margin-top:6px}@media(max-width:480px){.player-portrait:not(.player-portrait-small){width:112px;height:112px}.player-hero{gap:14px}}`;
export const imageClient=`for(const img of document.querySelectorAll('[data-player-image]')){
 const holder=img.closest('[data-player-portrait]');
 let team=img.dataset.imageKind==='team';
 const credit=holder.closest('.player-hero')?.querySelector('[data-image-credit]');
 const fail=()=>{if(!team&&img.dataset.fallbackSrc){team=true;img.dataset.imageKind='team';img.alt=img.dataset.team+' team logo';if(credit)credit.textContent='Team logo: ESPN';img.src=img.dataset.fallbackSrc;}else{img.hidden=true;if(credit)credit.textContent='Team badge';const badge=holder.querySelector('.portrait-badge');if(badge)badge.hidden=false;}};
 img.addEventListener('error',fail);
 if(img.complete&&!img.naturalWidth)fail();
}`;
