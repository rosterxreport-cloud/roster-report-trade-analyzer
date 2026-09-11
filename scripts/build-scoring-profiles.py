#!/usr/bin/env python3
"""Build documented 2026 scoring profiles from nflverse stats and play-by-play."""
from __future__ import annotations
import json, re, unicodedata
from pathlib import Path
import numpy as np
import pandas as pd

PLAYER_URL="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_{season}.csv"
PBP_URL="https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet"
FIELDS={"passing_yards":"passingYards","passing_tds":"passingTds","rushing_tds":"rushingTds","receiving_tds":"receivingTds","rushing_first_downs":"rushingFirstDowns","receiving_first_downs":"receivingFirstDowns","receptions":"receptions"}
REQUIRED={"player_id","player_display_name","position","games","fantasy_points","fantasy_points_ppr",*FIELDS}

def namekey(value):
    value=unicodedata.normalize("NFKD",str(value or "")).encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9]","",re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b","",value))

def load_stats(season):
    d=pd.read_csv(PLAYER_URL.format(season=season),low_memory=False);missing=sorted(REQUIRED-set(d.columns))
    if missing:raise RuntimeError(f"{season} player source missing columns: {missing}")
    return d[d.position.isin(["QB","RB","WR","TE"])].copy()
def long_tds(season):
    cols=["season_type","passer_player_id","rusher_player_id","receiver_player_id","pass_touchdown","rush_touchdown","yards_gained"]
    d=pd.read_parquet(PBP_URL.format(season=season),columns=cols);d=d[d.season_type.eq("REG")];result={}
    for threshold in (40,50):
        plays=d[pd.to_numeric(d.yards_gained,errors="coerce").ge(threshold)]
        for field,flag in (("passer_player_id","pass_touchdown"),("receiver_player_id","pass_touchdown"),("rusher_player_id","rush_touchdown")):
            counts=plays[pd.to_numeric(plays[flag],errors="coerce").eq(1)].groupby(field).size()
            for player_id,count in counts.items():
                if pd.notna(player_id):result.setdefault(str(player_id),{})[threshold]=result.setdefault(str(player_id),{}).get(threshold,0)+int(count)
    return result
def projected(old,current,field):
    games=float(pd.to_numeric(current.get("games"),errors="coerce") or 0) if current is not None else 0
    oldval=pd.to_numeric(old.get(field),errors="coerce") if old is not None else np.nan;curval=pd.to_numeric(current.get(field),errors="coerce") if current is not None else np.nan
    pace=curval/games*17 if games>0 and pd.notna(curval) else np.nan;weight=min(.65,.65*games/8)
    if pd.notna(oldval) and pd.notna(pace):return float((1-weight)*oldval+weight*pace)
    if pd.notna(pace):return float(pace)
    if pd.notna(oldval):return float(oldval)
    return None
def main():
    out=Path("scoring-profiles.json");p25,p26=load_stats(2025),load_stats(2026);long25,long26=long_tds(2025),long_tds(2026);by25={str(r.player_id):r for _,r in p25.iterrows()};by26={str(r.player_id):r for _,r in p26.iterrows()};profiles={}
    for player_id in sorted(set(by25)|set(by26)):
        old,cur=by25.get(player_id),by26.get(player_id);row=cur if cur is not None else old;profile={}
        for source,target in FIELDS.items():profile[target]=projected(old,cur,source)
        std=projected(old,cur,"fantasy_points");ppr=projected(old,cur,"fantasy_points_ppr");profile["baselinePoints"]=ppr if ppr is not None else std
        for threshold in (40,50):
            a=long25.get(player_id,{}).get(threshold);b=long26.get(player_id,{}).get(threshold);games=float(cur.games) if cur is not None and pd.notna(cur.games) else 0;pace=b/games*17 if b is not None and games>0 else None;w=min(.65,.65*games/8)
            profile[f"longTds{threshold}"]=float((1-w)*a+w*pace) if a is not None and pace is not None else float(pace) if pace is not None else float(a) if a is not None else None
        profiles[str(row.player_display_name)]=profile
    database=json.loads(Path("players.json").read_text());wanted={p["name"] for rows in database.values() for p in rows if p["pos"] in {"QB","RB","WR","TE"}};normalized={namekey(name):profile for name,profile in profiles.items()};profiles={name:normalized[namekey(name)] for name in sorted(wanted) if namekey(name) in normalized}
    out.write_text(json.dumps(profiles,indent=2,allow_nan=False)+"\n");print(f"Wrote {len(profiles)} documented scoring profiles for current database players")
if __name__=="__main__":main()
