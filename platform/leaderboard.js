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
  let snapshot;
  let board;

  function render() {
    const key = metricSelect.value;
    const volume = get('stat-volume').value;
    const minimum = get('stat-volume-min').value;
    const terms = normalize(search.value).split(' ').filter(Boolean);
    const rows = board.rows.filter(row =>
      terms.every(term => normalize(row.name).includes(term)) &&
      (!position.value || row.position === position.value) &&
      (!team.value || row.team === team.value) &&
      (!volume || minimum === '' || (row.stats[volume] != null && row.stats[volume] >= Number(minimum))) &&
      [...filters].every(([stat, [lo, hi]]) => {
        const value = row.stats[stat];
        return value != null && (lo === '' || value >= Number(lo)) && (hi === '' || value <= Number(hi));
      })
    );
    rows.sort((a,b) => {
      const x = a.stats[key], y = b.stats[key];
      if (x == null || y == null) return Number(x == null) - Number(y == null) || a.name.localeCompare(b.name);
      return (direction.value === 'asc' ? x-y : y-x) || a.name.localeCompare(b.name);
    });
    const keys = [key, ...Object.keys(board.metrics).filter(stat => stat !== key)];
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
        ...keys.map(stat => row.stats[stat] == null ? '—' : String(row.stats[stat]))];
      for (const value of values) {
        const td = tr.insertCell();
        td.textContent = value || '—';
      }
      body.append(tr);
    }
    table.tBodies[0].replaceChildren(body);
    status.textContent = rows.length ? 'Showing ' + visible.length + ' of ' + rows.length + ' matching players.' : 'No players match these filters.';
    get('stat-applied').textContent = [...filters].map(([stat,[lo,hi]]) =>
      board.metrics[stat] + ' ' + (lo === '' ? 'any minimum' : '≥ ' + lo) + ' / ' + (hi === '' ? 'any maximum' : '≤ ' + hi)).join(' · ');
  }
  function selectMetric(key) {
    metricSelect.value = key;
    direction.value = ['era','xera','est_woba','woba'].includes(key) && board.label === 'Pitching' ? 'asc' : 'desc';
    [from.value,to.value] = filters.get(key) || ['',''];
  }
  function selectBoard() {
    board = snapshot.boards[Number(boardSelect.value)];
    filters.clear();
    get('stat-volume-min').value = '';
    metricSelect.replaceChildren(...Object.entries(board.metrics).map(([key,label]) => option(label,key)));
    get('stat-volume').replaceChildren(option('None',''),...Object.entries(board.metrics).map(([key,label]) => option(label,key)));
    for (const [control,key] of [[team,'team'],[position,'position']]) {
      const values = [...new Set(board.rows.map(row => row[key]).filter(Boolean))].sort();
      control.closest('label').hidden = !values.length;
      control.replaceChildren(option('All',''),...values.map(value => option(value,value)));
    }
    selectMetric(board.default);
    render();
  }
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
      snapshot = data;
      boardSelect.replaceChildren(...data.boards.map((item,i) => option(item.label,String(i))));
      get('stat-source').textContent = data.source;
      get('stat-source').href = data.url;
      get('stat-date').textContent = data.season + ' regular season · Retrieved ' + new Date(data.capturedAt).toLocaleString();
      get('stat-controls').hidden = false;
      selectBoard();
    })
    .catch(() => {status.textContent = 'The leaderboard snapshot is temporarily unavailable. Reload to try again.';});
}
