import crypto from 'node:crypto';
import {parseCsv} from './slate-ingestion.mjs';
import {SLOTS} from './optimizer.mjs';
import {fail} from './domain.mjs';
const digest=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const sameSet=(a,b)=>[...new Set(a)].sort().join('|')===[...new Set(b)].sort().join('|');
const clean=value=>String(value).normalize('NFKC').trim().replace(/\s+/g,' ');
function gameInfo(game){
 const parts=Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:true}).formatToParts(new Date(game.startTime)).map(p=>[p.type,p.value]));
 return `${game.awayTeam.abbreviation}@${game.homeTeam.abbreviation} ${parts.month}/${parts.day}/${parts.year} ${parts.hour}:${parts.minute}${parts.dayPeriod} ET`;
}
/** Cross-check the complete official export against the independent official API view.
 * Approval here covers salary facts only; it cannot grant model/availability approval. */
export function validateOfficialCapture({sport,draftGroupId,salaryCsv,draftablesJson,lobbyJson,rulesJson,captures,now=Date.now()}){
 if(!SLOTS[sport]||!/^\d+$/.test(String(draftGroupId)))fail(400,'Unsupported sport or draft group.');
 const prefix=sport.toLowerCase(),group=String(draftGroupId),files={
  salaryCsv:{name:`${prefix}-${group}-csv`,url:`https://www.draftkings.com/bulklineup/getdraftablecsv?draftGroupId=${group}`,bytes:salaryCsv},
  draftables:{name:`${prefix}-${group}`,url:`https://api.draftkings.com/draftgroups/v1/draftgroups/${group}/draftables`,bytes:draftablesJson},
  lobby:{name:`${prefix}-lobby`,url:`https://www.draftkings.com/lobby/getcontests?sport=${sport}`,bytes:lobbyJson},
  rules:{name:`${prefix}-rules`,url:`https://api.draftkings.com/lineups/v1/gametypes/${sport==='NBA'?70:1}/rules`,bytes:rulesJson}};
 const sourceRecords={};
 for(const [key,file] of Object.entries(files)){
  const matches=captures.filter(c=>c.name===file.name);if(matches.length!==1)fail(400,'Missing unique capture evidence: '+key);
  const evidence=matches[0];const received=Date.parse(evidence.receivedAt),requested=Date.parse(evidence.capturedAt);
  if(evidence.status!==200||evidence.error||evidence.url!==file.url||evidence.sha256!==digest(file.bytes)||!Number.isFinite(received)||!Number.isFinite(requested)||requested>received||received>now)fail(400,'Invalid source receipt or hash: '+key);
  sourceRecords[key]={url:evidence.url,capturedAt:evidence.receivedAt,sha256:evidence.sha256};
 }
 const source=JSON.parse(draftablesJson),lobby=JSON.parse(lobbyJson),rules=JSON.parse(rulesJson);
 if(Object.keys(source.errorStatus||{}).length||Object.keys(rules.errorStatus||{}).length)fail(400,'Official API reported an error.');
 const listings=lobby.DraftGroups?.filter(g=>String(g.DraftGroupId)===group)||[];
 if(listings.length!==1)fail(400,'Draft group is not uniquely present in the official lobby.');
 const slate=listings[0],games=source.competitions;
 if(slate.Sport!==sport||slate.GameTypeId!==rules.gameTypeId||rules.gameTypeName!=='Classic'||rules.salaryCap?.maxValue!==50000||rules.uniquePlayers!==true||rules.gameCount?.minValue!==2||rules.lineupTemplate?.map(s=>s.rosterSlot.name).join(',')!==SLOTS[sport].join(','))fail(400,'Official rules do not match supported Classic constraints.');
 if(!Array.isArray(games)||games.length!==slate.GameCount||games.length<2||source.teamsWithoutCompetitions?.length||!Array.isArray(source.draftables)||!source.draftables.length)fail(400,'Official game or player coverage is incomplete.');
 const firstLock=Math.min(...games.map(g=>Date.parse(g.startTime)));
 if(!Number.isFinite(firstLock)||firstLock!==Date.parse(slate.StartDate)||Object.values(sourceRecords).some(r=>Date.parse(r.capturedAt)>=firstLock))fail(400,'Capture was not completed before the selected slate locked.');
 const gameById=new Map();
 for(const game of games){
  if(game.sport!==sport||game.competitionState!=='Upcoming'||game.competitionStartedEarly||gameById.has(String(game.competitionId))||!Number.isFinite(Date.parse(game.startTime)))fail(400,'Invalid or already-started official game.');
  gameById.set(String(game.competitionId),game);
 }
 const slotNames=new Map(rules.lineupTemplate.map(s=>[s.rosterSlot.id,s.rosterSlot.name]));
 const byDraftable=new Map(),byPlayer=new Map();
 for(const p of source.draftables){
  const id=String(p.draftableId);if(!/^\d+$/.test(id)||!/^\d+$/.test(String(p.playerId))||byDraftable.has(id)||!slotNames.has(p.rosterSlotId)||!gameById.has(String(p.competition?.competitionId)))fail(400,'Invalid or repeated official draftable identity.');
  byDraftable.set(id,p);const key=String(p.playerId);if(!byPlayer.has(key))byPlayer.set(key,[]);byPlayer.get(key).push(p);
 }
 const csv=parseCsv(String(salaryCsv)),players=[],seen=new Set(),exportIds=new Set();
 for(const row of csv){
  const raw=byDraftable.get(row.ID),player=String(raw?.playerId),game=gameById.get(String(raw?.competition?.competitionId));
  if(!raw||seen.has(player)||exportIds.has(row.ID)||clean(row.Name)!==clean(raw.displayName)||row.TeamAbbrev!==raw.teamAbbreviation||Number(row.Salary)!==raw.salary||!Number.isInteger(raw.salary)||raw.salary<=0||raw.salary>50000||!sameSet(row.Position.split('/'),raw.position.split('/'))||row['Game Info']!==gameInfo(game))fail(400,'Salary export does not match official player/game evidence: '+row.ID);
  const variants=byPlayer.get(player),rosterPositions=variants.map(p=>slotNames.get(p.rosterSlotId));
  if(!sameSet(row['Roster Position']?.split('/')||[],rosterPositions)||variants.some(p=>p.salary!==raw.salary||p.teamAbbreviation!==raw.teamAbbreviation||p.position!==raw.position||p.competition.competitionId!==raw.competition.competitionId||p.displayName!==raw.displayName))fail(400,'Official roster eligibility or duplicate-slot variants disagree.');
  seen.add(player);exportIds.add(row.ID);
  const opponent=raw.teamAbbreviation===game.homeTeam.abbreviation?game.awayTeam.abbreviation:raw.teamAbbreviation===game.awayTeam.abbreviation?game.homeTeam.abbreviation:null;
  if(!opponent)fail(400,'Player team is outside the official game.');
  players.push({id:row.ID,dkPlayerId:player,playerDkId:String(raw.playerDkId),name:clean(row.Name),team:row.TeamAbbrev,opponent,gameId:String(game.competitionId),startsAt:game.startTime,salary:raw.salary,positions:row.Position.split('/'),rosterPositions:[...new Set(rosterPositions)],slotDraftableIds:Object.fromEntries(variants.map(p=>[slotNames.get(p.rosterSlotId),String(p.draftableId)])),sourceStatus:raw.status,sourceDisabled:raw.isDisabled===true,availabilityVerified:false});
 }
 if(seen.size!==byPlayer.size)fail(400,'The export is a partial official salary pool.');
 return {schemaVersion:1,kind:'official-salary-pool',sport,draftGroupId:group,salaryDataApproved:true,publishApproved:false,capturedAt:sourceRecords.salaryCsv.capturedAt,locksAt:new Date(firstLock).toISOString(),games:games.map(g=>({id:String(g.competitionId),away:g.awayTeam.abbreviation,home:g.homeTeam.abbreviation,startsAt:g.startTime})),players,sourceRecords,validation:{officialCsvRows:csv.length,uniquePlayers:seen.size,rawSlotDraftables:source.draftables.length,gameCount:games.length,allCsvRowsMatched:true,fullApiPlayerCoverage:true,rosterAndSalaryCapVerified:true},limitations:['Salary data approval covers this captured slate only and is not model release approval.','Operator status is retained as evidence; an unlisted injury status is not asserted to be confirmed active.','Proprietary projection identity mappings, pre-lock availability and model release checks remain required.','This current capture is not evidence for a historical salary/backtest reconstruction.']};
}
