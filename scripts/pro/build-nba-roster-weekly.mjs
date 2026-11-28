import fs from 'node:fs';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {validateArtifact} from '../../server/domain.mjs';
import {validateModelLineage} from '../../server/model-lineage.mjs';
import {weeklyRosterRelease} from '../../server/nba-roster-projections.mjs';

const hash = text => crypto.createHash('sha256').update(text).digest('hex');
const pacific = new Intl.DateTimeFormat('en-CA', {timeZone:'America/Los_Angeles', year:'numeric', month:'2-digit', day:'2-digit'});

export function buildWeekly(manifest, artifacts, now = Date.now()) {
  // The manifest must be sourced from a full schedule and a current team roster.
  // Confirmed outs require dated availability evidence in that manifest.
  const {weekStart, games, roster, scheduleDays, absences = []} = manifest;
  if (!Array.isArray(games) || !games.length || !Array.isArray(roster) || !roster.length || !artifacts.length) {
    throw Error('A full schedule, current team roster and incumbent forecasts are required.');
  }
  const start = Date.parse(weekStart + 'T00:00:00Z');
  if (!Number.isFinite(start) || new Date(start).getUTCDay() !== 1) throw Error('Select a Monday week start.');
  const days = Array.from({length:7}, (_, i) => new Date(start + i * 86400000).toISOString().slice(0,10));
  const schedule = new Map();
  const tipoffs = new Map();
  for (const game of games) {
    const tip = Date.parse(game.startsAt);
    if (!game.id || tipoffs.has(String(game.id)) || !(tip > now) || !days.includes(pacific.format(tip)) ||
        !/^[A-Z]{2,3}$/.test(game.home) || !/^[A-Z]{2,3}$/.test(game.away) || game.home === game.away) {
      throw Error('The full-week schedule must contain unique upcoming games within the selected week.');
    }
    tipoffs.set(String(game.id), tip);
    for (const team of [game.home, game.away]) {
      const key = team + ':' + pacific.format(tip);
      if (schedule.has(key)) throw Error('Duplicate team game on a schedule date.');
      schedule.set(key, String(game.id));
    }
  }
  if (!Array.isArray(scheduleDays) || scheduleDays.length !== days.length || !days.every((day, i) => {
    const evidence = scheduleDays[i];
    const expected = games.filter(game => pacific.format(Date.parse(game.startsAt)) === day).map(game => String(game.id)).sort();
    return evidence?.day === day && /^[a-f0-9]{64}$/i.test(evidence.sourceHash || '') &&
      Array.isArray(evidence.gameIds) && JSON.stringify(evidence.gameIds.map(String).sort()) === JSON.stringify(expected);
  })) throw Error('Provide seven dated schedule captures, including explicitly empty dates.');
  const identities = new Map();
  for (const row of roster) {
    const id = String(row.id);
    if (!/^\d+$/.test(id) || !/^[A-Z]{2,3}$/.test(row.team) || identities.has(id)) throw Error('Invalid weekly roster identity.');
    identities.set(id, row.team);
  }
  for (const game of games) {
    if (![game.home,game.away].every(team => [...identities.values()].includes(team))) throw Error('A scheduled team is missing from the roster manifest.');
  }
  const unavailable = new Map();
  for (const row of absences) {
    const key = String(row.id) + ':' + String(row.gameId);
    if (!identities.has(String(row.id)) || !tipoffs.has(String(row.gameId)) || unavailable.has(key) ||
        !/^[a-f0-9]{64}$/i.test(row.evidenceHash || '') || !Number.isFinite(Date.parse(row.asOf)) ||
        Date.parse(row.asOf) > now) throw Error('Invalid confirmed absence evidence.');
    unavailable.set(key, row);
  }
  const players = new Map();
  const coveredGames = new Set();
  for (const artifact of artifacts) {
    validateArtifact(artifact, {kind:'projections', sport:'NBA', now});
    validateModelLineage(artifact);
    for (const row of artifact.players) {
      const id = String(row.id), game = String(row.gameId), tip = tipoffs.get(game);
      if (!tip || Date.parse(row.startsAt) !== tip || row.team !== identities.get(id) ||
          schedule.get(row.team + ':' + pacific.format(tip)) !== game) throw Error('Forecast does not match the verified weekly schedule and roster.');
      const key = id + ':' + game;
      if (players.has(key)) throw Error('Duplicate player-game forecast.');
      if (unavailable.has(key)) continue;
      players.set(key, row);
      coveredGames.add(game);
    }
  }
  if (coveredGames.size !== tipoffs.size) throw Error('At least one scheduled game is missing forecast coverage.');
  const coverage = {};
  for (const [id, team] of identities) {
    const entries = days.map(day => {
      const game = schedule.get(team + ':' + day), key = id + ':' + game;
      return {day, status: !game ? 'off' : unavailable.has(key) ? 'out' : players.has(key) ? 'forecast' : 'missing'};
    });
    if (entries.every(entry => entry.status !== 'missing')) coverage[id] = entries;
  }
  const artifact = {
    schemaVersion:1, kind:'weekly-roster-projections', sport:'NBA', publishApproved:true, weekStart,
    capturedAt:new Date(Math.max(...artifacts.map(a => Date.parse(a.capturedAt)))).toISOString(),
    validUntil:new Date(Math.min(...tipoffs.values(), ...artifacts.map(a => Date.parse(a.validUntil)))).toISOString(),
    provenance:{...artifacts[0].provenance, scheduleHash:hash(JSON.stringify({games, scheduleDays})),
      sourceHash:hash(JSON.stringify({manifest, artifacts:artifacts.map(a => a.provenance.sourceHash)}))},
    players:[...players.values()], coverage,
  };
  const validated = weeklyRosterRelease(artifact, now);
  if (!validated.players.every(row => Number.isFinite(row.yahoo)) || Object.keys(validated.coverage).length !== Object.keys(coverage).length) {
    throw Error('Weekly forecast rows contain incomplete statlines or Yahoo scoring.');
  }
  return artifact;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [manifestPath, outputPath, ...inputs] = process.argv.slice(2);
  if (!manifestPath || !outputPath || !inputs.length) {
    console.error('Usage: node scripts/pro/build-nba-roster-weekly.mjs manifest.json output.json daily-basic.json [more daily files]');
    process.exitCode = 1;
  } else {
    const read = path => JSON.parse(fs.readFileSync(path,'utf8'));
    const result = buildWeekly(read(manifestPath), inputs.map(read));
    fs.writeFileSync(outputPath, JSON.stringify(result), {flag:'wx', mode:0o600});
    console.log('Validated weekly NBA projection package', {weekStart:result.weekStart, forecasts:result.players.length, completePlayers:Object.keys(result.coverage).length});
  }
}
