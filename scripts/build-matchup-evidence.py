#!/usr/bin/env python3
"""Descriptive defensive results only. Never fit, adjust or run a projection model."""
import argparse, datetime as dt, hashlib, io, json
from pathlib import Path
from urllib.request import Request, urlopen
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.parquet'
FIELDS = ['attempts', 'passing_yards', 'passing_tds', 'passing_interceptions', 'sacks_suffered', 'carries', 'rushing_yards', 'rushing_tds', 'targets', 'receptions', 'receiving_yards', 'receiving_tds', 'fantasy_points_ppr']

def leaders(rows):
    """No future games; tied leaders are deliberately unclassified."""
    result = {}
    for team, group in rows[rows.position == 'WR'].groupby('team'):
        counts = group.groupby('player_id').agg(targets=('targets', 'sum'), games=('game_id', 'nunique'))
        counts['rate'] = counts.targets / counts.games
        top = counts[counts.rate == counts.rate.max()]
        if len(top) == 1 and float(top.iloc[0].rate) > 0:
            result[team] = str(top.index[0])
    return result

def summarize(rows, games):
    result = {}
    for defense, count in games.items():
        group = rows[rows.opponent_team == defense]
        # No position rows can mean a true zero only with a verified full-game denominator.
        totals = {field: float(group[field].sum()) for field in FIELDS}
        result[str(defense)] = {'games': int(count), 'totals': totals,
            'perGame': {field: round(value / count, 6) for field, value in totals.items()}}
    qualified = [r for r in result.values() if r['games'] >= 3]
    for row in qualified:
        row['mostPointsRank'] = 1 + sum(r['perGame']['fantasy_points_ppr'] > row['perGame']['fantasy_points_ppr'] for r in qualified)
        row['rankedDefenses'] = len(qualified)
    return result

def build(stats, season, through_week, source_hash, captured_at):
    required = {'player_id', 'position', 'team', 'opponent_team', 'season', 'season_type', 'week', 'game_id', *FIELDS}
    if not required <= set(stats):
        raise ValueError('Missing matchup source columns')
    rows = stats[(stats.season == season) & (stats.season_type == 'REG') & (stats.week.between(1, through_week))].copy()
    if set(map(int, rows.week.unique())) != set(range(1, through_week + 1)):
        raise ValueError('Incomplete matchup week coverage')
    # Source contains team-only defensive rows without player identities. They
    # establish game coverage but cannot contribute to offensive position splits.
    if rows[['team', 'opponent_team', 'game_id', *FIELDS]].isna().any().any():
        raise ValueError('Missing matchup observations')
    if ((rows.player_id.isna() | rows.position.isna()) & ((rows.attempts + rows.carries + rows.targets) > 0)).any():
        raise ValueError('Unidentified offensive production')
    if rows[rows.position.isin(['QB', 'RB', 'WR', 'TE'])].player_id.isna().any() or rows[rows.player_id.notna()].duplicated(['player_id', 'week']).any():
        raise ValueError('Duplicate or missing matchup observations')
    if not all(pd.to_numeric(rows[f], errors='raise').map(lambda v: float('-inf') < v < float('inf')).all() for f in FIELDS):
        raise ValueError('Nonfinite matchup statistics')
    games = rows.groupby('opponent_team').game_id.nunique()
    if len(games) != 32:
        raise ValueError('Expected all 32 defenses in source')
    # Count each defense's games once, including games with zero positional production.
    positions = {position: summarize(rows[rows.position == position], games) for position in ['QB', 'RB', 'WR', 'TE']}
    selected = []
    pregame_leaders = {int(week): leaders(rows[rows.week < week]) for week in rows.week.unique()}
    for (team, week), current in rows[rows.position == 'WR'].groupby(['team', 'week']):
        leader = pregame_leaders[int(week)].get(team)
        matched = current[current.player_id == leader]
        if len(matched) == 1:
            selected.append(matched.iloc[0])
    lead_rows = pd.DataFrame(selected, columns=rows.columns)
    lead_games = lead_rows.groupby('opponent_team').game_id.nunique()
    return {'schemaVersion': 1, 'season': season, 'throughWeek': through_week, 'capturedAt': captured_at,
        'source': {'url': URL.format(season=season), 'sha256': source_hash}, 'minimumGames': 3,
        'ranking': 'Most PPR points allowed per game; rank 1 allows the most. Ties share rank.',
        'leadingReceiverDefinition': 'WR with the highest targets per recorded player-stat appearance for that team entering the game. Prior weeks only; tied leaders, Week 1 and games without a recorded appearance by the leader are excluded. This is not cornerback coverage data.',
        'currentLeaders': leaders(rows), 'positions': positions, 'leadingWR': summarize(lead_rows, lead_games)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stats', type=Path)
    parser.add_argument('--through-week', type=int)
    parser.add_argument('--expected-sha')
    parser.add_argument('--evidence', type=Path, default=ROOT / 'data/player-evidence.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'data/matchup-evidence.json')
    args = parser.parse_args()
    evidence = json.loads(args.evidence.read_text())
    week = args.through_week or evidence['throughWeek']
    # In the Tuesday candidate pipeline, take the candidate's completed-week boundary.
    if not 1 <= week <= 18:
        raise ValueError('Invalid matchup week')
    if args.stats:
        raw = args.stats.read_bytes()
    else:
        with urlopen(Request(URL.format(season=evidence['season']), headers={'User-Agent': 'RosterReportMatchups/1.0'}), timeout=60) as response:
            raw = response.read()
    digest = hashlib.sha256(raw).hexdigest()
    expected = args.expected_sha or next(s['sha256'] for s in evidence['sources'] if s['file'] == 'player_stats.parquet')
    if digest != expected:
        raise ValueError('Matchup source checksum mismatch')
    snapshot = build(pd.read_parquet(io.BytesIO(raw)), evidence['season'], week, digest, dt.datetime.now(dt.timezone.utc).isoformat())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix('.tmp')
    temp.write_text(json.dumps(snapshot, indent=2, allow_nan=False) + '\n')
    temp.replace(args.output)
    print(f'Validated 32 defensive matchups through Week {week}')

if __name__ == '__main__':
    main()
