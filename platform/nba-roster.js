import {categories, matchPlayers, starters, production, tradeRoster, projectedRoster} from './nba-roster-engine.mjs';

const form = document.querySelector('#nba-roster-form');
const status = document.querySelector('#nba-roster-status');
const results = document.querySelector('#nba-roster-results');
const submit = document.querySelector('#nba-roster-submit');
const field = name => form.elements.namedItem(name);
const storageKey = 'rr.nba-roster.v1';
const savedFields = ['mode', 'period', 'league', 'slots', 'roster'];
const trades = ['outgoing', 'incoming', 'additions', 'drops'];
const fantasyPoints = ['fantasyPointsPerGame', 'Yahoo fantasy points'];
let periods;
let model;
const modelButton = document.querySelector('#nba-model-load');
const weeklyButton = document.querySelector('#nba-model-weekly');
const modelStatus = document.querySelector('#nba-model-status');

async function loadModel(weekly) {
  modelButton.disabled = weeklyButton.disabled = true;
  modelStatus.textContent = 'Checking access and loading model data…';
  try {
    const url = '/api/pro/?action=' + (weekly ? 'nba-roster-weekly' : 'nba-roster-projections');
    let response = await fetch(url);
    if (response.status === 401) {
      const renewed = await fetch('/api/pro/?action=refresh', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}',
      }).catch(() => null);
      if (renewed?.ok) response = await fetch(url);
    }
    const release = await response.json();
    if (!response.ok) throw Error(release.error || 'Model projections are unavailable.');
    model = release;
    const days = weekly ? ['week'] : [...new Set(model.players.map(player => player.day))].sort();
    field('modelDay').replaceChildren(new Option('Observed only', ''),
      ...days.map(day => new Option((weekly ? model.days[0] + ' through ' + model.days[6] : day) + (model.historical ? ' · historical preview' : ''), day)));
    field('modelDay').value = days[0];
    document.querySelector('#nba-model-date').hidden = false;
    modelStatus.textContent = (model.historical ? 'Historical model snapshot' : 'Release-approved model forecast') +
      ' · captured ' + new Date(model.capturedAt).toLocaleDateString('en-US', {timeZone: 'America/Los_Angeles'}) +
      '. Select Analyze roster to compare.';
  } catch (error) {
    model = null;
    document.querySelector('#nba-model-date').hidden = true;
    modelStatus.textContent = error.message;
  } finally {
    modelButton.disabled = weeklyButton.disabled = false;
  }
}
modelButton.addEventListener('click', () => loadModel(false));
weeklyButton.addEventListener('click', () => loadModel(true));

function table(title, headers, rows) {
  const wrapper = document.createElement('div');
  wrapper.className = 'pro-table';
  wrapper.tabIndex = 0;
  wrapper.setAttribute('role', 'region');
  wrapper.setAttribute('aria-label', title);
  const element = document.createElement('table');
  element.createCaption().textContent = title;
  const header = element.createTHead().insertRow();
  for (const name of headers) {
    const th = document.createElement('th');
    th.scope = 'col';
    th.textContent = name;
    header.append(th);
  }
  const body = element.createTBody();
  for (const row of rows) {
    const tr = body.insertRow();
    for (const value of row) tr.insertCell().textContent = value;
  }
  wrapper.append(element);
  return wrapper;
}

function format(value, percent, signed = false) {
  return value == null ? '—' : (signed && value > 0 ? '+' : '') + value.toFixed(1) + (percent ? (signed ? ' pp' : '%') : '');
}

function showWeekly(roster, afterRoster, slots, mode, metrics) {
  const title = document.createElement('h2');
  title.textContent = 'Weekly model projection comparison';
  const note = document.createElement('p');
  note.className = 'fine';
  results.append(title, note);
  if (Date.parse(model.validUntil) <= Date.now()) {
    note.textContent = 'The weekly model release expired. Load weekly projections again.';
    return;
  }
  function summarize(players) {
    const missing = new Set(players.filter(player => !Object.hasOwn(model.coverage, player.id)).map(player => player.name));
    const lineups = model.days.map((day, i) => {
      const forecasts = new Map(model.players.filter(player => player.day === day).map(player => [player.id, player]));
      const scheduled = players.filter(player => model.coverage[player.id]?.[i] === 'forecast');
      const projected = projectedRoster(scheduled, forecasts, mode);
      projected.missing.forEach(name => missing.add(name));
      return starters(projected.players, slots, mode);
    });
    return {missing, lineups, totals: production(lineups.flat())};
  }
  const before = summarize(roster);
  const after = afterRoster ? summarize(afterRoster) : null;
  const missing = [...new Set([...before.missing, ...(after?.missing || [])])];
  note.textContent = model.days[0] + ' through ' + model.days[6] + ' Pacific. Daily lineups are selected by ' +
    (mode === 'points' ? 'projected Yahoo points' : 'the observed 9-cat ranks for your selected stats period') +
    '. Weekly totals combine all covered starts and weight shooting by attempts. ' +
    (missing.length ? 'Incomplete roster coverage for ' + missing.join(', ') + '. Trade differences are withheld.' : '');
  results.append(table('Projected weekly starter production', ['Stat', 'Current', ...(after ? ['After trade', 'Change'] : [])],
    metrics.map(([key, label]) => {
      const percent = label.endsWith('%');
      const a = before.totals[key], b = after?.totals[key];
      return [label, format(a, percent), ...(after ? [format(b, percent),
        format(!missing.length && a != null && b != null ? b - a : null, percent, true)] : [])];
    })));
  const names = lineup => lineup.filter(Boolean).map(player => player.name).join(', ') || 'No projected starts';
  results.append(table('Projected starters by game date', ['Date', 'Current', ...(after ? ['After trade'] : [])],
    model.days.map((day, i) => [day, names(before.lineups[i]), ...(after ? [names(after.lineups[i])] : [])])));
}

function showProjected(roster, afterRoster, slots, mode, metrics, day) {
  const heading = document.createElement('h2');
  heading.textContent = model.historical ? 'Historical projection comparison' : 'Model projection comparison';
  const note = document.createElement('p');
  note.className = 'fine';
  results.append(heading, note);
  if (!model.historical && Date.parse(model.validUntil) <= Date.now()) {
    note.textContent = 'The model release expired. Load Pro projections again before comparing.';
    return;
  }
  const forecasts = new Map(model.players.filter(player => player.day === day).map(player => [player.id, player]));
  const before = projectedRoster(roster, forecasts, mode);
  const after = afterRoster ? projectedRoster(afterRoster, forecasts, mode) : null;
  const currentLineup = starters(before.players, slots, mode);
  const nextLineup = after ? starters(after.players, slots, mode) : null;
  const current = production(currentLineup);
  const next = nextLineup ? production(nextLineup) : null;
  const missing = [...new Set([...before.missing, ...(after?.missing || [])])];
  note.textContent = day + ' Pacific · conditional on playing · coverage limited to players in this release. ' +
    (mode === 'points' ? 'Starters are selected by projected Yahoo points. ' :
      'Starters are selected by 9-cat rank from the observed period you chose. ') +
    (missing.length ? 'Missing required data: ' + missing.join(', ') + '. Trade differences are withheld for incomplete rosters.' : '');
  results.append(table('Projected production for covered starters', ['Stat', 'Your lineup', ...(next ? ['After trade', 'Change'] : [])],
    metrics.map(([key, label]) => {
      const percent = label.endsWith('%');
      const change = next && !missing.length && next[key] != null && current[key] != null ? next[key] - current[key] : null;
      return [label, format(current[key], percent), ...(next ? [format(next[key], percent), format(change, percent, true)] : [])];
    })));
  results.append(table('Covered projected starters', ['Slot', 'Current', ...(nextLineup ? ['After trade'] : [])],
    slots.map((slot, i) => [slot, currentLineup[i]?.name || 'Open', ...(nextLineup ? [nextLineup[i]?.name || 'Open'] : [])])));
}

function analyze(event) {
  event.preventDefault();
  results.replaceChildren();
  try {
    const slots = field('slots').value.toUpperCase().split(/[\s,]+/).filter(Boolean);
    if (!slots.length || slots.length > 15 || slots.some(slot => !['G', 'F', 'C', 'UTIL'].includes(slot))) {
      throw Error('Enter 1–15 starting slots using G, F, C or UTIL.');
    }
    const period = field('period').value;
    const observed = periods.get(period);
    const played = new Set(observed.map(player => player.id));
    const pool = [...observed, ...periods.get('Full season').filter(player => !played.has(player.id))
      .map(player => ({...player, stats: {}}))];
    const read = name => {
      const result = matchPlayers(field(name).value, pool);
      if (result.issues.length) throw Error(field(name).labels[0].textContent.trim() + ': ' + result.issues.join(', '));
      return result.players;
    };
    const roster = read('roster');
    if (!roster.length) throw Error('Enter at least one player.');
    if (roster.length > 30) throw Error('Enter no more than 30 rostered players.');
    const mode = field('mode').value;
    const before = starters(roster, slots, mode);
    const afterRoster = trades.some(name => field(name).value.trim()) ? tradeRoster(roster, ...trades.map(read)) : null;
    const after = afterRoster ? starters(afterRoster, slots, mode) : null;
    const base = production(before);
    const next = after ? production(after) : null;
    const benchmarkCount = Number(field('league').value) * slots.length;
    const benchmarkPool = observed.filter(player => (mode === 'points' ? player.stats.fantasyPointsPerGame : player.stats.nineCatRank) != null)
      .sort((a, b) => mode === 'points' ? b.stats.fantasyPointsPerGame - a.stats.fantasyPointsPerGame : a.stats.nineCatRank - b.stats.nineCatRank)
      .slice(0, benchmarkCount);
    const benchmark = production(benchmarkPool);
    const notes = document.createElement('p');
    notes.className = 'fine';
    notes.textContent = 'Observed ' + period.toLowerCase() + ' per-game averages. Benchmark: average of the top ' +
      benchmarkPool.length + ' players by ' + (mode === 'points' ? 'Yahoo points' : '9-cat rank') +
      ', scaled to your starting slots. Lower turnovers are better. Empty slots are excluded from your totals.';
    const metrics = mode === 'points' ? [fantasyPoints] : categories;
    const comparison = metrics.map(([key, label]) => {
      const percent = label.endsWith('%');
      const reference = benchmark[key] == null ? null : benchmark[key] * (percent ? 1 : slots.length / benchmarkPool.length);
      const difference = next && next[key] != null && base[key] != null ? next[key] - base[key] : null;
      const edge = reference != null && base[key] != null ? base[key] - reference : null;
      return [label, format(base[key], percent), format(reference, percent), format(edge, percent, true),
        ...(next ? [format(next[key], percent), format(difference, percent, true)] : [])];
    });
    results.append(notes, table('Starter production per game', ['Stat', 'Your lineup', 'Benchmark', 'Vs. benchmark', ...(next ? ['After trade', 'Change'] : [])], comparison));
    const name = player => player?.name || 'Open';
    results.append(table('Starting lineup', ['Slot', 'Current', ...(after ? ['After trade'] : [])],
      slots.map((slot, i) => [slot, name(before[i]), ...(after ? [name(after[i])] : [])])));
    const bench = (players, lineup) => players.filter(player => !lineup.includes(player)).map(player =>
      player.name + (!played.has(player.id) ? ' (no stats this period)' : '')).join(', ') || 'None';
    results.append(table('Bench and depth', ['Roster', 'Players'], [['Current', bench(roster, before)],
      ...(after ? [['After trade', bench(afterRoster, after)]] : [])]));
    if (model && field('modelDay').value === 'week') showWeekly(roster, afterRoster, slots, mode, metrics);
    else if (model && field('modelDay').value) showProjected(roster, afterRoster, slots, mode, metrics, field('modelDay').value);
    status.textContent = after ? 'Trade comparison ready.' : 'Roster analysis ready.';
  } catch (error) {
    status.textContent = error.message;
  }
}

function save() {
  try { localStorage.setItem(storageKey, JSON.stringify(Object.fromEntries(savedFields.map(name => [name, field(name).value])))); } catch {}
}

form.addEventListener('submit', analyze);
form.addEventListener('input', event => { if (savedFields.includes(event.target.name)) save(); });
form.addEventListener('reset', () => {
  try { localStorage.removeItem(storageKey); } catch {}
  results.replaceChildren();
  status.textContent = 'Roster cleared.';
});
try {
  const response = await fetch('/platform/stats/nba.json.gz');
  if (!response.ok) throw Error();
  const data = await new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).json();
  periods = new Map([['Full season', data.boards], ...Object.entries(data.recent || {})]
    .map(([label, boards]) => [label, boards.find(board => board.label === 'Box score').rows]));
  field('period').replaceChildren(...[...periods.keys()].map(label => new Option(label, label)));
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    for (const name of savedFields) {
      if (typeof saved?.[name] !== 'string') continue;
      const control = field(name);
      if (control.options && ![...control.options].some(option => option.value === saved[name])) continue;
      control.value = saved[name];
    }
  } catch {}
  submit.disabled = false;
  status.textContent = 'Stats retrieved ' + new Date(data.capturedAt).toLocaleDateString() + '. Enter your roster to get started.';
} catch {
  status.textContent = 'NBA stats are temporarily unavailable. Reload to try again.';
}
