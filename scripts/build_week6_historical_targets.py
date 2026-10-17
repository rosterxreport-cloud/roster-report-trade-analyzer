"""Build a historical target-share input from nflverse weekly player stats.
Fetches 2026 data only, using weeks 1-5. No prior-season target shares.
Does not overwrite projections. Requires pandas and network access.
"""
import io
from pathlib import Path
import pandas as pd
import requests

ROOT="https://github.com/nflverse/nflverse-data/releases/download/stats_player"
OUT=Path("data/projections/2026_week6_historical_target_shares.csv")
frames=[]
for season in (2026,):
    url=f"{ROOT}/stats_player_week_{season}.csv"
    response=requests.get(url,timeout=90)
    response.raise_for_status()
    df=pd.read_csv(io.BytesIO(response.content))
    # nflverse player-stats exports use team in some versions, recent_team in others.
    if "recent_team" not in df.columns and "team" in df.columns:
        df=df.rename(columns={"team":"recent_team"})
    needed={"player_id","player_name","recent_team","week","season_type","targets"}
    missing=needed-set(df.columns)
    if missing: raise ValueError(f"Missing nflverse columns: {missing}")
    df=df[(df.season_type=="REG") & (df.week<= 5)].copy()
    df["season"]=season
    df["position"]=df["position"].fillna("")
    frames.append(df)
all_stats=pd.concat(frames,ignore_index=True)
# Team attempts denominator: sum QB pass attempts by team and week.
# nflverse 'attempts' is the passer's attempts, not player targets.
qbs=all_stats[all_stats["position"]=="QB"].groupby(["season","week","recent_team"])["attempts"].sum().rename("team_pass_attempts")
receivers=all_stats[all_stats["position"].isin(["WR","TE","RB"])].copy()
receivers=receivers.join(qbs,on=["season","week","recent_team"])
receivers=receivers[receivers.team_pass_attempts>0].copy()
receivers["weekly_target_share"]=receivers.targets/receivers.team_pass_attempts
receivers=receivers[receivers["weekly_target_share"].between(0,1)].copy()
receivers["source"]="nflverse_stats_player"
receivers["data_cutoff_week"]=5
# Do not fabricate missing weeks or collapse different team stints.
result=receivers[["season","week","player_id","player_name","recent_team","position","targets","team_pass_attempts","weekly_target_share","receptions","receiving_yards","receiving_tds","source","data_cutoff_week"]]
OUT.parent.mkdir(parents=True,exist_ok=True)
result.to_csv(OUT,index=False)
print(f"Wrote {len(result)} player-week observations to {OUT}")
