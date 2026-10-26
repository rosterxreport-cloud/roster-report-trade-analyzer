#!/usr/bin/env python3
"""Audit saved pregame NFL projections against nflverse weekly player stats.

Fail closed: no partial/empty data presented as final, no guesses for unmatched names.
"""
import argparse
import csv
import io
import json
import math
import re
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATA_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.csv"
POSITIONS = ("QB", "RB", "WR", "TE")

def clean_name(value):
    value = (value or "").lower().replace("’", "'")
    value = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", value)
    return re.sub(r"[^a-z0-9]", "", value)

def num(row, *keys):
    for key in keys:
        if key in row and row[key] not in ("", None, "NA"):
            try:
                v = float(row[key])
                if math.isfinite(v):
                    return v
            except (ValueError, TypeError):
                pass
    return 0.0

def actual_points(row):
    # Four-point passing touchdowns; full PPR; -2 turnovers, +2 two-point conversions.
    # nflverse weekly stats use 'passing_interceptions' rather than legacy 'interceptions'.
    return round(
        .04*num(row,"passing_yards")
        + 4*num(row,"passing_tds")
        - 2*num(row,"passing_interceptions","interceptions")
        + .1*num(row,"rushing_yards")
        + 6*num(row,"rushing_tds")
        + num(row,"receptions")
        + .1*num(row,"receiving_yards")
        + 6*num(row,"receiving_tds")
        - 2*num(row,"sack_fumbles_lost") # see below: deduplicated against total fumbles_lost
        - 2*max(0,num(row,"rushing_fumbles_lost")+num(row,"receiving_fumbles_lost")
                 +num(row,"passing_fumbles_lost")-num(row,"sack_fumbles_lost"))
        + 2*num(row,"passing_2pt_conversions")
        + 2*num(row,"rushing_2pt_conversions")
        + 2*num(row,"receiving_2pt_conversions"), 2
    )

def calc(projections, actual_rows, completed_teams=None):
    # A source row must have a nonempty player name and a specific week.
    actual_index = defaultdict(list)
    for r in actual_rows:
        name = r.get("player_display_name") or r.get("player_name") or r.get("display_name")
        team = r.get("team") or r.get("recent_team")
        if name and team:
            actual_index[(clean_name(name), team.upper())].append(r)
    details, missing, ambiguous = [], [], []
    for p in projections:
        pos=p.get("Position")
        if pos not in POSITIONS:
            continue
        team=str(p.get("Team") or "").upper()
        name=p.get("Player")
        if completed_teams is not None and team not in completed_teams:
            continue
        matches=actual_index.get((clean_name(name),team),[])
        if len(matches)!=1:
            (ambiguous if matches else missing).append({"player":name,"team":team,"position":pos})
            continue
        a=matches[0]
        if "PPR" not in p:
            raise ValueError("Missing PPR projection for "+str(name))
        expected=float(p["PPR"])
        if not math.isfinite(expected):
            raise ValueError("Invalid projection for "+str(name))
        scored=actual_points(a)
        details.append({"player":name,"team":team,"position":pos,
                        "projected":expected,"actual":scored,
                        "absolute_error":round(abs(expected-scored),2),
                        "signed_error":round(expected-scored,2)})
    def metrics(items):
        if not items:
            return {"players":0,"mae":None,"bias":None,"within_1":None,"within_3":None,"within_5":None}
        n=len(items)
        return {"players":n,"mae":round(sum(x["absolute_error"] for x in items)/n,4),
                "bias":round(sum(x["signed_error"] for x in items)/n,4),
                **{"within_"+str(k):round(100*sum(x["absolute_error"]<=k for x in items)/n,2)
                   for k in (1,3,5)}}
    return {"overall":metrics(details),
            "by_position":{pos:metrics([r for r in details if r["position"]==pos]) for pos in POSITIONS},
            "matched":sorted(details,key=lambda r:-r["absolute_error"]),
            "unmatched":missing,"ambiguous":ambiguous}

def load_stats(url,season,week):
    with urllib.request.urlopen(url.format(season=season),timeout=70) as response:
        rows=list(csv.DictReader(io.TextIOWrapper(response,encoding="utf-8-sig")))
    if not rows: raise ValueError("Stats source returned no rows")
    needed={"season","week"}
    if not needed.issubset(rows[0]): raise ValueError("Stats source missing season/week")
    matches=[r for r in rows if str(r.get("season"))==str(season) and
             str(r.get("week"))==str(week) and
             str(r.get("season_type","REG")) in ("REG","")]
    if not matches: raise ValueError("No completed-game stats found for requested season/week")
    return matches

def run(args):
    if args.self_test:
        p=[{"Player":"Test Player","Team":"NE","Position":"RB","PPR":12.0}]
        a=[{"player_display_name":"Test Player","team":"NE","rushing_yards":"50",
            "rushing_tds":"1","receptions":"2","receiving_yards":"20"}]
        result=calc(p,a)
        assert result["overall"]["mae"]==3.0, result
        assert result["by_position"]["RB"]["within_3"]==100.0
        print("Self-test passed")
        return
    source=Path(args.snapshot)
    snap=json.loads(source.read_text())
    season,week=int(snap["season"]),int(snap["week"])
    if season < 2020 or not 1<=week<=22: raise ValueError("Invalid snapshot season/week")
    players=snap["players"]
    if not players: raise ValueError("Empty projections")
    rows=load_stats(args.stats_url,season,week)
    # Only teams represented by real weekly stats are eligible: future games are omitted.
    teams={str(r.get("team") or r.get("recent_team") or "").upper() for r in rows}
    result=calc(players,rows,completed_teams=teams)
    coverage_den=result["overall"]["players"]+len(result["unmatched"])+len(result["ambiguous"])
    coverage=result["overall"]["players"]/coverage_den if coverage_den else 0
    if result["overall"]["players"]<args.min_matched or coverage<args.min_coverage:
        raise ValueError(f"Insufficient matching: {result['overall']['players']} matched, {coverage:.1%} coverage")
    projected_teams={str(p.get("Team") or "").upper() for p in players if p.get("Position") in POSITIONS}
    incomplete_teams=sorted(projected_teams-teams)
    result.update({"season":season,"week":week,"projection_source":str(source),
                   "actuals_source":args.stats_url.format(season=season),
                   "source_rows":len(rows),"eligible_projections":coverage_den,
                   "coverage_pct":round(coverage*100,2),
                   "generated_at":datetime.now(timezone.utc).isoformat(),
                   "missing_team_results":incomplete_teams,
                   "status":"partial" if incomplete_teams else "all projected teams have game stats"})
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2)+"\n")
    markdown=[f"# Week {week}, {season} projection accuracy ({result['status']})",
              "",f"**MAE: {result['overall']['mae']}** | matched: {result['overall']['players']} | coverage: {result['coverage_pct']}%",
              "","| Position | Players | MAE | Bias | ±1 | ±3 | ±5 |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for pos, m in [("ALL",result["overall"]),*result["by_position"].items()]:
        markdown.append(f"| {pos} | {m['players']} | {m['mae']} | {m['bias']} | {m['within_1']}% | {m['within_3']}% | {m['within_5']}% |")
    markdown+=["","## Largest misses","",
               "| Player | Position | Projected | Actual | Error |",
               "|---|---|---:|---:|---:|"]
    for r in result["matched"][:20]:
        markdown.append(f"| {r['player']} | {r['position']} | {r['projected']} | {r['actual']} | {r['absolute_error']} |")
    markdown+=["",f"Unmatched: {len(result['unmatched'])}; ambiguous: {len(result['ambiguous'])}.",
               "This report never assumes unavailable games or missing player rows scored zero.",
               "Missing team results: "+(", ".join(incomplete_teams) if incomplete_teams else "none")+".",
               "A final label still requires all expected team games and player matches to be reconciled.",""]
    out.with_suffix(".md").write_text("\n".join(markdown))
    print(f"Audit saved: {out} ({result['overall']['players']} players, MAE {result['overall']['mae']})")

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--snapshot",default="data/weekly-projections.json")
    ap.add_argument("--output",default="data/audits/latest.json")
    ap.add_argument("--stats-url",default=DATA_URL)
    ap.add_argument("--min-matched",type=int,default=1)
    ap.add_argument("--min-coverage",type=float,default=.65)
    ap.add_argument("--self-test",action="store_true")
    try: run(ap.parse_args())
    except (ValueError,KeyError,OSError) as e:
        print(f"AUDIT FAILED: {e}",file=sys.stderr);sys.exit(1)
