"""Create an approved full-week release using the existing private NBA producer."""
import concurrent.futures
import datetime
import hashlib
import json
import pathlib
import subprocess

from nba_release import authorize

WEEK_START = datetime.date(2026, 11, 30)
# ESPN daily counts reconciled after the NBA announced the 2026 Cup bracket.
GAME_COUNTS = (7, 8, 11, 3, 2, 2, 7)
CUP_GAMES = {
    datetime.date(2026, 12, 4): {('PHI', 'ATL'), ('SAS', 'DAL')},
    datetime.date(2026, 12, 5): {('BOS', 'DET'), ('MEM', 'POR')},
}
TEAMS = dict(enumerate('ATL BOS NOP CHI CLE DAL DEN DET GSW HOU IND LAC LAL MIA MIL MIN BKN NYK ORL PHI PHX POR SAC SAS OKC UTA WAS TOR MEM CHA'.split(), 1))
ESPN = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/'
WEEKLY_PATH = 'nba/roster-weekly.json'


def board_url(day):
    return f'{ESPN}scoreboard?dates={day:%Y%m%d}&limit=1000'


def roster_url(team):
    return f'{ESPN}teams/{team}/roster'


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def capture_week(fetch):
    dates = [WEEK_START + datetime.timedelta(days=i) for i in range(7)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        boards = dict(zip((board_url(day) for day in dates), pool.map(fetch, (board_url(day) for day in dates))))
        games, schedule_days, team_ids = [], [], set()
        for day, count in zip(dates, GAME_COUNTS):
            board = boards[board_url(day)]
            day_games = []
            for event in board['events']:
                competition = event['competitions'][0]
                team = {p['homeAway']: int(p['team']['id']) for p in competition['competitors']}
                if set(team) != {'home', 'away'} or not set(team.values()) <= TEAMS.keys() or competition['status']['type']['state'] != 'pre':
                    raise ValueError(f'Unverified NBA matchup on {day}')
                team_ids.update(team.values())
                day_games.append(dict(id=str(event['id']), startsAt=event['date'], home=TEAMS[team['home']], away=TEAMS[team['away']]))
            if len(day_games) != count or (day in CUP_GAMES and {(g['away'], g['home']) for g in day_games} != CUP_GAMES[day]):
                raise ValueError(f'Updated NBA schedule does not match the verified slate on {day}')
            games.extend(day_games)
            schedule_days.append(dict(day=day.isoformat(), gameIds=[g['id'] for g in day_games], sourceHash=fingerprint(board)))
        urls = [roster_url(team) for team in sorted(team_ids)]
        rosters = dict(zip(urls, pool.map(fetch, urls)))
    identities = []
    for team in sorted(team_ids):
        roster = rosters[roster_url(team)]['athletes']
        if not roster:
            raise ValueError(f'Team roster is empty: {TEAMS[team]}')
        identities.extend(dict(id=str(athlete['id']), team=TEAMS[team]) for athlete in roster)
    return dates, {**boards, **rosters}, dict(weekStart=WEEK_START.isoformat(), games=games, scheduleDays=schedule_days, roster=identities)


def build_release(producer, data, frozen_manifest, repo, work):
    dates, captures, manifest = capture_week(producer.fetch)
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
        list(pool.map(producer.injury, (day.isoformat() for day in dates)))
    original_fetch = producer.fetch
    producer.fetch = captures.__getitem__
    try:
        for day in dates:
            snapshot = producer.ROOT / 'forward' / 'predictions' / f'{day}.json'
            snapshot.unlink(missing_ok=True)
            producer.forecast(day, data, frozen_manifest)
    finally:
        producer.fetch = original_fetch

    paths, absences = [], []
    scheduled = {g['id']: g for g in manifest['games']}
    simulator_hash = hashlib.sha256((producer.ROOT/'src'/'simulate_slate.py').read_bytes()).hexdigest()
    for day in dates:
        source = producer.ROOT / 'forward' / 'predictions' / f'{day}.json'
        raw = source.read_bytes()
        snapshot = json.loads(raw)
        captured = snapshot['createdAt']
        release = authorize(producer.ROOT, snapshot, repo / 'config/nba-incumbent-release.json')
        evidence_path = producer.ROOT / 'data' / 'injury_reports' / f'{day}.meta.json'
        evidence = json.loads(evidence_path.read_text()) if evidence_path.is_file() else None
        players = []
        for row in snapshot['predictions']:
            game = scheduled[str(row['game'])]
            team = TEAMS[row['team']]
            if team not in (game['home'], game['away']):
                raise ValueError('NBA model team does not match the verified fixture')
            if row['status_asof_capture'] == 'Out' and evidence:
                absences.append(dict(id=str(row['player']), gameId=game['id'], asOf=evidence['capturedAt'], evidenceHash=evidence['sha256']))
            if row['model']['MIN'] <= 0:
                continue
            opponent = game['away'] if team == game['home'] else game['home']
            players.append(dict(id=str(row['player']), name=row['name'], team=team, opponent=opponent,
                                gameId=game['id'], startsAt=row['start'], statline=row['model'],
                                projection=row['DraftKings'], fantasyPoints={k:row[k] for k in ('Yahoo','ESPN','DraftKings')}))
        artifact = dict(schemaVersion=1, kind='projections', sport='NBA', publishApproved=True,
                        capturedAt=captured, validUntil=min(g['start'] for g in snapshot['fixtures']),
                        provenance=dict(model=snapshot['model'], modelHash=snapshot['modelFingerprint'],
                                        sourceHash=hashlib.sha256(raw).hexdigest(),
                                        simulatorHash=simulator_hash,
                                        releaseAuthorization=release), players=players)
        target = work / f'weekly-{day}.json'
        target.write_text(json.dumps(artifact, allow_nan=False))
        paths.append(str(target))
    manifest['absences'] = absences
    schedule_path = work / 'weekly-game-manifest.json'
    schedule_path.write_text(json.dumps(manifest))
    output = work / 'roster-weekly.json'
    result = subprocess.run(['node', str(repo / 'scripts/pro/build-nba-roster-weekly.mjs'),
                             str(schedule_path), str(output), *paths], capture_output=True, text=True, timeout=30)
    if result.returncode:
        message = next((line for line in result.stderr.splitlines() if line.startswith('Error:')), 'Full-week NBA validation failed')
        raise ValueError(message)
    return json.loads(output.read_bytes())
