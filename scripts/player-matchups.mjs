/** Descriptive matchup evidence. Does not adjust projections or model scores. */
const n=(value)=>Number(value).toFixed(1);
const fields=['attempts','passing_yards','passing_tds','passing_interceptions','sacks_suffered','carries','rushing_yards','rushing_tds','targets','receptions','receiving_yards','receiving_tds','fantasy_points_ppr'];
const valid=row=>row&&Number.isInteger(row.games)&&row.games>=3&&Number.isInteger(row.mostPointsRank)&&row.mostPointsRank>=1&&Number.isInteger(row.rankedDefenses)&&row.rankedDefenses>=row.mostPointsRank&&fields.every(key=>Number.isFinite(row.perGame?.[key])&&Number.isFinite(row.totals?.[key]));
export function matchupAnalysis(p,evidence){
 const q=p.projection;
 if(p.retained)return {unavailable:'This retained profile has no current matchup analysis.'};
 if(p.editorial?.out)return {unavailable:'This player is ruled out for the published forecast week; no playable matchup recommendation is shown.'};
 if(!q?.Opponent)return {unavailable:'No opponent is available in this player’s published weekly forecast. No matchup is inferred.'};
 if(evidence?.schemaVersion!==1||evidence.season!==p.season||evidence.throughWeek!==p.throughWeek||p.projectionWeek!==evidence.throughWeek+1||p.sources?.find(s=>s.file==='player_stats.parquet')?.sha256!==evidence.source?.sha256||!Number.isFinite(q.PPR)||!Number.isFinite(Date.parse(evidence.capturedAt))||!/^https:\/\/github.com\/nflverse\//.test(evidence.source?.url||'')||!/^[a-f0-9]{64}$/.test(evidence.source?.sha256||''))return {unavailable:'Verified matchup statistics are not aligned with this weekly profile snapshot. Matchup claims are withheld until the next validated update.'};
 const row=evidence.positions?.[p.position]?.[q.Opponent];
 if(!valid(row))return {unavailable:'Fewer than three verified defensive games are available for this position. No defensive rank or matchup verdict is assigned.'};
 const g=row.perGame,plural={QB:'quarterbacks',RB:'running backs',WR:'wide receivers',TE:'tight ends'}[p.position];
 const lines=[`${q.Opponent} allows ${n(g.fantasy_points_ppr)} PPR points per game to opposing ${plural}: No. ${row.mostPointsRank} of ${row.rankedDefenses} for most points allowed through Week ${evidence.throughWeek} (${row.games} games).`];
 const ratio=(yards,volume)=>row.totals[volume]>0?n(row.totals[yards]/row.totals[volume]):null;
 if(p.position==='QB'){
  lines.push(`Opposing quarterbacks average ${n(g.passing_yards)} passing yards, ${n(g.passing_tds)} passing touchdowns and ${n(g.passing_interceptions)} interceptions per game against this defense.`);
  const ypa=ratio('passing_yards','attempts');if(ypa)lines.push(`The defense allows ${ypa} yards per pass attempt; opposing quarterbacks take ${n(g.sacks_suffered)} sacks per game.`);
 }else if(p.position==='RB'){
  lines.push(`Opposing backfields average ${n(g.rushing_yards)} rushing yards, ${n(g.receptions)} receptions and ${n(g.receiving_yards)} receiving yards per game.`);
  const ypc=ratio('rushing_yards','carries');if(ypc)lines.push(`Running backs gain ${ypc} yards per carry against this defense.`);
 }else{
  lines.push(`Opposing ${plural} average ${n(g.targets)} targets, ${n(g.receptions)} receptions, ${n(g.receiving_yards)} receiving yards and ${n(g.receiving_tds)} receiving touchdowns per game as a group.`);
 }
 const top=Math.ceil(row.rankedDefenses/4),bottom=row.rankedDefenses-top+1;
 lines.push(row.mostPointsRank<=top?'This is a favorable matchup by positional fantasy points allowed.':row.mostPointsRank>=bottom?'This is a difficult matchup by positional fantasy points allowed.':'The defense sits in the middle half of the ranked defenses by positional fantasy points allowed.');
 // Apply leading-receiver context only to this team's measured leading WR.
 if(p.position==='WR'&&evidence.currentLeaders?.[q.Team]===p.id){
  const lead=evidence.leadingWR?.[q.Opponent];
  if(valid(lead)){
   lines.push(`Against opposing leading receivers, ${q.Opponent} allows ${n(lead.perGame.receptions)} catches, ${n(lead.perGame.receiving_yards)} receiving yards and ${n(lead.perGame.fantasy_points_ppr)} PPR points per game across ${lead.games} qualifying games (No. ${lead.mostPointsRank} of ${lead.rankedDefenses} for most PPR points allowed).`);
   if(lead.games<6)lines.push('That leading-receiver split is a small sample; treat it as supporting context.');
  }
 }
 lines.push(`The published forecast is ${n(q.PPR)} PPR points.`);
 return {text:lines.join(' '),source:evidence.source,throughWeek:evidence.throughWeek,capturedAt:evidence.capturedAt,definition:evidence.leadingReceiverDefinition};
}
export function renderMatchup(p,evidence,esc,dateLabel){
 const result=matchupAnalysis(p,evidence);
 const head=`<h2>Week ${esc(p.projectionWeek)} matchup analysis</h2>`;
 if(result.unavailable)return `${head}<p class="data-meta">${esc(result.unavailable)}</p>`;
 return `${head}<p>${esc(result.text)}</p><details><summary>Matchup sources and sample limits</summary><p>Position results are totals for all opposing players at that position, divided by defensive games, not an individual player forecast. Rank 1 allows the most PPR points; ties share rank. At least three games are required. Raw results are not adjusted for opponent strength, game script or injuries and do not establish individual cornerback coverage. QB PPR totals follow the source’s default 4-point passing-TD scoring.</p><p>${esc(result.definition)}</p><p><a href="${esc(result.source.url)}">nflverse weekly player statistics</a> · through Week ${result.throughWeek} · captured ${dateLabel(result.capturedAt)} · SHA-256 <code>${esc(result.source.sha256)}</code></p></details>`;
}
