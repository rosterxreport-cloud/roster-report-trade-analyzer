/** Team logos only. Player photographs are never rendered or requested. */
// Verified against https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams
const TEAMS=new Set('ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LV LAC LAR MIA MIN NE NO NYG NYJ PHI PIT SF SEA TB TEN WAS'.split(' '));
export function teamLogoUrl(team){
 const raw=String(team||'').toUpperCase(),code=({JAC:'JAX',WSH:'WAS',LA:'LAR',OAK:'LV',SD:'LAC'})[raw]||raw;if(!TEAMS.has(code))return null;
 return `https://a.espncdn.com/i/teamlogos/nfl/500/${code==='WAS'?'wsh':code.toLowerCase()}.png`;
}
export function teamLogo(p,esc,{small=false}={}){
 const src=teamLogoUrl(p.team);
 return `<span class="player-team-logo${small?' player-team-logo-small':''}" data-team-logo${small?' aria-hidden="true"':''}><span class="team-badge" ${src?'hidden ':''}>${esc(p.team||p.position)}</span>${src?`<img data-team-logo-image src="${esc(src)}" alt="${small?'':esc(p.team)+' team logo'}" width="${small?48:112}" height="${small?48:112}" loading="${small?'lazy':'eager'}" decoding="async" referrerpolicy="no-referrer">`:''}</span>`;
}
export const imageCss=`.player-hero{display:flex;align-items:center;gap:20px;margin:20px 0}.player-hero .lede{margin:0}.player-team-logo{display:inline-flex;flex:none;align-items:center;justify-content:center;width:112px;height:112px;border:1px solid #46556a;border-radius:12px;background:#10283d;overflow:hidden}.player-team-logo img{display:block;width:100%;height:100%;object-fit:contain;padding:10px;box-sizing:border-box}.player-team-logo-small{width:48px;height:48px;border-radius:8px}.player-team-logo-small img{padding:4px}.team-badge{font-size:1.2rem;font-weight:800;color:#f9d84a}.team-badge[hidden],.player-team-logo img[hidden]{display:none}.player-directory a{display:flex;align-items:center;gap:12px}.player-team-logo-small .team-badge{font-size:.8rem}@media(max-width:480px){.player-team-logo:not(.player-team-logo-small){width:88px;height:88px}.player-hero{gap:14px}}`;
export const imageClient=`for(const img of document.querySelectorAll('[data-team-logo-image]')){
 const fail=()=>{img.hidden=true;const badge=img.closest('[data-team-logo]').querySelector('.team-badge');if(badge)badge.hidden=false;};
 img.addEventListener('error',fail);
 if(img.complete&&!img.naturalWidth)fail();
}`;
