export function nbaRosterPage() {
  return `<section class="pro-panel" id="nba-roster-tool">
  <form class="pro-form" id="nba-roster-form">
    <div class="pro-controls">
      <label>Scoring<select name="mode"><option value="nine">Standard 9-cat</option><option value="points">Yahoo points</option></select></label>
      <label>Stats period<select name="period"></select></label>
      <label>Teams in league<input name="league" type="number" min="4" max="30" value="12" required></label>
      <label>Starting slots<input name="slots" value="G, G, F, F, C, UTIL, UTIL" required></label>
    </div>
    <p class="fine">Use G, F, C and UTIL slots. Eligibility is based on the positions in the Toolkit leaderboard.</p>
    <label>Your roster<textarea name="roster" maxlength="4000" placeholder="One player per line" required></textarea></label>
    <p class="fine">Use names as shown in the <a href="/nba/leaderboards/">NBA leaderboard</a>.</p>
    <details>
      <summary>Simulate a trade</summary>
      <div class="pro-controls">
        <label>Send<textarea name="outgoing" maxlength="1000"></textarea></label>
        <label>Receive<textarea name="incoming" maxlength="1000"></textarea></label>
        <label>Add from waivers<textarea name="additions" maxlength="1000"></textarea></label>
        <label>Drop<textarea name="drops" maxlength="1000"></textarea></label>
      </div>
    </details>
    <div class="pro-actions"><button id="nba-roster-submit" disabled>Analyze roster</button><button id="nba-roster-clear" class="secondary" type="reset">Clear roster</button></div>
  </form>
  <p id="nba-roster-status" role="status">Loading NBA stats…</p>
  <div id="nba-roster-results"></div>
  <noscript>Enable JavaScript to analyze your roster.</noscript>
  <script type="module" src="/platform/nba-roster.js"></script>
</section>`;
}
