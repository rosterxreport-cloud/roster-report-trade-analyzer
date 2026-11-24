import {fail} from './domain.mjs';

export function rosterProjectionRelease(artifact, {historical = false, now = Date.now()} = {}) {
  const fields = ['MIN','PTS','FG3M','REB','AST','STL','BLK','TOV','FGM','FGA','FTM','FTA'];
  const dates = new Intl.DateTimeFormat('en-CA', {timeZone: 'America/Los_Angeles',
    year: 'numeric', month: '2-digit', day: '2-digit'});
  const players = [];
  const seen = new Set();
  for (const player of artifact.players) {
    const start = Date.parse(player.startsAt);
    const id = String(player.id);
    if (!/^\d+$/.test(id) || !Number.isFinite(start) || (!historical && start <= now)) continue;
    const day = dates.format(start);
    const key = day + ':' + id;
    if (seen.has(key)) fail(503, 'The model release has duplicate player forecasts for a game date.');
    seen.add(key);
    const statline = player.statline;
    if (['out', 'inactive', 'doubtful', 'ir', 'suspended'].includes(String(player.status || player.availability).toLowerCase()) ||
        !(statline?.MIN > 0) || fields.some(k => !Number.isFinite(statline[k]) || statline[k] < 0) ||
        statline.FGM > statline.FGA || statline.FTM > statline.FTA) continue;
    players.push({id, day, statline: Object.fromEntries(fields.map(k => [k, statline[k]])),
      yahoo: Number.isFinite(player.fantasyPoints?.Yahoo) ? player.fantasyPoints.Yahoo : null});
  }
  if (!players.length) fail(503, 'No eligible game-dated NBA model forecasts are available.');
  return {capturedAt: artifact.capturedAt, historical, players,
    validUntil: historical ? null : artifact.validUntil};
}

// Each player needs seven explicitly verified days. Off days and confirmed absences
// are represented separately from omitted or unusable forecasts.
export function weeklyRosterRelease(artifact, now = Date.now()) {
  const start = Date.parse(artifact.weekStart + 'T00:00:00Z');
  const today = new Intl.DateTimeFormat('en-CA', {timeZone: 'America/Los_Angeles',
    year: 'numeric', month: '2-digit', day: '2-digit'}).format(now);
  if (!Number.isFinite(start) || new Date(start).toISOString().slice(0, 10) !== artifact.weekStart ||
      new Date(start).getUTCDay() !== 1 || artifact.weekStart < today ||
      !/^[a-f0-9]{64}$/i.test(artifact.provenance?.scheduleHash || '')) {
    fail(503, 'A verified full-week NBA model release is unavailable.');
  }
  const days = Array.from({length: 7}, (_, i) => new Date(start + i * 86400000).toISOString().slice(0, 10));
  const firstGame = Math.min(...artifact.players.map(player => Date.parse(player.startsAt)));
  if (!Number.isFinite(firstGame) || firstGame <= now) fail(503, 'A complete pregame weekly forecast is unavailable.');
  const forecasts = rosterProjectionRelease(artifact, {now});
  const byPlayerDay = new Map(forecasts.players.map(player => [player.id + ':' + player.day, player]));
  if (forecasts.players.some(player => !days.includes(player.day))) fail(503, 'The weekly release contains forecasts outside its week.');
  const coverage = {};
  for (const [id, entries] of Object.entries(artifact.coverage || {})) {
    if (!/^\d+$/.test(id) || !Array.isArray(entries) || entries.length !== 7) continue;
    if (!entries.every((entry, i) => entry?.day === days[i] &&
      (entry.status === 'forecast' ? byPlayerDay.has(id + ':' + entry.day) :
        ['off', 'out'].includes(entry.status) && !byPlayerDay.has(id + ':' + entry.day)))) continue;
    coverage[id] = entries.map(entry => entry.status);
  }
  if (!Object.keys(coverage).length) fail(503, 'No players have all seven days verified.');
  return {...forecasts, days, coverage, validUntil: new Date(Math.min(firstGame, Date.parse(artifact.validUntil))).toISOString()};
}
