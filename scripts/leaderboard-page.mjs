export function leaderboardPage(sport) {
  return `<section class="pro-panel" data-leaderboard="${sport.toLowerCase()}">
    <p><a href="/nfl/leaderboards/">NFL</a> · <a href="/nba/leaderboards/">NBA</a> · <a href="/mlb/leaderboards/">MLB</a></p>
    <p><span id="stat-date"></span> <a id="stat-source"></a></p>
    <div id="stat-controls" hidden>
      <div class="pro-controls leaderboard-controls">
        <label>Board<select id="stat-board"></select></label>
        <label>Search players<input type="search" id="stat-search"></label>
        <label>Team<select id="stat-team"></select></label>
        <label>Position<select id="stat-position"></select></label>
        <label>Stat<select id="stat-metric"></select></label>
        <label>Sort direction<select id="stat-direction"><option value="desc">Highest first</option><option value="asc">Lowest first</option></select></label>
        <label>Stat minimum<input type="number" step="any" id="stat-min"></label>
        <label>Stat maximum<input type="number" step="any" id="stat-max"></label>
        <label>Sample size stat<select id="stat-volume"></select></label>
        <label>Minimum sample size<input type="number" step="any" id="stat-volume-min"></label>
        <label>Rows shown<select id="stat-limit"><option>50</option><option>100</option><option>250</option><option value="10000">All</option></select></label>
        <button type="button" id="stat-reset" class="secondary">Clear filters</button>
      </div>
      <p class="fine">Stat thresholds stay active when you switch stats. Use a sample minimum such as attempts, minutes or plate appearances to compare rate stats.</p>
      <p id="stat-applied" class="fine"></p>
    </div>
    <p id="stat-status" role="status">Loading leaderboard…</p>
    <div class="pro-table" tabindex="0" role="region" aria-label="${sport} leaderboard"><table id="stat-table"><thead><tr></tr></thead><tbody></tbody></table></div>
    <noscript>Enable JavaScript to search and filter this leaderboard.</noscript>
    <script defer src="/platform/leaderboard.js"></script>
  </section>`;
}
