import {categories, matchPlayers, starters, production, tradeRoster} from './nba-roster-engine.mjs';

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
