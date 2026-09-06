let DB = null;
let format = "half";
let give = [];
let get = [];

const $ = (id) => document.getElementById(id);
const escapeHtml = (s) => String(s).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));

async function init(){
  const source = await fetch("players.json").then(r=>r.json());
  DB = Object.fromEntries(Object.entries(source).map(([scoring, list])=>[scoring, applyRbPremium(list)]));
  initTeam();
  bind();
  render();
}

function players(){ return applyLeagueScarcity(DB[format],team); }
function findPlayer(name){ return players().find(p=>p.name===name); }

function applyLeagueScarcity(list,profile){
  const sf=profile?.slots?.SF||0;
  if(!sf)return list;
  // A configurable model premium, not an external Superflex market ranking.
  // Always derive from DB's pre-Superflex values so saves and scoring changes
  // cannot compound the adjustment or mutate the workbook player records.
  const demand=Math.min(32,profile.leagueSize*((profile.slots.QB||0)+sf));
  const starterPremium=Math.min(.40,.20*profile.leagueSize*sf/12);
  const qbs=[...list].filter(p=>p.pos==='QB').sort((a,b)=>b.value-a.value||a.rank-b.rank);
  const ranks=new Map(qbs.map((p,i)=>[p.name,i+1]));
  return list.map(p=>{
    const sfPremium=p.pos==='QB'?starterPremium*Math.min(1,demand/ranks.get(p.name)):0;
    return {...p,sfPremium,value:p.pos==='QB'?Math.round(p.value*(1+sfPremium)*100)/100:p.value};
  }).sort((a,b)=>b.value-a.value||a.rank-b.rank).map((p,i)=>({...p,rank:i+1}));
}

function bind(){
  document.querySelectorAll(".format-btn").forEach(btn=>{
    btn.addEventListener("click", ()=>{
      format=btn.dataset.format;
      // Rehydrate selected player records using the chosen scoring format.
      give=give.map(p=>findPlayer(p.name)).filter(Boolean);
      get=get.map(p=>findPlayer(p.name)).filter(Boolean);
      if(team){team.scoring=format;saveTeam();}
      render();
    })
  });
  setupSearch("giveSearch","giveSuggestions","give");
  setupSearch("getSearch","getSuggestions","get");
  document.addEventListener("click",(e)=>{
    if(!e.target.closest(".search-wrap")) document.querySelectorAll(".suggestions").forEach(x=>x.style.display="none");
  });
}

function setupSearch(inputId, suggestionsId, side){
  const input=$(inputId), box=$(suggestionsId);
  const refresh=()=>{
    const q=input.value.trim().toLowerCase();
    const selected = side==="give" ? give : get;
    const other = side==="give" ? get : give;
    const names = new Set([...selected,...other].map(p=>p.name));
    let matches=players().filter(p=>!names.has(p.name) && (!q || `${p.name} ${p.team} ${p.pos}`.toLowerCase().includes(q))).slice(0,10);
    if(!matches.length){box.innerHTML='<div class="suggestion"><span>No matches</span></div>';box.style.display="block";return;}
    box.innerHTML=matches.map(p=>`<div class="suggestion" data-name="${escapeHtml(p.name)}">
       <span><b>${escapeHtml(p.name)}</b><span class="meta"> &nbsp;${p.pos} • ${p.team}</span></span>
       <span class="meta">#${p.rank} • ${p.value.toFixed(1)}</span>
    </div>`).join("");
    box.style.display="block";
    box.querySelectorAll(".suggestion[data-name]").forEach(row=>row.addEventListener("click",()=>{
      const p=findPlayer(row.dataset.name);
      if(side==="give") give.push(p); else get.push(p);
      input.value=""; box.style.display="none"; render();
    }));
  };
  input.addEventListener("input",refresh);
  input.addEventListener("focus",refresh);
  input.addEventListener("keydown",(e)=>{
    if(e.key==="Enter"){
      const first=box.querySelector(".suggestion[data-name]");
      if(first){e.preventDefault();first.click();}
    }
  });
}

function remove(side,index){
  if(side==="give") give.splice(index,1); else get.splice(index,1);
  render();
}
window.removePlayer=remove;

function renderSide(side,list){
  $(side+"Count").textContent=list.length;
  const el=$(side+"Players");
  if(!list.length){el.innerHTML='<div class="empty-state">Add one or more players</div>';return;}
  el.innerHTML=list.map((p,i)=>`<div class="player-row">
    <div class="player-rank">#${p.rank}</div>
    <div><div class="player-name">${escapeHtml(p.name)}</div><div class="player-meta">${p.pos} • ${p.team} • ${p.rookie?"ROOKIE • ":""}AW #${p.awRank}</div></div>
    <div class="player-value">${p.value.toFixed(1)}</div>
    <button class="remove-btn" onclick="removePlayer('${side}',${i})" aria-label="Remove ${escapeHtml(p.name)}">×</button>
  </div>`).join("");
}

function sideValue(list){
  if(!list.length) return {adjusted:0,raw:0,top:null};
  const sorted=[...list].sort((a,b)=>b.value-a.value);
  const raw=sorted.reduce((s,p)=>s+p.value,0);
  const top=sorted[0];
  let eliteMult = top.value>=95 ? 1.05 : top.value>=90 ? 1.03 : top.value>=85 ? 1.015 : 1;
  let adjusted=top.value*eliteMult;
  const multipliers=[0,.70,.45,.30,.20,.15,.12,.10];
  for(let i=1;i<sorted.length;i++){
    const marginal=Math.max(0,sorted[i].value-50);
    const m=multipliers[Math.min(i,multipliers.length-1)];
    adjusted += marginal*m;
  }
  return {adjusted,raw,top,eliteMult};
}

function result(){
  if(!give.length || !get.length) return null;
  const a=sideValue(give), b=sideValue(get);
  const edge=(b.adjusted-a.adjusted)/Math.max(a.adjusted,1)*100;
  let verdict = edge >= 4 ? "ACCEPT" : edge <= -4 ? "REJECT" : "FAIR TRADE";
  let cls = edge >= 4 ? "accept" : edge <= -4 ? "reject" : "fair";
  const abs=Math.abs(edge);
  let explanation;
  if(verdict==="ACCEPT") explanation=`The model prefers what you receive by ${abs.toFixed(1)}%.`;
  else if(verdict==="REJECT") explanation=`The model prefers what you give away by ${abs.toFixed(1)}%.`;
  else explanation=`The adjusted values are within ${abs.toFixed(1)}%, which falls inside the model's fair-trade band.`;
  if((give.length>1 || get.length>1)){
    explanation += " Package players are discounted against replacement level, while elite one-player assets receive a modest consolidation premium.";
  }
  return {a,b,edge,verdict,cls,explanation};
}

function renderResult(){
  const r=result(), panel=$("resultPanel");
  if(!r){panel.innerHTML='<div class="result-placeholder"><span class="pixel-ball">◆</span>Add players to both sides to analyze the trade.</div>';return;}
  const direction=r.edge>0?"INCOMING SIDE":"OUTGOING SIDE";
  panel.innerHTML=`<div class="result-card">
    <div class="result-top">
      <div>
        <div class="kicker">MODEL VERDICT • ${format==="half"?"HALF PPR":format==="ppr"?"FULL PPR":"STANDARD"}</div>
        <div class="verdict ${r.cls}">${r.verdict}</div>
        <div class="result-sub">${r.explanation}</div>
      </div>
      <div class="edge-box">
        <div class="edge-num">${Math.abs(r.edge).toFixed(1)}%</div>
        <div class="edge-label">${Math.abs(r.edge)<4?"Value difference":direction+" edge"}</div>
      </div>
    </div>
    <div class="score-grid">
      <div class="side-score">
        <div class="score-label">I GIVE • ADJUSTED VALUE</div>
        <div class="score-num">${r.a.adjusted.toFixed(1)}</div>
        <div class="raw">Raw player-value sum: ${r.a.raw.toFixed(1)}</div>
      </div>
      <div class="side-score">
        <div class="score-label">I GET • ADJUSTED VALUE</div>
        <div class="score-num">${r.b.adjusted.toFixed(1)}</div>
        <div class="raw">Raw player-value sum: ${r.b.raw.toFixed(1)}</div>
      </div>
    </div>
    <div class="analysis-strip">
      Best asset: <b>${escapeHtml((r.a.top.value>=r.b.top.value?r.a.top:r.b.top).name)}</b>. 
      The analyzer values starters over bench accumulation by counting the best player at full value, then applying diminishing marginal value to additional pieces above a replacement-level baseline.
    </div>
  </div>`;
}

function render(){
  document.querySelectorAll(".format-btn").forEach(btn=>{
    const active=btn.dataset.format===format;
    btn.classList.toggle("active",active);
    btn.setAttribute("aria-pressed",String(active));
  });
  renderSide("give",give);
  renderSide("get",get);
  renderResult();
  renderRankings();
  renderTeam();
}

function applyRbPremium(list){
  // Use the unadjusted model order, not the source AW positional rank.
  // Retain base values so reapplying this transformation never compounds it.
  const baseValue=p=>p.baseValue ?? p.value;
  const baseRank=p=>p.baseRank ?? p.rank;
  const backs=[...list].filter(p=>p.pos==="RB")
    .sort((a,b)=>baseValue(b)-baseValue(a) || baseRank(a)-baseRank(b));
  const rbRanks=new Map(backs.map((p,i)=>[p.name,i+1]));
  return list.map(p=>{
    const rbRank=rbRanks.get(p.name);
    const rbPremium=p.pos==="RB" ? (rbRank<=12 ? .03 : rbRank<=24 ? .015 : 0) : 0;
    return {...p, baseValue:baseValue(p), baseRank:baseRank(p), rbPremium,
      value:Math.round(baseValue(p)*(1+rbPremium)*100)/100};
  }).sort((a,b)=>b.value-a.value || a.baseRank-b.baseRank)
    .map((p,i)=>({...p,rank:i+1}));
}

function renderRankings(){
  const label=format==="half"?"Half PPR":format==="ppr"?"Full PPR":"Standard";
  $("rankingsCaption").textContent=`${label} • Top 250 Redraft Rankings`;
  $("rankingsRows").innerHTML=[...players()].sort((a,b)=>a.rank-b.rank).map(p=>`<tr>
    <td>${p.rank}</td><th scope="row">${escapeHtml(p.name)}</th><td>${escapeHtml(p.pos)}</td><td>${escapeHtml(p.team)}</td><td>${p.value.toFixed(1)}</td>
  </tr>`).join("");
}

const TEAM_KEY="roster-report-team-v1";
const SLOT_DEFAULTS={QB:1,RB:2,WR:2,TE:1,FLEX:1,SF:0,K:0,DST:0};
const FLEX_ELIGIBILITY={FLEX:['RB','WR','TE'],SF:['QB','RB','WR','TE']};
let team=null,teamNotice="";
function normalizeTeam(value){
  if(!value || value.version!==1 || !Array.isArray(value.roster))return null;
  const bounded=(n,min,max,fallback)=>Number.isInteger(n)&&n>=min&&n<=max?n:fallback;
  return {version:1,leagueSize:bounded(value.leagueSize,4,32,12),scoring:['half','ppr','standard'].includes(value.scoring)?value.scoring:'half',
    bench:bounded(value.bench,0,20,6),slots:Object.fromEntries(Object.entries(SLOT_DEFAULTS).map(([pos,n])=>[pos,bounded(value.slots?.[pos],0,6,n)])),
    roster:[...new Set(value.roster.filter(n=>typeof n==='string'&&n.length>0&&n.length<=100))].slice(0,60)};
}
function saveTeam(){
  try{localStorage.setItem(TEAM_KEY,JSON.stringify(team));teamNotice="Saved on this browser.";}
  catch{teamNotice="Browser storage is unavailable. Your team works for this visit but cannot be saved.";}
}
function optimalLineup(roster,slots){
  const pool=[...roster].sort((a,b)=>b.value-a.value||a.rank-b.rank),used=new Set(),lineup=[];
  // Fill restricted positions, then FLEX, then the broader Superflex slot.
  for(const pos of [...Object.keys(SLOT_DEFAULTS).filter(p=>!FLEX_ELIGIBILITY[p]),'FLEX','SF']){
    for(let i=0;i<(slots[pos]||0);i++){
      const p=pool.find(p=>!used.has(p.name)&&(FLEX_ELIGIBILITY[pos]?FLEX_ELIGIBILITY[pos].includes(p.pos):p.pos===pos));
      if(p)used.add(p.name);
      lineup.push({slot:pos,player:p||null});
    }
  }
  return {lineup,total:lineup.reduce((s,x)=>s+(x.player?.value||0),0),bench:pool.filter(p=>!used.has(p.name)),empty:lineup.filter(x=>!x.player).length};
}
function teamComparison(profile,outgoing,incoming,database){
  const byName=new Map(database.map(p=>[p.name,p]));
  const missing=profile.roster.filter(n=>!byName.has(n));
  if(missing.length)return {error:`These saved players are outside the current player database: ${missing.join(', ')}. Remove them to analyze the available roster.`};
  if(outgoing.some(p=>!profile.roster.includes(p.name)))return {error:'Add every outgoing player to My Team before calculating roster fit.'};
  if(incoming.some(p=>profile.roster.includes(p.name)))return {error:'An incoming player is already on My Team. Correct the trade or saved roster.'};
  const beforeRoster=profile.roster.map(n=>byName.get(n));
  const afterRoster=[...beforeRoster.filter(p=>!outgoing.some(x=>x.name===p.name)),...incoming.map(p=>byName.get(p.name)).filter(Boolean)];
  const before=optimalLineup(beforeRoster,profile.slots),after=optimalLineup(afterRoster,profile.slots);
  const delta=after.total-before.total,warnings=[];
  const capacity=Object.values(profile.slots).reduce((a,b)=>a+b,0)+profile.bench;
  if(afterRoster.length>capacity)warnings.push(`The trade leaves ${afterRoster.length-capacity} player(s) over your roster limit. Choose drops before relying on this comparison; no drops are assumed.`);
  if(after.empty)warnings.push(`${after.empty} starting slot(s) would be empty after the trade. No waiver replacements are assumed.`);
  if(before.empty)warnings.push(`Your saved roster currently leaves ${before.empty} starting slot(s) empty. Add your full roster for a complete comparison.`);
  for(const pos of ['QB','RB','WR','TE']){
    if(!profile.slots[pos]&&!after.lineup.some(x=>x.player?.pos===pos))continue;
    const reserves=after.bench.filter(p=>p.pos===pos).length;
    if(!reserves)warnings.push(`No ${pos} backup remains${profile.leagueSize>=14?` in your ${profile.leagueSize}-team league; review replacement availability carefully`:''}.`);
  }
  const verdict=afterRoster.length>capacity?'Choose roster drops first':after.empty>before.empty?'Creates a lineup hole':delta>0.05?'Improves your starting lineup':delta<-.05?'Weakens your starting lineup':'Starting lineup stays level';
  return {before,after,delta,warnings,verdict};
}
function initTeam(){
  try{const saved=localStorage.getItem(TEAM_KEY);if(saved){team=normalizeTeam(JSON.parse(saved));teamNotice=team?'Saved team restored.':'Saved team settings were invalid. Set up your team again.';}}
  catch{teamNotice='Saved team could not be loaded. You can still use My Team for this visit.';}
  if(team)format=team.scoring;
  const style=document.createElement('style');
  style.textContent=`.team-section{margin-top:28px;padding:22px;border:1px solid var(--line);background:#081a2f}.team-section h2{margin:0 0 10px}.team-settings{display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:12px;margin:18px 0}.team-settings label{display:grid;gap:6px;font-size:14px;color:#c6d8e9}.team-section select{width:100%;padding:12px;background:#04111f;border:2px solid #2a5276;color:white;font-size:16px}.team-action{padding:11px 14px;background:var(--yellow);border:0;color:var(--navy);font-weight:800;cursor:pointer}.team-action:focus-visible,.team-section select:focus-visible{outline:2px solid white;outline-offset:3px}.team-add{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}.team-add input{flex:1;min-width:180px}.team-roster{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}.team-chip{padding:9px;background:#0b2743;border:1px solid var(--line);color:var(--cream);cursor:pointer;font-size:14px}.team-note{font-size:14px;line-height:1.6;color:#b8cce0}.fit-table{width:100%;border-collapse:collapse;font-size:14px}.fit-table th,.fit-table td{padding:10px;text-align:left;border-bottom:1px solid var(--line)}.team-fit{margin-top:24px}.team-fit li{margin:8px 0}.team-fit h3{color:var(--yellow)}@media(max-width:500px){.team-section{padding:16px}.fit-table th,.fit-table td{padding:7px 4px;font-size:13px}}`;
  document.head.appendChild(style);
  const section=document.createElement('section');section.className='team-section';section.id='my-team';section.setAttribute('aria-labelledby','teamTitle');
  section.innerHTML=`<h2 id="teamTitle">My Team</h2><p class="team-note">Save your roster and league settings to see how trades affect your starting lineup and depth. Saved on this browser only; clearing browser data removes your team.</p>
    <form id="teamSettings"><div class="team-settings"><label>League size<input id="teamLeague" type="number" min="4" max="32" value="12" required></label><label>Scoring<select id="teamScoring"><option value="half">Half PPR</option><option value="ppr">Full PPR</option><option value="standard">Standard</option></select></label>
    ${Object.entries(SLOT_DEFAULTS).map(([p,n])=>`<label>${p==='SF'?'Superflex (SF)':p}<input id="slot${p}" type="number" min="0" max="6" value="${n}" required></label>`).join('')}<label>Bench<input id="teamBench" type="number" min="0" max="20" value="6" required></label></div>
    <p class="team-note">FLEX accepts RB, WR or TE. Superflex (SF) accepts QB, RB, WR or TE. Save with SF above zero to apply increased QB scarcity values throughout the analyzer and rankings. Defaults: 12 teams, 1 QB, 2 RB, 2 WR, 1 TE, 1 FLEX, 0 SF, 6 bench.</p><button class="team-action" type="submit">Save settings</button></form>
    <p id="scarcityStatus" class="team-note" role="status"></p>
    <form class="team-add" id="teamAdd"><input id="rosterSearch" list="rosterOptions" autocomplete="off" placeholder="Search a roster player…" aria-label="Player to add to My Team" required><datalist id="rosterOptions"></datalist><button class="team-action" type="submit">Add player</button></form>
    <p class="team-note">Players are limited to the current Top 250 database. Add your full available roster. Click a saved player to remove them.</p><div id="teamRoster" class="team-roster"></div><p id="teamStatus" class="team-note" role="status"></p>`;
  document.querySelector('.trade-grid').before(section);
  document.querySelector('.section-nav').insertAdjacentHTML('beforeend','<a href="#my-team">My Team</a>');
  const fit=document.createElement('section');fit.id='teamFit';fit.className='team-section team-fit';fit.setAttribute('aria-label','Roster fit analysis');$('resultPanel').after(fit);
  if(team){$('teamLeague').value=team.leagueSize;$('teamBench').value=team.bench;for(const p of Object.keys(SLOT_DEFAULTS))$('slot'+p).value=team.slots[p];}
  $('teamScoring').value=format;
  $('teamSettings').addEventListener('submit',e=>{e.preventDefault();if(!readTeamSettings())return;saveTeam();render();});
  $('teamAdd').addEventListener('submit',e=>{
    e.preventDefault();const name=$('rosterSearch').value.trim(),p=players().find(p=>p.name.toLowerCase()===name.toLowerCase());
    if(!p){$('teamStatus').textContent='Choose a player from the current database.';return;}
    if(!readTeamSettings())return;
    if(team.roster.includes(p.name)){$('teamStatus').textContent='That player is already on your roster.';return;}
    if(team.roster.length>=60){$('teamStatus').textContent='Your saved roster has reached the 60-player limit.';return;}
    team.roster.push(p.name);$('rosterSearch').value='';saveTeam();render();
  });
  $('teamRoster').addEventListener('click',e=>{const button=e.target.closest('button[data-player]');if(!button||!team)return;team.roster=team.roster.filter(n=>n!==button.dataset.player);saveTeam();render();});
}
function readTeamSettings(){
  if(!$('teamSettings').reportValidity())return false;
  const slots=Object.fromEntries(Object.keys(SLOT_DEFAULTS).map(p=>[p,Number($('slot'+p).value)]));
  if(!Object.values(slots).some(n=>n>0)){$('teamStatus').textContent='Choose at least one starting lineup slot.';return false;}
  team=normalizeTeam({version:1,leagueSize:Number($('teamLeague').value),bench:Number($('teamBench').value),scoring:$('teamScoring').value,slots,roster:team?.roster||[]});
  format=team.scoring;give=give.map(p=>findPlayer(p.name)).filter(Boolean);get=get.map(p=>findPlayer(p.name)).filter(Boolean);return true;
}
function renderTeam(){
  if(!$('teamRoster'))return;
  $('teamScoring').value=format;
  $('scarcityStatus').textContent=team?.slots.SF>0
    ? `Superflex enabled: QB scarcity values include a model premium scaled by league size and SF slots (20% for starting-range QBs in a 12-team, 1-SF league, capped at 40%, with smaller premiums for deeper backups). Player positions and scoring rules are unchanged.`
    : 'Superflex disabled: standard player values apply, including the existing RB premium.';
  const names=team?.roster||[];
  $('rosterOptions').innerHTML=players().filter(p=>!names.includes(p.name)).map(p=>`<option value="${escapeHtml(p.name)}">${escapeHtml(p.pos)} • ${escapeHtml(p.team)}</option>`).join('');
  $('teamRoster').innerHTML=names.length?names.map(n=>`<button type="button" class="team-chip" data-player="${escapeHtml(n)}" aria-label="Remove ${escapeHtml(n)} from My Team">${escapeHtml(n)} · ${escapeHtml(findPlayer(n)?.pos||'Unavailable')} ×</button>`).join(''):'<p class="team-note">No players saved yet.</p>';
  $('teamStatus').textContent=teamNotice;
  const target=$('teamFit');
  if(!team||!names.length){target.innerHTML='<h3>Fit for your team</h3><p class="team-note">Save your roster in My Team to add a lineup and depth comparison.</p>';return;}
  if(!give.length||!get.length){target.innerHTML='<h3>Fit for your team</h3><p class="team-note">Add players to both sides of a trade to compare your saved roster before and after.</p>';return;}
  const r=teamComparison(team,give,get,players());
  if(r.error){target.innerHTML=`<h3>Fit for your team</h3><p class="team-note">${escapeHtml(r.error)}</p>`;return;}
  target.innerHTML=`<div class="kicker">FIT FOR YOUR TEAM • ${team.leagueSize}-TEAM LEAGUE</div><h3>${r.verdict}</h3><p>Starting lineup value: <b>${r.before.total.toFixed(1)} → ${r.after.total.toFixed(1)}</b> (${r.delta>=0?'+':''}${r.delta.toFixed(1)})</p>
    <p class="team-note">Uses the highest-value eligible lineup in your saved scoring format. These are v10 model values, not projected fantasy points. The trade-value verdict above remains separate. Trades do not change your saved roster.</p>
    <table class="fit-table"><caption>Best starting lineup before and after</caption><thead><tr><th scope="col">Slot</th><th scope="col">Before</th><th scope="col">After</th></tr></thead><tbody>${r.before.lineup.map((x,i)=>`<tr><th scope="row">${x.slot==='SF'?'Superflex (SF)':x.slot}</th><td>${escapeHtml(x.player?.name||'Empty')}</td><td>${escapeHtml(r.after.lineup[i].player?.name||'Empty')}</td></tr>`).join('')}</tbody></table>
    <p class="team-note">Bench depth: ${r.before.bench.length} → ${r.after.bench.length} players. After trade: ${['QB','RB','WR','TE','K','DST'].map(pos=>`${pos} ${r.after.bench.filter(p=>p.pos===pos).length}`).join(' · ')}.</p>
    ${r.warnings.length?`<ul>${r.warnings.map(w=>`<li>${escapeHtml(w)}</li>`).join('')}</ul>`:''}<p class="team-note">League size provides depth-risk context and scales QB scarcity when Superflex is enabled. Actual waiver availability, byes and injuries are not modeled.</p>`;
}

init().catch(err=>{
  console.error(err);
  document.body.insertAdjacentHTML("beforeend","<p style='padding:20px;color:#ff7171'>Unable to load player data.</p>");
});

