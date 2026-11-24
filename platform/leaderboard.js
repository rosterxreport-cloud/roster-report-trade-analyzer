// Keep column order independent of the active sort and filter.
const columnOrder = {
  'Box score': 'gamesPlayed avgMinutes avgPoints avgRebounds avgAssists avgSteals avgBlocks avgTurnovers avgFouls avgFieldGoalsMade avgFieldGoalsAttempted avgThreePointFieldGoalsMade avgThreePointFieldGoalsAttempted avgFreeThrowsMade avgFreeThrowsAttempted minutes points rebounds assists steals blocks turnovers fouls fieldGoalsMade fieldGoalsAttempted threePointFieldGoalsMade threePointFieldGoalsAttempted freeThrowsMade freeThrowsAttempted doubleDouble tripleDouble flagrantFouls technicalFouls ejections fieldGoalPct threePointFieldGoalPct freeThrowPct fantasyPointsPerGame pointsPerMinute fantasyPointsPerMinute nineCatRank usageRate ts efg threeRate ftRate astTo pts36 reb36 ast36 stocks36',
  'Efficiency & per 36': 'gamesPlayed minutes fieldGoalsAttempted usageRate ts efg threeRate ftRate astTo pts36 reb36 ast36 stocks36',
  'Fantasy basketball': 'nineCatRank fantasyPointsPerGame fantasyPointsPerMinute pointsPerMinute gamesPlayed avgMinutes avgPoints avgThreePointFieldGoalsMade avgRebounds avgAssists avgSteals avgBlocks avgTurnovers fieldGoalPct freeThrowPct',
  Passing: 'games offense_pct attempts passing_yards passing_tds passing_interceptions sacks_suffered passing_air_yards passing_epa passing_cpoe pacr',
  Rushing: 'games offense_pct carries rushing_yards rushing_tds rushing_20 rushing_epa',
  Receiving: 'games offense_pct targets receptions receiving_yards receiving_tds receiving_yards_after_catch receiving_air_yards target_share air_yards_share receiving_epa wopr racr',
  'Defense & kicking': 'games defense_pct st_pct def_tackles_solo def_tackles_for_loss def_sacks def_qb_hits def_interceptions def_pass_defended def_fumbles_forced fg_att fg_made fg_pct',
  Fantasy: 'games offense_pct targets passing_yards rushing_yards receiving_yards fantasy_points_ppr',
  Hitting: 'gamesPlayed pa bip hits doubles triples homeRuns runs rbi stolenBases strikeOuts baseOnBalls ba obp slg ops kRate bbRate kMinusBb babip iso woba est_ba est_slg est_woba est_woba_minus_woba_diff',
  Pitching: 'gamesPlayed gamesStarted outs pa bip wins saves holds strikeOuts baseOnBalls homeRuns era whip ba slg kRate bbRate kMinusBb strikeoutsPer9Inn walksPer9Inn homeRunsPer9Inn strikeoutWalkRatio woba est_ba est_slg est_woba xera est_woba_minus_woba_diff',
};
const percentages = new Set('fieldGoalPct threePointFieldGoalPct freeThrowPct usageRate ts efg threeRate ftRate target_share air_yards_share fg_pct offense_pct defense_pct st_pct kRate bbRate'.split(' '));

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
  const viewButton = get('stat-view');
  const mobile = matchMedia('(max-width: 760px)');
  let compact = mobile.matches;
  let chosenView = false;
  get('stat-filters').open = !compact;
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
    if (stat === 'nineCatRank') return String(value);
    return value.toFixed(1) + (percentages.has(stat) ? '%' : '');
  };

  const sport = panel.dataset.leaderboard;
  const storageKey = 'rr.leaderboard.v1.' + sport;
  const volumeSelect = get('stat-volume');
  const volumeMinimum = get('stat-volume-min');
  const dialog = get('stat-player');
  const presets = {
    nba: [['9-Cat', 'Fantasy basketball', 'nineCatRank'], ['Fantasy points', 'Fantasy basketball', 'fantasyPointsPerGame'], ['Scoring leaders', 'Box score', 'avgPoints']],
    nfl: [['Snap leaders', 'Fantasy', 'offense_pct'], ['PPR leaders', 'Fantasy', 'fantasy_points_ppr'], ['Receiving leaders', 'Receiving', 'receiving_yards']],
    mlb: [['Hitters', 'Hitting', 'ops'], ['Pitchers', 'Pitching', 'era']],
  };
  const hashPrefix = '#view=';
  let presetButtons = [];

  function readView() {
    // A shared view takes priority over this browser’s preferences.
    for (const read of [
      () => location.hash.startsWith(hashPrefix) ? decodeURIComponent(location.hash.slice(hashPrefix.length)) : null,
      () => localStorage.getItem(storageKey),
    ]) {
      try {
        const state = JSON.parse(read());
        if (state && typeof state === 'object' && !Array.isArray(state)) return state;
      } catch {}
    }
    return {};
  }

  function viewState() {
    return {
      period: periodSelect.value, board: board.label, metric: metricSelect.value,
      direction: direction.value, team: team.value, position: position.value,
      search: search.value, limit: limit.value, volume: volumeSelect.value, minimum: volumeMinimum.value,
      filters: [...filters], layout: chosenView ? panel.dataset.view : '',
    };
  }

  function saveView() {
    try { localStorage.setItem(storageKey, JSON.stringify(viewState())); } catch {}
  }

  function setOption(select, value) {
    if ([...select.options].some(option => option.value === value)) select.value = value;
  }

  const numericInput = value => typeof value === 'string' && value.trim() && Number.isFinite(Number(value)) ? value : '';

  function restoreView(state) {
    setOption(periodSelect, state.period);
    selectPeriod(state.board);
    for (const [control, value] of [[team, state.team], [position, state.position],
        [volumeSelect, state.volume], [limit, state.limit]]) setOption(control, value);
    search.value = typeof state.search === 'string' ? state.search.slice(0, 120) : '';
    volumeMinimum.value = volumeSelect.value ? numericInput(state.minimum) : '';
    for (const entry of Array.isArray(state.filters) ? state.filters : []) {
      if (!Array.isArray(entry) || !keys.includes(entry[0]) || !Array.isArray(entry[1])) continue;
      const [lo, hi] = entry[1].map(numericInput);
      if (lo || hi) filters.set(entry[0], [lo || '', hi || '']);
    }
    selectMetric(keys.includes(state.metric) ? state.metric : board.default);
    setOption(direction, state.direction);
    if (state.layout === 'compact' || state.layout === 'table') {
      chosenView = true;
      compact = state.layout === 'compact';
    }
  }

  function initPresets() {
    presetButtons = (presets[sport] || []).map(([label, target, metric]) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'secondary';
      button.textContent = label;
      button.addEventListener('click', () => {
        boardSelect.value = String(periodBoards.findIndex(item => item.label === target));
        selectBoard();
        selectMetric(metric);
        render();
      });
      return {button, target, metric};
    });
    get('stat-presets').replaceChildren(...presetButtons.map(item => item.button));
  }

  function showPlayer(row) {
    get('stat-player-name').textContent = row.name;
    get('stat-player-context').textContent = [row.team, row.position, periodSelect.value || 'Full season'].filter(Boolean).join(' · ');
    const selected = metricSelect.value;
    get('stat-player-stats').replaceChildren(...[selected, ...keys.filter(key => key !== selected)].map(key => {
      const entry = document.createElement('div');
      const label = document.createElement('dt');
      const value = document.createElement('dd');
      label.textContent = board.metrics[key];
      value.textContent = format(row, key);
      entry.append(label, value);
      return entry;
    }));
    dialog.showModal();
  }

  function renderFilters() {
    const container = get('stat-applied');
    const buttons = [];
    const add = (label, remove) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'secondary';
      button.textContent = label + ' ×';
      button.setAttribute('aria-label', 'Remove ' + label);
      button.addEventListener('click', () => {
        const index = buttons.indexOf(button);
        remove();
        render();
        (container.children[Math.min(index, container.children.length - 1)] || search).focus();
      });
      buttons.push(button);
    };
    if (periodSelect.value) add(periodSelect.value, () => {
      periodSelect.value = '';
      changePeriod();
    });
    if (search.value.trim()) add('Search: ' + search.value.trim(), () => { search.value = ''; });
    if (team.value) add(team.value, () => { team.value = ''; });
    if (position.value) add(position.value, () => { position.value = ''; });
    if (volumeSelect.value && volumeMinimum.value !== '') {
      add(board.metrics[volumeSelect.value] + ' ≥ ' + volumeMinimum.value, () => { volumeMinimum.value = ''; });
    }
    for (const [stat, [lo, hi]] of filters) {
      const bounds = [lo === '' ? '' : '≥ ' + lo, hi === '' ? '' : '≤ ' + hi].filter(Boolean).join(' · ');
      add(board.metrics[stat] + ' ' + bounds, () => {
        filters.delete(stat);
        if (metricSelect.value === stat) from.value = to.value = '';
      });
    }
    container.replaceChildren(...buttons);
    container.hidden = !buttons.length;
  }

  get('stat-share').addEventListener('click', async () => {
    const url = new URL(location.href);
    url.hash = hashPrefix + encodeURIComponent(JSON.stringify(viewState()));
    const fallback = get('stat-share-fallback');
    const field = get('stat-share-url');
    const feedback = get('stat-share-status');
    try {
      await navigator.clipboard.writeText(url.href);
      fallback.hidden = true;
      feedback.textContent = 'View link copied.';
    } catch {
      feedback.textContent = 'Copy the link below.';
      fallback.hidden = false;
      field.value = url.href;
      field.select();
    }
  });

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
    const hasTeam = !compact && board.rows.some(row => row.team);
    const hasPosition = !compact && board.rows.some(row => row.position);
    const visibleKeys = compact ? [key] : keys;
    panel.dataset.view = compact ? 'compact' : 'table';
    viewButton.textContent = compact ? 'Show full table' : 'Show compact view';
    get('stat-scroll-hint').hidden = compact || !mobile.matches || !rows.length;
    const head = table.tHead.rows[0];
    head.replaceChildren();
    for (const label of ['#', 'Player', ...(hasTeam ? ['Team'] : []), ...(hasPosition ? ['Position'] : []), ...visibleKeys]) {
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
        ...visibleKeys.map(stat => format(row, stat))];
      for (const value of values) {
        const td = tr.insertCell();
        td.textContent = value || '—';
      }
      const playerLink = document.createElement('button');
      playerLink.type = 'button';
      playerLink.className = 'leaderboard-player-link';
      playerLink.textContent = row.name;
      playerLink.addEventListener('click', () => showPlayer(row));
      tr.cells[1].replaceChildren(playerLink);
      if (compact && (row.team || row.position)) {
        const detail = document.createElement('span');
        detail.className = 'leaderboard-player-detail';
        detail.textContent = [row.team, row.position].filter(Boolean).join(' · ');
        tr.cells[1].append(detail);
      }
      body.append(tr);
    }
    table.tBodies[0].replaceChildren(body);
    status.textContent = rows.length ? 'Showing ' + visible.length + ' of ' + rows.length + ' matching players.' : board.rows.length ? 'No players match these filters.' : 'No regular-season player stats in this period.';
    for (const {button, target, metric} of presetButtons) {
      button.hidden = !periodBoards.some(item => item.label === target && Object.hasOwn(item.metrics, metric));
      button.setAttribute('aria-pressed', String(board.label === target && key === metric));
    }
    renderFilters();
    saveView();
  }
  function selectMetric(key) {
    metricSelect.value = key;
    const lowerFirst = key === 'nineCatRank' || (board.label === 'Pitching' && ['era', 'xera', 'est_woba', 'woba'].includes(key));
    direction.value = lowerFirst ? 'asc' : 'desc';
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
  }
  function selectPeriod(label = board?.label) {
    periodBoards = snapshot.recent?.[periodSelect.value] || snapshot.boards;
    boardSelect.replaceChildren(...periodBoards.map((item, i) => option(item.label, String(i))));
    boardSelect.value = String(Math.max(0, periodBoards.findIndex(item => item.label === label)));
    get('stat-date').textContent = snapshot.season + ' regular season · ' +
      (periodSelect.value && snapshot.recentThrough ? 'Window through ' + snapshot.recentThrough + ' · ' : '') +
      'Retrieved ' + new Date(snapshot.capturedAt).toLocaleString();
    selectBoard();
  }
  function changePeriod() {
    const state = viewState();
    restoreView(state);
  }
  viewButton.addEventListener('click', () => {
    chosenView = true;
    compact = !compact;
    table.parentElement.scrollLeft = 0;
    render();
  });
  mobile.addEventListener('change', () => {
    if (!chosenView) compact = mobile.matches;
    if (board) render();
  });
  periodSelect.addEventListener('change', () => { changePeriod(); render(); });
  boardSelect.addEventListener('change', () => { selectBoard(); render(); });
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
    render();
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
      initPresets();
      restoreView(readView());
      render();
    })
    .catch(() => {status.textContent = 'The leaderboard snapshot is temporarily unavailable. Reload to try again.';});
}
