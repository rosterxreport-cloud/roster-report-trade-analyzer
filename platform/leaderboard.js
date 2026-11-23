// Keep column order independent of the active sort and filter.
const columnOrder = {
  'Box score': 'gamesPlayed avgMinutes avgPoints avgRebounds avgAssists avgSteals avgBlocks avgTurnovers avgFouls avgFieldGoalsMade avgFieldGoalsAttempted avgThreePointFieldGoalsMade avgThreePointFieldGoalsAttempted avgFreeThrowsMade avgFreeThrowsAttempted minutes points rebounds assists steals blocks turnovers fouls fieldGoalsMade fieldGoalsAttempted threePointFieldGoalsMade threePointFieldGoalsAttempted freeThrowsMade freeThrowsAttempted doubleDouble tripleDouble flagrantFouls technicalFouls ejections fieldGoalPct threePointFieldGoalPct freeThrowPct usageRate ts efg threeRate ftRate astTo pts36 reb36 ast36 stocks36',
  'Efficiency & per 36': 'gamesPlayed minutes fieldGoalsAttempted usageRate ts efg threeRate ftRate astTo pts36 reb36 ast36 stocks36',
  Passing: 'games attempts passing_yards passing_tds passing_interceptions sacks_suffered passing_air_yards passing_epa passing_cpoe pacr',
  Rushing: 'games carries rushing_yards rushing_tds rushing_20 rushing_epa',
  Receiving: 'games targets receptions receiving_yards receiving_tds receiving_yards_after_catch receiving_air_yards target_share air_yards_share receiving_epa wopr racr',
  'Defense & kicking': 'games def_tackles_solo def_tackles_for_loss def_sacks def_qb_hits def_interceptions def_pass_defended def_fumbles_forced fg_att fg_made fg_pct',
  Fantasy: 'games targets passing_yards rushing_yards receiving_yards fantasy_points_ppr',
  Hitting: 'gamesPlayed pa bip hits doubles triples homeRuns runs rbi stolenBases strikeOuts baseOnBalls ba obp slg ops kRate bbRate kMinusBb babip iso woba est_ba est_slg est_woba est_woba_minus_woba_diff',
  Pitching: 'gamesPlayed gamesStarted outs pa bip wins saves holds strikeOuts baseOnBalls homeRuns era whip ba slg kRate bbRate kMinusBb strikeoutsPer9Inn walksPer9Inn homeRunsPer9Inn strikeoutWalkRatio woba est_ba est_slg est_woba xera est_woba_minus_woba_diff',
};
const percentages = new Set('fieldGoalPct threePointFieldGoalPct freeThrowPct usageRate ts efg threeRate ftRate target_share air_yards_share fg_pct kRate bbRate'.split(' '));

const panel = document.querySelector('[data-leaderboard]');
if (panel) {
  const get = id => panel.querySelector('#' + id);
  const boardSelect = get('stat-board');
  const metricSelect = get('stat-metric');
  const from = get('stat-min');
  const to = get('stat-max');
  const search = get('stat-search');
  const position = get('stat-position');
  const team = get('stat-team');
  const limit = get('stat-limit');
  const direction = get('stat-direction');
  const table = get('stat-table');
  const status = get('stat-status');
  const filters = new Map();
  const normalize = value => value.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
  const option = (label, key) => new Option(label, key);
  const periodSelect = get('stat-period');
  let snapshot;
  let periodBoards;
  let board;
  let keys;
  // nflverse stores field-goal percentage as a fraction. Filters use percentage points.
  const valueOf = (row, stat) => {
    const value = row.stats[stat];
    return stat === 'fg_pct' && value != null ? value * 100 : value;
  };
  const format = (row, stat) => {
    const value = valueOf(row, stat);
    if (value == null) return '—';
    return value.toFixed(1) + (percentages.has(stat) ? '%' : '');
  };

  function render() {
    const key = metricSelect.value;
    const volume = get('stat-volume').value;
    const minimum = get('stat-volume-min').value;
    const terms = normalize(search.value).split(' ').filter(Boolean);
    const rows = board.rows.filter(row =>
      terms.every(term => normalize(row.name).includes(term)) &&
      (!position.value || row.position === position.value) &&
      (!team.value || row.team === team.value) &&
      (!volume || minimum === '' || (valueOf(row, volume) != null && valueOf(row, volume) >= Number(minimum))) &&
      [...filters].every(([stat, [lo, hi]]) => {
        const value = valueOf(row, stat);
        return value != null && (lo === '' || value >= Number(lo)) && (hi === '' || value <= Number(hi));
      })
    );
    rows.sort((a,b) => {
      const x = valueOf(a, key), y = valueOf(b, key);
      if (x == null || y == null) return Number(x == null) - Number(y == null) || a.name.localeCompare(b.name);
      return (direction.value === 'asc' ? x-y : y-x) || a.name.localeCompare(b.name);
    });
    const hasTeam = board.rows.some(row => row.team);
    const hasPosition = board.rows.some(row => row.position);
    const head = table.tHead.rows[0];
    head.replaceChildren();
    for (const label of ['#', 'Player', ...(hasTeam ? ['Team'] : []), ...(hasPosition ? ['Position'] : []), ...keys]) {
      const cell = document.createElement('th');
      cell.scope = 'col';
      if (Object.hasOwn(board.metrics,label)) {
        const control = document.createElement('button');
        control.type = 'button';
        control.className = 'secondary';
        control.textContent = board.metrics[label];
        if (label === key) cell.setAttribute('aria-sort', direction.value === 'asc' ? 'ascending' : 'descending');
        control.addEventListener('click', () => {
          if (metricSelect.value === label) direction.value = direction.value === 'asc' ? 'desc' : 'asc';
          else selectMetric(label);
          render();
        });
        cell.append(control);
      } else cell.textContent = label;
      head.append(cell);
    }
    const visible = rows.slice(0, Number(limit.value));
    const body = document.createDocumentFragment();
    for (const [index,row] of visible.entries()) {
      const tr = document.createElement('tr');
      const values = [index+1,row.name,...(hasTeam ? [row.team] : []),...(hasPosition ? [row.position] : []),
        ...keys.map(stat => format(row, stat))];
      for (const value of values) {
        const td = tr.insertCell();
        td.textContent = value || '—';
      }
      body.append(tr);
    }
    table.tBodies[0].replaceChildren(body);
    status.textContent = rows.length ? 'Showing ' + visible.length + ' of ' + rows.length + ' matching players.' : board.rows.length ? 'No players match these filters.' : 'No regular-season player stats in this period.';
    get('stat-applied').textContent = [...filters].map(([stat,[lo,hi]]) =>
      board.metrics[stat] + ' ' + (lo === '' ? 'any minimum' : '≥ ' + lo) + ' / ' + (hi === '' ? 'any maximum' : '≤ ' + hi)).join(' · ');
  }
  function selectMetric(key) {
    metricSelect.value = key;
    direction.value = ['era','xera','est_woba','woba'].includes(key) && board.label === 'Pitching' ? 'asc' : 'desc';
    [from.value,to.value] = filters.get(key) || ['',''];
  }
  function selectBoard() {
    board = periodBoards[Number(boardSelect.value)];
    const preferred = (columnOrder[board.label] || '').split(' ').filter(key => Object.hasOwn(board.metrics, key));
    keys = [...new Set([...preferred, ...Object.keys(board.metrics)])];
    filters.clear();
    get('stat-volume-min').value = '';
    metricSelect.replaceChildren(...keys.map(key => option(board.metrics[key],key)));
    get('stat-volume').replaceChildren(option('None',''),...keys.map(key => option(board.metrics[key],key)));
    for (const [control,key] of [[team,'team'],[position,'position']]) {
      const values = [...new Set(board.rows.map(row => row[key]).filter(Boolean))].sort();
      control.closest('label').hidden = !values.length;
      control.replaceChildren(option('All',''),...values.map(value => option(value,value)));
    }
    selectMetric(board.default);
    render();
  }
  function selectPeriod() {
    const label = board?.label;
    periodBoards = snapshot.recent?.[periodSelect.value] || snapshot.boards;
    boardSelect.replaceChildren(...periodBoards.map((item, i) => option(item.label, String(i))));
    boardSelect.value = String(Math.max(0, periodBoards.findIndex(item => item.label === label)));
    get('stat-date').textContent = snapshot.season + ' regular season · ' +
      (periodSelect.value && snapshot.recentThrough ? 'Window through ' + snapshot.recentThrough + ' · ' : '') +
      'Retrieved ' + new Date(snapshot.capturedAt).toLocaleString();
    selectBoard();
  }
  periodSelect.addEventListener('change', selectPeriod);
  boardSelect.addEventListener('change',selectBoard);
  metricSelect.addEventListener('change',() => {selectMetric(metricSelect.value);render();});
  for (const control of [from,to]) control.addEventListener('input',() => {
    if (from.value === '' && to.value === '') filters.delete(metricSelect.value);
    else filters.set(metricSelect.value,[from.value,to.value]);
    render();
  });
  for (const control of [search,team,position,limit,direction,get('stat-volume'),get('stat-volume-min')]) control.addEventListener('input',render);
  get('stat-reset').addEventListener('click',() => {
    search.value = '';
    selectBoard();
  });
  fetch('/platform/stats/' + panel.dataset.leaderboard + '.json.gz')
    .then(response => {if (!response.ok) throw Error('Snapshot unavailable'); return new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).json();})
    .then(data => {
      for (const boards of [data.boards, ...Object.values(data.recent || {})]) {
        const boxScore = boards.find(item => item.label === 'Box score');
        const efficiency = boards.find(item => item.label === 'Efficiency & per 36');
        if (boxScore && efficiency) Object.assign(boxScore.metrics, efficiency.metrics);
      }
      snapshot = data;
      const periods = Object.keys(data.recent || {});
      periodSelect.replaceChildren(option('Full season', ''), ...periods.map(period => option(period, period)));
      get('stat-period-label').hidden = !periods.length;
      get('stat-source').textContent = data.source;
      get('stat-source').href = data.url;
      get('stat-controls').hidden = false;
      selectPeriod();
    })
    .catch(() => {status.textContent = 'The leaderboard snapshot is temporarily unavailable. Reload to try again.';});
}
