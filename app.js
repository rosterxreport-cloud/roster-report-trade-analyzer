let DB = null;
let format = "half";
let give = [];
let get = [];

const $ = (id) => document.getElementById(id);
const escapeHtml = (s) => String(s).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));

async function init(){
  DB = await fetch("players.json").then(r=>r.json());
  bind();
  render();
}

function players(){ return DB[format]; }
function findPlayer(name){ return players().find(p=>p.name===name); }

function bind(){
  document.querySelectorAll(".format-btn").forEach(btn=>{
    btn.addEventListener("click", ()=>{
      format=btn.dataset.format;
      // Rehydrate selected player records using the chosen scoring format.
      give=give.map(p=>findPlayer(p.name)).filter(Boolean);
      get=get.map(p=>findPlayer(p.name)).filter(Boolean);
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
}

function renderRankings(){
  const label=format==="half"?"Half PPR":format==="ppr"?"Full PPR":"Standard";
  $("rankingsCaption").textContent=`${label} • Top 200 Redraft Rankings`;
  $("rankingsRows").innerHTML=[...players()].sort((a,b)=>a.rank-b.rank).slice(0,200).map(p=>`<tr>
    <td>${p.rank}</td><th scope="row">${escapeHtml(p.name)}</th><td>${escapeHtml(p.pos)}</td><td>${escapeHtml(p.team)}</td><td>${p.value.toFixed(1)}</td>
  </tr>`).join("");
}

init().catch(err=>{
  console.error(err);
  document.body.insertAdjacentHTML("beforeend","<p style='padding:20px;color:#ff7171'>Unable to load player data.</p>");
});
