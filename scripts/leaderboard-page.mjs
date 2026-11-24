export function leaderboardPage(sport) {
  return `<section class="pro-panel" data-leaderboard="${sport.toLowerCase()}">
    <nav class="leaderboard-sports" aria-label="Sport">
      ${['NFL', 'NBA', 'MLB'].map(league => `<a href="/${league.toLowerCase()}/leaderboards/"${league === sport ? ' aria-current="page"' : ''}>${league}</a>`).join('')}
    </nav>
    <p><span id="stat-date"></span> <a id="stat-source"></a></p>
    <div id="stat-controls" hidden>
      <div id="stat-presets" class="leaderboard-presets" role="group" aria-label="Leaderboard presets"></div>
      <div class="pro-controls leaderboard-controls">
        <label id="stat-period-label" hidden>Period<select id="stat-period"></select></label>
        <label>Board<select id="stat-board"></select></label>
        <label class="leaderboard-search">Search players<input type="search" id="stat-search" placeholder="Player name"></label>
        <label>Stat<select id="stat-metric"></select></label>
        <label>Sort direction<select id="stat-direction"><option value="desc">Highest first</option><option value="asc">Lowest first</option></select></label>
      </div>
      <details id="stat-filters" class="leaderboard-filters">
        <summary>Filters and rows</summary>
        <div class="pro-controls leaderboard-controls">
        <label>Team<select id="stat-team"></select></label>
        <label>Position<select id="stat-position"></select></label>
        <label>Stat minimum<input type="number" step="any" id="stat-min"></label>
        <label>Stat maximum<input type="number" step="any" id="stat-max"></label>
        <label>Sample size stat<select id="stat-volume"></select></label>
        <label>Minimum sample size<input type="number" step="any" id="stat-volume-min"></label>
        <label>Rows shown<select id="stat-limit"><option>50</option><option>100</option><option>250</option><option value="10000">All</option></select></label>
        <button type="button" id="stat-reset" class="secondary">Clear filters</button>
        </div>
      <p class="fine">Stat thresholds stay active when you switch stats. Use a sample minimum such as attempts, minutes or plate appearances to compare rate stats.</p>
      </details>
      <div id="stat-applied" class="leaderboard-presets" role="group" aria-label="Active filters" hidden></div>
      <div class="pro-actions leaderboard-view-actions">
        <button type="button" id="stat-view" class="secondary" aria-controls="stat-table"></button>
        <button type="button" id="stat-share" class="secondary">Copy view link</button>
      </div>
      <p id="stat-share-status" class="fine" role="status"></p>
      <label id="stat-share-fallback" hidden>View link<input id="stat-share-url" readonly></label>
      <p id="stat-scroll-hint" class="fine" hidden>Swipe the table to see more stats.</p>
    </div>
    ${sport === 'NBA' ? '<details class="leaderboard-filters"><summary>Fantasy scoring and ranks</summary><p class="fine">Yahoo points use 1 per point, 1.2 per rebound, 1.5 per assist, 3 per steal or block, and −1 per turnover. The 9-category rank combines per-game points, threes, rebounds, assists, steals, blocks, turnovers, field-goal percentage and free-throw percentage. Shooting percentages are weighted by attempts. Category scores use players averaging at least 15 minutes as the baseline, and rank 1 is best.</p></details>' : ''}
    ${sport === 'NFL' ? '<details class="leaderboard-filters"><summary>How snap percentages work</summary><p class="fine">Snap percentages average each player’s game-level share for the selected period. Offense, defense and special teams are shown separately. A dash indicates missing snap data for at least one game.</p></details>' : ''}
    <p id="stat-status" role="status">Loading leaderboard…</p>
    <div class="pro-table" tabindex="0" role="region" aria-label="${sport} leaderboard"><table id="stat-table"><thead><tr></tr></thead><tbody></tbody></table></div>
    <dialog id="stat-player" class="leaderboard-player" aria-labelledby="stat-player-name">
      <form method="dialog">
        <button type="submit" class="secondary" autofocus>Close</button>
      </form>
      <h2 id="stat-player-name"></h2>
      <p id="stat-player-context" class="fine"></p>
      <dl id="stat-player-stats"></dl>
    </dialog>
    <noscript>Enable JavaScript to search and filter this leaderboard.</noscript>
    <script defer src="/platform/leaderboard.js"></script>
  </section>`;
}
