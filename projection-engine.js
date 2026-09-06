/*
 * The Roster Report Fantasy Football Projection Engine — v0.1
 *
 * Philosophy:
 *   team environment -> player opportunity -> player efficiency -> raw stats
 *   -> scoring-format fantasy points -> uncertainty / value hooks
 *
 * This module is intentionally independent from app.js so the existing v10
 * trade analyzer remains stable while projections are developed and backtested.
 */

export const DEFAULT_SCORING = {
  ppr: {
    passYd: 0.04, passTd: 4, interception: -2,
    rushYd: 0.1, rushTd: 6,
    reception: 1, recYd: 0.1, recTd: 6,
    fumbleLost: -2
  },
  half: {
    passYd: 0.04, passTd: 4, interception: -2,
    rushYd: 0.1, rushTd: 6,
    reception: 0.5, recYd: 0.1, recTd: 6,
    fumbleLost: -2
  },
  standard: {
    passYd: 0.04, passTd: 4, interception: -2,
    rushYd: 0.1, rushTd: 6,
    reception: 0, recYd: 0.1, recTd: 6,
    fumbleLost: -2
  }
};

export const DEFAULT_MODEL = {
  seasons: { 2023: 0.20, 2024: 0.30, 2025: 0.50 },
  tradeAnalyzerPrior: {
    aw: 0.45,
    analytics: 0.35,
    scarcity: 0.10,
    market: 0.10
  },
  regression: {
    catchRate: 0.30,
    yardsPerTarget: 0.35,
    tdRate: 0.55,
    yardsPerCarry: 0.35,
    passTdRate: 0.45,
    interceptionRate: 0.40
  },
  uncertainty: {
    QB: 0.18,
    RB: 0.24,
    WR: 0.22,
    TE: 0.23,
    rookieAdd: 0.08,
    roleChangeAdd: 0.05,
    injuryAdd: 0.04
  }
};

const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, Number.isFinite(x) ? x : lo));
const safe = (x, fallback = 0) => Number.isFinite(Number(x)) ? Number(x) : fallback;
const div = (a, b, fallback = 0) => safe(b) !== 0 ? safe(a) / safe(b) : fallback;
const weightedMean = pairs => {
  let num = 0, den = 0;
  for (const [value, weight] of pairs) {
    if (Number.isFinite(Number(value)) && Number.isFinite(Number(weight)) && weight > 0) {
      num += Number(value) * Number(weight);
      den += Number(weight);
    }
  }
  return den ? num / den : null;
};
const round = (x, n = 1) => Number(Number(x || 0).toFixed(n));

export function buildTradeAnalyzerPrior(player, weights = DEFAULT_MODEL.tradeAnalyzerPrior) {
  const fields = {
    aw: player.awRating ?? player.awScore ?? null,
    analytics: player.analyticsRating ?? player.analyticsScore ?? null,
    scarcity: player.scarcityRating ?? player.scarcityScore ?? null,
    market: player.marketRating ?? player.marketScore ?? null
  };
  const pairs = Object.entries(weights).map(([key, weight]) => [fields[key], weight]);
  return weightedMean(pairs);
}

export function weightedHistory(seasons, field, seasonWeights = DEFAULT_MODEL.seasons) {
  return weightedMean(Object.entries(seasonWeights).map(([season, weight]) => [seasons?.[season]?.[field], weight]));
}

export function regressRate(playerRate, leagueRate, regressionWeight) {
  if (!Number.isFinite(Number(playerRate))) return safe(leagueRate);
  return safe(playerRate) * (1 - regressionWeight) + safe(leagueRate) * regressionWeight;
}

export function projectTeam(team) {
  const games = clamp(safe(team.games, 17), 1, 17);
  const playsPerGame = clamp(safe(team.playsPerGame, 63.5), 50, 75);
  const passRate = clamp(safe(team.passRate, 0.57), 0.42, 0.72);
  const sacksPerDropback = clamp(safe(team.sacksPerDropback, 0.065), 0.02, 0.16);

  const plays = games * playsPerGame;
  const dropbacks = plays * passRate;
  const passAttempts = dropbacks * (1 - sacksPerDropback);
  const rushAttempts = Math.max(0, plays - dropbacks);

  return {
    team: team.team,
    games,
    plays: round(plays),
    passRate: round(passRate, 3),
    dropbacks: round(dropbacks),
    passAttempts: round(passAttempts),
    rushAttempts: round(rushAttempts),
    passYards: round(safe(team.passYardsPerAttempt, 7.0) * passAttempts),
    passTds: round(safe(team.passTdRate, 0.045) * passAttempts),
    interceptions: round(safe(team.interceptionRate, 0.022) * passAttempts),
    rushYards: round(safe(team.rushYardsPerCarry, 4.25) * rushAttempts),
    rushTds: round(safe(team.rushTdRate, 0.032) * rushAttempts)
  };
}

function availability(player) {
  const games = clamp(safe(player.projectedGames, 16.2), 1, 17);
  return { games, share: games / 17 };
}

function roleMultiplier(player) {
  return clamp(safe(player.roleMultiplier, 1), 0.35, 1.40);
}

function projectReceiver(player, team, league) {
  const avail = availability(player);
  const role = roleMultiplier(player);
  const routeParticipation = clamp(safe(player.routeParticipation, 0.75), 0, 1);
  const targetsPerRoute = clamp(safe(player.targetsPerRoute, player.pos === 'TE' ? 0.18 : 0.20), 0.05, 0.40);
  const routes = team.dropbacks * routeParticipation * avail.share * role;
  const targets = Math.min(team.passAttempts * avail.share, routes * targetsPerRoute);

  const catchRate = regressRate(
    player.catchRate,
    safe(league.catchRate, player.pos === 'TE' ? 0.68 : 0.64),
    DEFAULT_MODEL.regression.catchRate
  );
  const ypt = regressRate(
    player.yardsPerTarget,
    safe(league.yardsPerTarget, player.pos === 'TE' ? 7.5 : 8.0),
    DEFAULT_MODEL.regression.yardsPerTarget
  );
  const tdPerTarget = regressRate(
    player.recTdPerTarget,
    safe(league.recTdPerTarget, 0.05),
    DEFAULT_MODEL.regression.tdRate
  );

  const receptions = targets * catchRate;
  return {
    games: avail.games,
    routes,
    targets,
    receptions,
    recYards: targets * ypt,
    recTds: targets * tdPerTarget,
    rushAttempts: safe(player.rushAttemptsPerGame) * avail.games,
    rushYards: safe(player.rushYardsPerGame) * avail.games,
    rushTds: safe(player.rushTdsPerGame) * avail.games
  };
}

function projectRunningBack(player, team, league) {
  const avail = availability(player);
  const role = roleMultiplier(player);
  const carryShare = clamp(safe(player.carryShare, 0.42), 0.02, 0.90);
  const routeParticipation = clamp(safe(player.routeParticipation, 0.42), 0, 0.90);
  const targetsPerRoute = clamp(safe(player.targetsPerRoute, 0.18), 0.03, 0.38);

  const rushAttempts = team.rushAttempts * carryShare * avail.share * role;
  const ypc = regressRate(
    player.yardsPerCarry,
    safe(league.yardsPerCarry, 4.25),
    DEFAULT_MODEL.regression.yardsPerCarry
  );
  const routes = team.dropbacks * routeParticipation * avail.share * role;
  const targets = Math.min(team.passAttempts * avail.share, routes * targetsPerRoute);
  const catchRate = regressRate(player.catchRate, safe(league.rbCatchRate, 0.77), DEFAULT_MODEL.regression.catchRate);
  const ypt = regressRate(player.yardsPerTarget, safe(league.rbYardsPerTarget, 6.2), DEFAULT_MODEL.regression.yardsPerTarget);

  const teamGoalLineTds = team.rushTds;
  const rushTdShare = clamp(safe(player.rushTdShare, carryShare), 0, 0.95);
  const recTdPerTarget = regressRate(player.recTdPerTarget, safe(league.rbRecTdPerTarget, 0.025), DEFAULT_MODEL.regression.tdRate);

  return {
    games: avail.games,
    rushAttempts,
    rushYards: rushAttempts * ypc,
    rushTds: teamGoalLineTds * rushTdShare * avail.share,
    targets,
    receptions: targets * catchRate,
    recYards: targets * ypt,
    recTds: targets * recTdPerTarget
  };
}

function projectQuarterback(player, team, league) {
  const avail = availability(player);
  const role = roleMultiplier(player);
  const attemptShare = clamp(safe(player.qbAttemptShare, 0.97), 0.20, 1);
  const attempts = team.passAttempts * attemptShare * avail.share * role;

  const ypa = regressRate(player.passYardsPerAttempt, safe(league.passYardsPerAttempt, 7.0), 0.30);
  const passTdRate = regressRate(player.passTdRate, safe(league.passTdRate, 0.045), DEFAULT_MODEL.regression.passTdRate);
  const interceptionRate = regressRate(player.interceptionRate, safe(league.interceptionRate, 0.022), DEFAULT_MODEL.regression.interceptionRate);

  const rushAttempts = safe(player.rushAttemptsPerGame, 3.5) * avail.games * role;
  const rushYpc = regressRate(player.rushYardsPerAttempt, safe(league.qbRushYardsPerAttempt, 4.7), 0.25);
  const rushTdRate = regressRate(player.rushTdPerAttempt, safe(league.qbRushTdPerAttempt, 0.035), 0.35);

  return {
    games: avail.games,
    passAttempts: attempts,
    passYards: attempts * ypa,
    passTds: attempts * passTdRate,
    interceptions: attempts * interceptionRate,
    rushAttempts,
    rushYards: rushAttempts * rushYpc,
    rushTds: rushAttempts * rushTdRate
  };
}

export function projectPlayer(player, teamProjection, league = {}) {
  let stats;
  if (player.pos === 'QB') stats = projectQuarterback(player, teamProjection, league);
  else if (player.pos === 'RB') stats = projectRunningBack(player, teamProjection, league);
  else if (player.pos === 'WR' || player.pos === 'TE') stats = projectReceiver(player, teamProjection, league);
  else throw new Error(`Unsupported projection position: ${player.pos}`);

  const rounded = Object.fromEntries(Object.entries(stats).map(([k, v]) => [k, round(v, k === 'games' ? 1 : 1)]));
  return {
    name: player.name,
    team: player.team,
    pos: player.pos,
    rookie: Boolean(player.rookie),
    tradeAnalyzerPrior: round(buildTradeAnalyzerPrior(player), 2),
    ...rounded
  };
}

export function fantasyPoints(stats, scoring = DEFAULT_SCORING.half) {
  return round(
    safe(stats.passYards) * scoring.passYd +
    safe(stats.passTds) * scoring.passTd +
    safe(stats.interceptions) * scoring.interception +
    safe(stats.rushYards) * scoring.rushYd +
    safe(stats.rushTds) * scoring.rushTd +
    safe(stats.receptions) * scoring.reception +
    safe(stats.recYards) * scoring.recYd +
    safe(stats.recTds) * scoring.recTd +
    safe(stats.fumblesLost) * scoring.fumbleLost,
    1
  );
}

export function addScoring(projection, scoringSets = DEFAULT_SCORING) {
  return {
    ...projection,
    fantasyPoints: Object.fromEntries(
      Object.entries(scoringSets).map(([format, scoring]) => [format, fantasyPoints(projection, scoring)])
    )
  };
}

export function uncertaintyBand(player, projection, format = 'half', model = DEFAULT_MODEL) {
  const median = safe(projection.fantasyPoints?.[format]);
  let sigma = safe(model.uncertainty[player.pos], 0.22);
  if (player.rookie) sigma += model.uncertainty.rookieAdd;
  if (player.majorRoleChange) sigma += model.uncertainty.roleChangeAdd;
  if (player.injuryConcern) sigma += model.uncertainty.injuryAdd;

  return {
    floor: round(median * Math.max(0, 1 - 1.15 * sigma), 1),
    median: round(median, 1),
    ceiling: round(median * (1 + 1.15 * sigma), 1),
    uncertainty: round(sigma, 3)
  };
}

export function projectRoster({ teams, players, league = {}, scoringSets = DEFAULT_SCORING }) {
  const teamMap = new Map(teams.map(t => {
    const projected = projectTeam(t);
    return [projected.team, projected];
  }));

  const projections = players.map(player => {
    const teamProjection = teamMap.get(player.team);
    if (!teamProjection) throw new Error(`Missing team environment for ${player.name} (${player.team})`);
    const base = addScoring(projectPlayer(player, teamProjection, league), scoringSets);
    return {
      ...base,
      ranges: Object.fromEntries(Object.keys(scoringSets).map(format => [format, uncertaintyBand(player, base, format)]))
    };
  });

  for (const format of Object.keys(scoringSets)) {
    const sorted = [...projections].sort((a, b) => b.fantasyPoints[format] - a.fantasyPoints[format]);
    sorted.forEach((p, i) => {
      p.ranks ??= {};
      p.ranks[format] = i + 1;
    });

    for (const pos of ['QB', 'RB', 'WR', 'TE']) {
      const group = sorted.filter(p => p.pos === pos);
      group.forEach((p, i) => {
        p.posRanks ??= {};
        p.posRanks[format] = i + 1;
      });
    }
  }

  return projections;
}

export function projectionTradeValueHook(player, projection, format = 'half') {
  // Does not replace v10 trade value. This gives the analyzer a normalized
  // projection signal that can later be blended after backtesting.
  const points = safe(projection.fantasyPoints?.[format]);
  const floor = safe(projection.ranges?.[format]?.floor, points);
  const ceiling = safe(projection.ranges?.[format]?.ceiling, points);
  const stability = points ? clamp(floor / points, 0, 1) : 0;
  const upside = points ? clamp(ceiling / points - 1, 0, 1) : 0;
  return round(points * (0.85 + 0.10 * stability + 0.05 * upside), 2);
}
