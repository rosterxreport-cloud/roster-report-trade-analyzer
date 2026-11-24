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
