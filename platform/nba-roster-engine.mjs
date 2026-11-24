export const categories = [
  ['avgPoints', 'PTS'], ['avgThreePointFieldGoalsMade', '3PM'], ['avgRebounds', 'REB'],
  ['avgAssists', 'AST'], ['avgSteals', 'STL'], ['avgBlocks', 'BLK'], ['avgTurnovers', 'TO'],
  ['fieldGoalPct', 'FG%'], ['freeThrowPct', 'FT%'],
];

export function matchPlayers(input, players) {
  const normalize = name => name.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase().replace(/[^a-z0-9]/g, '');
  const names = input.split(/[\n,]+/).map(name => name.trim()).filter(Boolean);
  const matched = new Map();
  const issues = [];
  for (const name of names) {
    const candidates = players.filter(player => normalize(player.name) === normalize(name));
    if (candidates.length !== 1) issues.push(name + (candidates.length ? ' (ambiguous)' : ' (unmatched)'));
    else if (matched.has(candidates[0].id)) issues.push(name + ' (duplicate)');
    else matched.set(candidates[0].id, candidates[0]);
  }
  return {players: [...matched.values()], issues};
}

export function starters(roster, slots, mode) {
  const score = player => mode === 'points' ? player.stats.fantasyPointsPerGame : -player.stats.nineCatRank;
  const eligible = player => mode === 'points' ? player.stats.fantasyPointsPerGame != null : player.stats.nineCatRank != null;
  const ordered = roster.filter(eligible).sort((a, b) => score(b) - score(a) || a.name.localeCompare(b.name));
  const filled = Array(slots.length).fill(null);
  function place(player, visited) {
    for (const [i, slot] of slots.entries()) {
      if (visited.has(i) || (slot !== 'UTIL' && !player.position.split(/[/, -]+/).includes(slot))) continue;
      visited.add(i);
      if (!filled[i] || place(filled[i], visited)) {
        filled[i] = player;
        return true;
      }
    }
    return false;
  }
  for (const player of ordered) place(player, new Set());
  return filled;
}

export function production(players) {
  const rows = players.filter(Boolean).map(player => player.stats);
  const sum = key => rows.length && rows.every(stats => Number.isFinite(stats[key]))
    ? rows.reduce((total, stats) => total + stats[key], 0) : null;
  const percentage = (made, attempts) => {
    const m = sum(made), a = sum(attempts);
    return m != null && a > 0 ? 100 * m / a : null;
  };
  return {
    ...Object.fromEntries(categories.slice(0, 7).map(([key]) => [key, sum(key)])),
    fieldGoalPct: percentage('avgFieldGoalsMade', 'avgFieldGoalsAttempted'),
    freeThrowPct: percentage('avgFreeThrowsMade', 'avgFreeThrowsAttempted'),
    fantasyPointsPerGame: sum('fantasyPointsPerGame'),
  };
}

export function tradeRoster(roster, outgoing, incoming, additions, drops) {
  const held = new Map(roster.map(player => [player.id, player]));
  if (!outgoing.length || !incoming.length) throw Error('Enter at least one player on both sides of the trade.');
  for (const player of [...outgoing, ...drops]) {
    if (!held.delete(player.id)) throw Error(player.name + ' must be on your roster and can only leave once.');
  }
  const original = new Set(roster.map(player => player.id));
  for (const player of [...incoming, ...additions]) {
    if (original.has(player.id) || held.has(player.id)) throw Error(player.name + ' is already on your roster or listed twice.');
    held.set(player.id, player);
  }
  if (held.size !== roster.length) throw Error('Use the add or drop fields to keep the same roster size.');
  return [...held.values()];
}

export function projectedRoster(roster, forecasts, mode) {
  const missing = [];
  const players = roster.map(player => {
    const forecast = forecasts.get(String(player.id));
    const rank = player.stats.nineCatRank;
    if (!forecast || (mode === 'points' ? !Number.isFinite(forecast.yahoo) : !Number.isFinite(rank))) {
      missing.push(player.name);
      return {...player, stats: {}};
    }
    const s = forecast.statline;
    return {...player, stats: {
      avgPoints: s.PTS, avgThreePointFieldGoalsMade: s.FG3M, avgRebounds: s.REB,
      avgAssists: s.AST, avgSteals: s.STL, avgBlocks: s.BLK, avgTurnovers: s.TOV,
      avgFieldGoalsMade: s.FGM, avgFieldGoalsAttempted: s.FGA,
      avgFreeThrowsMade: s.FTM, avgFreeThrowsAttempted: s.FTA,
      fantasyPointsPerGame: forecast.yahoo, nineCatRank: rank,
    }};
  });
  return {players, missing};
}
