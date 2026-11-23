"""Fetch observed regular-season data and publish complete leaderboard snapshots."""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo
import csv
import datetime as dt
import io
import gzip
import json
import math
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1] / "platform/stats"
NFL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_{year}.csv"
ESPN_NBA = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
NBA = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/statistics/byathlete?region=us&lang=en&contentorigin=espn&season={year}&seasontype=2&limit=1000"
MLB_STATS = "https://statsapi.mlb.com/api/v1/stats?stats=season&group={group}&season={year}&sportIds=1&playerPool=ALL&limit=2000"
MLB = "https://baseballsavant.mlb.com/leaderboard/expected_statistics?type={kind}&year={year}&min=1&csv=true"

def read(url, file, inputs):
    if inputs:
        return (inputs / file).read_text(encoding="utf-8-sig")
    with urlopen(Request(url, headers={"User-Agent": "RosterReportLeaderboard/1.0"}), timeout=40) as response:
        return response.read().decode("utf-8-sig")

def number(value):
    try:
        value = float(value)
        return round(value, 5) if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None

def ratio(numerator, denominator, scale=1):
    return round(scale * numerator / denominator, 4) if denominator else None

def board(label, default, metrics, rows, recent=False):
    rows = list(rows)
    if (not recent and len(rows) < 20) or len({row["id"] for row in rows}) != len(rows):
        raise ValueError(f"Incomplete or duplicate player pool: {label}")
    if default not in metrics or (rows and not any(row["stats"].get(default) is not None for row in rows)):
        raise ValueError(f"Missing default stat: {label}")
    return dict(label=label, default=default, metrics=metrics, rows=rows)

def nfl(year, inputs, games=None, weekly=None):
    source = csv.DictReader(io.StringIO(read(NFL.format(year=year), "nfl.csv", inputs))) if games is None else nfl_recent_rows(weekly, games)
    labels = {
        "games":"Games", "attempts":"Pass attempts", "passing_yards":"Pass yards",
        "passing_tds":"Pass TD", "passing_interceptions":"INT", "passing_epa":"Passing EPA",
        "passing_cpoe":"CPOE (percentage points)", "passing_air_yards":"Passing air yards",
        "sacks_suffered":"Sacks taken", "pacr":"Passing air-yard conversion",
        "carries":"Carries", "rushing_yards":"Rush yards", "rushing_tds":"Rush TD",
        "rushing_epa":"Rushing EPA", "rushing_20":"20+ yard rushes",
        "targets":"Targets", "receptions":"Receptions", "receiving_yards":"Receiving yards",
        "receiving_tds":"Receiving TD", "receiving_epa":"Receiving EPA",
        "receiving_air_yards":"Receiving air yards", "receiving_yards_after_catch":"Yards after catch",
        "target_share":"Target share", "air_yards_share":"Air-yard share", "wopr":"WOPR",
        "racr":"Receiving air-yard conversion", "def_tackles_solo":"Solo tackles",
        "def_tackles_for_loss":"Tackles for loss", "def_sacks":"Sacks",
        "def_qb_hits":"QB hits", "def_interceptions":"Defensive INT", "def_pass_defended":"Passes defended",
        "def_fumbles_forced":"Forced fumbles", "fg_made":"Field goals made",
        "fg_att":"Field goal attempts", "fg_pct":"Field goal %",
        "fantasy_points_ppr":"PPR points",
    }
    groups = [
        ("Passing", "passing_yards", "attempts", ["games", *[k for k in labels if k.startswith("passing_")], "attempts","sacks_suffered","pacr"]),
        ("Rushing", "rushing_yards", "carries", ["games", "carries", *[k for k in labels if k.startswith("rushing_")]]),
        ("Receiving", "receiving_yards", "targets", ["games","targets","receptions", *[k for k in labels if k.startswith("receiving_")],"target_share","air_yards_share","wopr","racr"]),
        ("Defense & kicking", "def_tackles_solo", None, ["games", *[k for k in labels if k.startswith(("def_","fg_"))]]),
        ("Fantasy", "fantasy_points_ppr", None, ["games","fantasy_points_ppr","passing_yards","rushing_yards","receiving_yards","targets"]),
    ]
    rows = [r for r in source if r["season"] == str(year) and r["season_type"] == "REG"]
    result = []
    for label, default, volume, keys in groups:
        if games is not None:
            keys = [key for key in keys if key not in ("target_share", "air_yards_share", "wopr", "passing_cpoe")]
        players = []
        for r in rows:
            if volume and not number(r[volume]):
                continue
            if label == "Fantasy" and r["position"] not in ("QB","RB","WR","TE"):
                continue
            if label == "Defense & kicking" and not any(number(r[k]) for k in keys[1:]):
                continue
            stats = {key:number(r[key]) for key in keys}
            for key in ("target_share","air_yards_share"):
                if stats.get(key) is not None:
                    stats[key] = round(stats[key] * 100, 2)
            players.append(dict(id=r["player_id"], name=r["player_display_name"], team=r["recent_team"], position=r["position"], stats=stats))
        metrics = {k:labels[k] + (" (%)" if k in ("target_share","air_yards_share") else "") for k in keys}
        result.append(board(label, default, metrics, players, recent=games is not None))
    return result

def nba_efficiency(values):
    def stat(key): return values.get(key) or 0
    fga, fta, minutes = stat("fieldGoalsAttempted"), stat("freeThrowsAttempted"), stat("minutes")
    values.update(ts=ratio(stat("points"),2*(fga+.44*fta),100),
                  efg=ratio(stat("fieldGoalsMade")+.5*stat("threePointFieldGoalsMade"), fga,100),
                  astTo=ratio(stat("assists"),stat("turnovers")),
                  pts36=ratio(stat("points"),minutes,36), reb36=ratio(stat("rebounds"),minutes,36),
                  ast36=ratio(stat("assists"),minutes,36),
                  stocks36=ratio(stat("steals")+stat("blocks"),minutes,36),
                  threeRate=ratio(stat("threePointFieldGoalsAttempted"),fga,100), ftRate=ratio(fta,fga,100))


def nba(year, inputs):
    data = json.loads(read(NBA.format(year=year), "nba-espn.json", inputs))
    if data["requestedSeason"]["year"] != year or data["requestedSeason"]["type"]["id"] != "2" or data["pagination"]["pages"] != 1:
        raise ValueError("Unexpected NBA season or incomplete pagination")
    categories = {c["name"]:c for c in data["categories"]}
    labels = {key:label for c in categories.values() for key,label in zip(c["names"],c["displayNames"],strict=True)}
    metrics = dict(ts="True shooting %", efg="Effective field goal %", astTo="Assist / turnover ratio",
                   pts36="Points per 36 minutes", reb36="Rebounds per 36 minutes", ast36="Assists per 36 minutes",
                   stocks36="Steals + blocks per 36 minutes", threeRate="3-point attempt rate %", ftRate="Free throw attempt rate %")
    players = []
    for entry in data["athletes"]:
        athlete = entry["athlete"]
        values = {key:number(value) for c in entry["categories"]
                  for key,value in zip(categories[c["name"]]["names"],c["values"],strict=True)}
        nba_efficiency(values)
        players.append(dict(id=athlete["id"], name=athlete["displayName"],
                            team=athlete.get("teamShortName",""),
                            position=athlete.get("position",{}).get("abbreviation",""), stats=values))
    return [board("Box score", "avgPoints", labels, players),
            board("Efficiency & per 36", "ts", {"gamesPlayed":"Games played","minutes":"Minutes","fieldGoalsAttempted":"Field goal attempts", **metrics}, players)]

def mlb(year, inputs, window=None):
    boards = []
    for kind, file, title, default in [("batter","mlb-bat.csv","Hitting","est_woba"),("pitcher","mlb-pitch.csv","Pitching","xera")]:
        source = [] if window else csv.DictReader(io.StringIO(read(MLB.format(kind=kind, year=year), file, inputs)))
        metrics = dict(pa="Plate appearances" if kind=="batter" else "Batters faced", bip="Balls in play",
                       ba="Batting average", est_ba="Expected batting average", slg="Slugging",
                       est_slg="Expected slugging", woba="wOBA", est_woba="Expected wOBA",
                       est_woba_minus_woba_diff="Expected wOBA minus actual")
        if kind == "pitcher":
            metrics.update(era="ERA", xera="Expected ERA")
            for key in ("ba","est_ba","slg","est_slg","woba","est_woba","est_woba_minus_woba_diff"):
                metrics[key] += " allowed"
        group = "hitting" if kind == "batter" else "pitching"
        url = MLB_STATS.format(group=group, year=year)
        if window:
            start, end = window
            url = url.replace("stats=season", "stats=byDateRange") + f"&startDate={start}&endDate={end}&gameType=R"
        payload = json.loads(read(url, f"mlb-{group}{'-' + str((end-start).days + 1) if window else ''}.json", inputs))
        blocks = payload["stats"]
        raw = blocks[0] if blocks else {"totalSplits": 0, "splits": []}
        if raw.get("totalSplits", len(raw["splits"])) != len(raw["splits"]) or len(raw["splits"]) >= 2000:
            raise ValueError(f"Incomplete MLB {group} results")
        expected = {r["player_id"]:r for r in source if r["year"] == str(year)}
        metrics.update(gamesPlayed="Games", homeRuns="HR" if kind=="batter" else "HR allowed",
                       strikeOuts="Strikeouts", baseOnBalls="Walks", kRate="Strikeout %", bbRate="Walk %",
                       kMinusBb="K% minus BB%")
        if kind == "batter":
            metrics.update(runs="Runs",rbi="RBI",stolenBases="Stolen bases",hits="Hits",doubles="Doubles",
                           triples="Triples",obp="OBP",ops="OPS",babip="BABIP",iso="Isolated power")
        else:
            metrics.update(gamesStarted="Starts",wins="Wins",saves="Saves",holds="Holds",whip="WHIP",
                           outs="Outs recorded", strikeoutsPer9Inn="K/9",walksPer9Inn="BB/9",
                           homeRunsPer9="HR/9",strikeoutWalkRatio="K / BB")
        if window:
            for key in ("bip", "woba", "est_ba", "est_slg", "est_woba", "est_woba_minus_woba_diff", "xera"):
                metrics.pop(key, None)
            default = "ops" if kind == "batter" else "era"
        players = []
        for r in raw["splits"]:
            if r.get("season", str(year)) != str(year):
                raise ValueError("Unexpected MLB season")
            pid = str(r["player"]["id"])
            stat = r["stat"]
            savant = expected.get(pid,{})
            stats = {key:number(savant.get(key,stat.get(key))) for key in metrics}
            sample = stat.get("plateAppearances" if kind=="batter" else "battersFaced",0)
            stats["pa"] = sample
            stats["kRate"] = ratio(stat.get("strikeOuts",0),sample,100)
            stats["bbRate"] = ratio(stat.get("baseOnBalls",0),sample,100)
            stats["kMinusBb"] = ratio(stat.get("strikeOuts",0)-stat.get("baseOnBalls",0),sample,100)
            if window and kind == "pitcher":
                stats["ba"] = number(stat.get("avg"))
            if kind == "batter":
                avg, slg = number(stat.get("avg")),number(stat.get("slg"))
                stats["iso"] = round(slg-avg,4) if avg is not None and slg is not None else None
                for key in ("ba","slg"):
                    stats[key] = avg if key=="ba" else slg
            players.append(dict(id=pid,name=r["player"]["fullName"],team=r.get("team",{}).get("name",""),
                                position=r.get("position",{}).get("abbreviation",""),stats=stats))
        boards.append(board(title, default, metrics, players, recent=window is not None))
    return boards

def nfl_recent_rows(weekly, games):
    appearances = defaultdict(dict)
    for row in weekly:
        identity, week = row["player_id"], int(row["week"])
        if week in appearances[identity]:
            raise ValueError("Duplicate NFL player-week")
        appearances[identity][week] = row
    for weeks in appearances.values():
        recent = sorted(weeks.items(), reverse=True)[:games]
        latest = recent[0][1]
        totals = {}
        for key in latest:
            values = [number(row[key]) for _, row in recent]
            totals[key] = sum(value for value in values if value is not None) if any(
                value is not None for value in values) else None
        def total(key):
            return totals.get(key) or 0
        yield {**totals, **{key: latest[key] for key in ("season", "season_type", "player_id",
               "player_display_name", "position")},
               "recent_team": latest.get("recent_team") or latest["team"],
               "games": len(recent), "fg_pct": ratio(total("fg_made"), total("fg_att")),
               "pacr": ratio(total("passing_yards"), total("passing_air_yards")),
               "racr": ratio(total("receiving_yards"), total("receiving_air_yards"))}


NBA_BOX = dict(MIN="minutes", PTS="points", REB="rebounds", AST="assists",
               STL="steals", BLK="blocks", TO="turnovers", PF="fouls",
               OREB="offensiveRebounds", DREB="defensiveRebounds")
NBA_SHOT = dict(FG="fieldGoals", **{"3PT": "threePointFieldGoals"}, FT="freeThrows")


def nba_usage_plays(stats):
    return stats["fieldGoalsAttempted"] + 0.44 * stats["freeThrowsAttempted"] + stats["turnovers"]


def nba_usage(values):
    return ratio(nba_usage_plays(values), values["usageOpportunity"], 100)


def nba_game(event, inputs):
    event_id = event["id"]
    data = json.loads(read(f"{ESPN_NBA}/summary?event={event_id}", f"nba-game-{event_id}.json", inputs))
    teams = data["boxscore"]["players"]
    if len(teams) != 2:
        raise ValueError(f"Incomplete NBA box score: {event_id}")
    players = []
    for team in teams:
        team_players = []
        for group in team["statistics"]:
            for entry in group["athletes"]:
                if entry.get("didNotPlay"):
                    continue
                raw = dict(zip(group["labels"], entry["stats"], strict=True))
                values = {}
                for label, key in NBA_BOX.items():
                    if label in raw:
                        value = raw[label]
                        if label == "MIN" and ":" in value:
                            minutes, seconds = map(int, value.split(":"))
                            value = minutes + seconds / 60
                        values[key] = float(value)
                for label, key in NBA_SHOT.items():
                    values[key + "Made"], values[key + "Attempted"] = map(int, raw[label].split("-"))
                if not all(key in values for key in ("minutes", "points", "rebounds", "assists", "turnovers")):
                    raise ValueError(f"Missing NBA box-score columns: {event_id}")
                values["gamesPlayed"] = 1
                if all(key in values for key in ("points", "rebounds", "assists", "steals", "blocks")):
                    double_digits = sum(values[key] >= 10 for key in ("points", "rebounds", "assists", "steals", "blocks"))
                    values.update(doubleDouble=int(double_digits >= 2), tripleDouble=int(double_digits >= 3))
                athlete = entry["athlete"]
                team_players.append(dict(id=str(athlete["id"]), name=athlete["displayName"],
                                    team=team["team"]["abbreviation"],
                                    position=athlete.get("position", {}).get("abbreviation", ""), stats=values))
        if len(team_players) < 5:
            raise ValueError(f"Incomplete NBA player pool: {event_id}")
        team_minutes = sum(row["stats"]["minutes"] for row in team_players)
        if not team_minutes:
            raise ValueError(f"Missing NBA team minutes: {event_id}")
        plays_per_minute = 5 * sum(nba_usage_plays(row["stats"]) for row in team_players) / team_minutes
        for row in team_players:
            row["stats"]["usageOpportunity"] = row["stats"]["minutes"] * plays_per_minute
        players.extend(team_players)
    if len({row["id"] for row in players}) != len(players):
        raise ValueError(f"Duplicate NBA players: {event_id}")
    return players


def nba_recent(year, inputs, season_boards, end):
    start = dt.date(year - 1, 10, 1)
    def scoreboard(day):
        return json.loads(read(f"{ESPN_NBA}/scoreboard?dates={day:%Y%m%d}", f"nba-scoreboard-{day}.json", inputs))["events"]

    events = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        for daily in executor.map(scoreboard, (start + dt.timedelta(days=offset) for offset in range((end - start).days + 1))):
            for event in daily:
                date = dt.datetime.fromisoformat(event["date"]).astimezone(ZoneInfo("America/New_York")).date()
                if (start <= date <= end and int(event["season"]["year"]) == year and
                        int(event["season"]["type"]) == 2 and event["status"]["type"]["completed"]):
                    events[event["id"]] = (date, event)
        games = sorted(events.values(), key=lambda pair: pair[1]["date"])
        boxes = list(executor.map(lambda pair: nba_game(pair[1], inputs), games))
    periods = {}
    for days in (None, 7, 15):
        cutoff = start if days is None else end - dt.timedelta(days=days-1)
        players = {}
        for (date, _), box in zip(games, boxes, strict=True):
            if date < cutoff:
                continue
            for player in box:
                row = players.setdefault(player["id"], {**player, "stats": defaultdict(float)})
                row.update(team=player["team"], position=player["position"] or row["position"])
                for key, value in player["stats"].items():
                    row["stats"][key] += value
        if days is None:
            for item in season_boards:
                item["metrics"]["usageRate"] = "Usage rate (est.) %"
                for row in item["rows"]:
                    player = players.get(str(row["id"]))
                    row["stats"]["usageRate"] = nba_usage(player["stats"]) if player else None
            continue
        for row in players.values():
            values = row["stats"]
            values["usageRate"] = nba_usage(values)
            del values["usageOpportunity"]
            for key in list(values):
                if key not in ("gamesPlayed", "doubleDouble", "tripleDouble", "usageRate"):
                    values["avg" + key[0].upper() + key[1:]] = ratio(values[key], values["gamesPlayed"])
            for shot, metric in (("fieldGoals", "fieldGoalPct"), ("threePointFieldGoals", "threePointFieldGoalPct"),
                                 ("freeThrows", "freeThrowPct")):
                values[metric] = ratio(values[shot+"Made"], values[shot+"Attempted"], 100)
            nba_efficiency(values)
        available = {key for row in players.values() for key in row["stats"]}
        periods[f"Last {days} days"] = [
            board(item["label"], item["default"],
                  {key: label for key, label in item["metrics"].items() if not players or key in available},
                  players.values(), recent=True) for item in season_boards]
    return periods


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=dt.date.today().year)
    parser.add_argument("--nba-end-year", type=int)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--as-of", type=dt.date.fromisoformat,
                        default=dt.datetime.now(ZoneInfo("America/New_York")).date())
    parser.add_argument("--season-only", action="store_true")
    args = parser.parse_args()
    year = args.year
    nba_year = args.nba_end_year or (year + (args.as_of.month >= 10))
    captured = dt.datetime.now(dt.timezone.utc).isoformat()
    snapshots = {
        "nfl": (str(year), "nflverse · CC BY 4.0", "https://nflreadr.nflverse.com/reference/load_player_stats", nfl(year,args.inputs)),
        "nba": (f"{nba_year-1}-{nba_year%100:02d}", "ESPN box scores · Roster Report calculations", "https://www.espn.com/nba/stats", nba(nba_year,args.inputs)),
        "mlb": (str(year), "MLB official season stats · Baseball Savant Statcast", "https://baseballsavant.mlb.com/expected_statistics", mlb(year,args.inputs)),
    }
    recent = {}
    if not args.season_only:
        weekly_url = NFL.format(year=year).replace("stats_player_reg_", "stats_player_week_")
        weekly = [row for row in csv.DictReader(io.StringIO(read(weekly_url, "nfl-weekly.csv", args.inputs)))
                  if row["season"] == str(year) and row["season_type"] == "REG"]
        if not weekly:
            raise ValueError("Missing NFL regular-season game logs")
        recent["nfl"] = {f"Last {games} games": nfl(year, args.inputs, games, weekly) for games in (2, 5)}
        recent["nba"] = nba_recent(nba_year, args.inputs, snapshots["nba"][3], args.as_of)
        recent["mlb"] = {f"Last {days} days": mlb(year, args.inputs, (args.as_of - dt.timedelta(days=days-1), args.as_of))
                         for days in (7, 15)}
    ROOT.mkdir(parents=True,exist_ok=True)
    for sport,(season,source,url,boards) in snapshots.items():
        path = ROOT / f"{sport}.json.gz"
        temp = path.with_suffix(".tmp")
        temp.write_bytes(gzip.compress(json.dumps(dict(season=season, capturedAt=captured, source=source, url=url, boards=boards, recent=recent.get(sport, {}), recentThrough=args.as_of.isoformat()),ensure_ascii=False,separators=(",",":")).encode(),mtime=0))
        temp.replace(path)
        print(sport, season, [(b["label"],len(b["rows"])) for b in boards])

if __name__ == "__main__":
    main()
