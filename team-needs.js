// Recommendations use model lineup value, not projected points or trade acceptance odds.
function analyzeTeamNeeds(profile,database){
  if(!profile?.roster.length)return {message:'Add your roster in My Team to see position needs and trade targets.'};
  const byName=new Map(database.map(p=>[p.name,p]));
  const missing=profile.roster.filter(n=>!byName.has(n));
  if(missing.length)return {message:`Recommendations need matching player data. These saved players are outside the Top 250: ${missing.join(', ')}.`};
  const roster=profile.roster.map(n=>byName.get(n));
  const before=optimalLineup(roster,profile.slots);
  // Allocate the available pool across league-wide starting slots, restricted first.
  const leagueSlots=Object.fromEntries(Object.entries(profile.slots).map(([s,n])=>[s,n*profile.leagueSize]));
  const league=optimalLineup(database,leagueSlots);
  const needs=Object.entries(profile.slots).filter(([,n])=>n>0).map(([slot,count])=>{
    const actual=before.lineup.filter(x=>x.slot===slot);
    const reference=league.lineup.filter(x=>x.slot===slot);
    const covered=reference.length>0&&reference.every(x=>x.player);
    const benchmark=covered?reference.reduce((s,x)=>s+x.player.value,0)/reference.length:null;
    const value=actual.reduce((s,x)=>s+(x.player?.value||0),0)/count;
    return {slot,count,value,benchmark,gap:benchmark===null?null:Math.max(0,benchmark-value),empty:actual.filter(x=>!x.player).length};
  }).sort((a,b)=>b.empty-a.empty||(b.gap??-1)-(a.gap??-1)||a.slot.localeCompare(b.slot));
  const depth=['QB','RB','WR','TE'].filter(pos=>
    (profile.slots[pos]>0||before.lineup.some(x=>x.player?.pos===pos))&&!before.bench.some(p=>p.pos===pos));
  const priority=needs.find(n=>n.empty||n.gap>0);
  const capacity=Object.values(profile.slots).reduce((a,b)=>a+b,0)+profile.bench;
  const incomplete=before.empty>0;
  const overCapacity=roster.length>capacity;
  const targets=[];
  if(priority){
    const eligible=FLEX_ELIGIBILITY[priority.slot]||[priority.slot];
    const candidates=database.filter(p=>!byRoster(p)&&eligible.includes(p.pos)).map(p=>{
      const after=optimalLineup([...roster,p],profile.slots);
      return {player:p,gain:after.total-before.total};
    }).filter(x=>x.gain>.05).sort((a,b)=>a.player.value-b.player.value||a.player.rank-b.player.rank);
    // Show lower, middle and upper value options among actual lineup upgrades.
    const picks=[0,Math.floor((candidates.length-1)/2),candidates.length-1];
    for(const i of [...new Set(picks)]){
      const target=candidates[i];if(!target)continue;
      let offer=null;
      if(!incomplete&&!overCapacity){
        const incoming=sideValue([target.player]).adjusted;
        const packages=roster.map(p=>[p]);
        for(let a=0;a<roster.length;a++)for(let b=a+1;b<roster.length;b++)packages.push([roster[a],roster[b]]);
        for(const outgoing of packages){
          const cost=sideValue(outgoing).adjusted;
          const edge=(incoming-cost)/Math.max(cost,1)*100;
          if(Math.abs(edge)>=4)continue;
          const names=new Set(outgoing.map(p=>p.name));
          const after=optimalLineup([...roster.filter(p=>!names.has(p.name)),target.player],profile.slots);
          const gain=after.total-before.total;
          if(after.empty>before.empty||gain<=.05)continue;
          if(!offer||gain>offer.gain+.001||(Math.abs(gain-offer.gain)<.001&&Math.abs(edge)<Math.abs(offer.edge)))offer={outgoing:outgoing.map(p=>p.name),gain,edge};
        }
      }
      targets.push({...target,offer});
    }
  }
  function byRoster(p){return profile.roster.includes(p.name);}
  return {before,needs,depth,priority,targets,incomplete,overCapacity};
}

let needsCacheKey='',needsCache=null;
function renderTeamNeeds(){
  let panel=document.getElementById('teamNeeds');
  if(!panel){
    panel=document.createElement('section');panel.id='teamNeeds';panel.className='team-section';panel.setAttribute('aria-labelledby','teamNeedsTitle');
    document.getElementById('my-team').after(panel);
    panel.addEventListener('click',e=>{
      const button=e.target.closest('button[data-needs-target]');if(!button)return;
      const target=needsCache?.targets?.[Number(button.dataset.needsTarget)];if(!target?.offer)return;
      give=target.offer.outgoing.map(findPlayer).filter(Boolean);get=[findPlayer(target.player.name)].filter(Boolean);
      render();const result=document.getElementById('resultPanel');result.setAttribute('tabindex','-1');result.focus();result.scrollIntoView({behavior:'smooth',block:'start'});
    });
  }
  const key=JSON.stringify([format,team]);
  if(key===needsCacheKey)return;
  needsCacheKey=key;needsCache=analyzeTeamNeeds(team,players());
  const r=needsCache;
  let html='<h2 id="teamNeedsTitle">Team Needs &amp; Trade Targets</h2>';
  if(r.message){panel.innerHTML=html+`<p class="team-note">${escapeHtml(r.message)}</p>`;return;}
  const label=s=>s==='SF'?'Superflex (SF)':s;
  html+=`<p class="team-note">Based on your saved ${team.leagueSize}-team league and ${format==='half'?'Half PPR':format==='ppr'?'Full PPR':'Standard'} settings. Gains measure model lineup value, not projected fantasy points.</p>`;
  if(r.incomplete)html+='<p class="team-note">Your entered roster leaves starting slots empty. Fill those slots or finish entering your roster first. Targets are provisional; trade packages are withheld.</p>';
  if(r.overCapacity)html+='<p class="team-note">Your entered roster exceeds your saved roster limit. Resolve this before considering trade packages.</p>';
  html+=r.priority?`<h3>Priority: ${escapeHtml(label(r.priority.slot))}</h3><p class="team-note">${r.priority.empty?'Fill an empty starting slot.':'This slot group has the largest average shortfall against the modeled league starter benchmark.'} Eligible targets: ${escapeHtml((FLEX_ELIGIBILITY[r.priority.slot]||[r.priority.slot]).join(', '))}.</p>`:'<h3>No starting-position shortfall detected</h3><p class="team-note">Covered slot groups meet the modeled starter benchmark. Review depth and any groups with unavailable benchmarks.</p>';
  html+=`<div class="needs-table-wrap"><table class="fit-table"><caption>Starting-slot strength</caption><thead><tr><th scope="col">Slot</th><th scope="col">Your average</th><th scope="col">Benchmark</th><th scope="col">Gap</th></tr></thead><tbody>${r.needs.map(n=>`<tr><th scope="row">${escapeHtml(label(n.slot))}</th><td>${n.value.toFixed(1)}</td><td>${n.benchmark===null?'Unavailable':n.benchmark.toFixed(1)}</td><td>${n.gap===null?'—':n.gap.toFixed(1)}</td></tr>`).join('')}</tbody></table></div>`;
  html+='<p class="team-note">Benchmarks average model values after allocating the Top 250 across league-wide starting slots, then FLEX and SF. Unavailable means the database cannot fill that slot group across the league. These are estimates; opponents’ rosters are not imported.</p>';
  html+=`<h3>Depth</h3><p class="team-note">${r.depth.length?`No bench backup at ${escapeHtml(r.depth.join(', '))}. Review these positions before offering depth in a trade.`:'Your used QB/RB/WR/TE positions each have at least one bench backup.'}</p>`;
  if(r.priority)html+='<h3>Trade targets</h3><p class="team-note">Lower, middle and upper value options that improve your best lineup. The add-only gain assumes no outgoing player; a package gain includes every outgoing player. Availability and the other manager’s willingness to trade are unknown.</p>';
  html+=`<div class="needs-targets">${r.targets.map((t,i)=>`<article class="needs-target"><h4>${escapeHtml(t.player.name)} · ${escapeHtml(t.player.pos)}</h4><p>Model value ${t.player.value.toFixed(1)} · Add-only lineup gain +${t.gain.toFixed(1)}</p>${t.offer?`<p>Possible offer: ${t.offer.outgoing.map(escapeHtml).join(' + ')}</p><p><b>Net lineup gain +${t.offer.gain.toFixed(1)}</b> · FAIR TRADE (${Math.abs(t.offer.edge).toFixed(1)}% difference)</p><button class="team-action" type="button" data-needs-target="${i}">Evaluate trade for ${escapeHtml(t.player.name)}</button>`:'<p class="team-note">No verified package suggested. Packages require a complete starting lineup and a one- or two-player offer within the existing fair-trade band that improves your whole lineup without adding an empty slot.</p>'}</article>`).join('')}</div>`;
  if(r.priority&&!r.targets.length)html+='<p class="team-note">No eligible upgrades found in the current Top 250 database.</p>';
  html+='<p class="team-note">Recommendations do not change your saved roster or send offers. Suggested packages use the existing trade engine, including applicable acquisition premiums. Review the full trade and any loss of bench depth before acting.</p>';
  panel.innerHTML=html;
}

