#!/usr/bin/env python3
"""Build auditable 2026 team-environment and player-role context.

Current fantasy assignments and trade-analyzer components come from players.json.
Historical football inputs come from nflverse 2023-2025 feature tables.
Veterans without a 2025 row fall back to available 2023-2024 history; true rookies
remain on the dedicated rookie pathway.
"""

from __future__ import annotations
import argparse, json, re, unicodedata
from pathlib import Path
import numpy as np
import pandas as pd

SEASON_WEIGHTS={2023:.20,2024:.30,2025:.50}
TEAM_REGRESSION=.30
TEAM_GAMES=17.0
POSITIONS={"QB","RB","WR","TE"}
TEAM_ALIASES={"LAR":"LA","STL":"LA","JAC":"JAX","WSH":"WAS","OAK":"LV","SD":"LAC"}
PLAYER_HISTORY_FIELDS=[
    "ppr_per_game","targets_per_game","carries_per_game","attempts_per_game",
    "target_share","air_yards_share","wopr","catch_rate","yards_per_target",
    "rec_td_per_target","yards_per_carry","pass_yards_per_attempt","pass_td_rate",
    "interception_rate","rush_td_per_attempt","passing_epa_per_attempt",
    "rushing_epa_per_attempt","receiving_epa_per_target"
]

def norm_name(value):
    text=unicodedata.normalize("NFKD",str(value or "")).encode("ascii","ignore").decode().lower()
    text=re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b","",text)
    return re.sub(r"[^a-z0-9]","",text)

def norm_team(value):
    if pd.isna(value) or value is None:return None
    team=str(value).strip().upper()
    return TEAM_ALIASES.get(team,team)

def weighted(values):
    pairs=[]
    for season,value,games in values:
        if season not in SEASON_WEIGHTS or pd.isna(value):continue
        availability=min(max(float(games) if pd.notna(games) else 12.0,0)/12,1)
        pairs.append((float(value),SEASON_WEIGHTS[season]*availability))
    if not pairs:return np.nan
    den=sum(w for _,w in pairs)
    return sum(v*w for v,w in pairs)/den if den else np.nan

def league_regress(value,mean,amount=TEAM_REGRESSION):
    if value is None or not np.isfinite(value):return float(mean)
    return float((1-amount)*value+amount*mean)

def load_current_players(path):
    raw=json.loads(path.read_text()); rows=[]
    for p in raw.get("half",[]):
        if p.get("pos") not in POSITIONS:continue
        rows.append({"name":p.get("name"),"team_2026":p.get("team"),"position":p.get("pos"),"rookie":bool(p.get("rookie",False)),"trade_value":p.get("value"),"aw_rank":p.get("awRank"),"analytics":p.get("analytics"),"analytics_score":p.get("analyticsScore"),"scarcity_score":p.get("scarcity"),"market_score":p.get("market")})
    df=pd.DataFrame(rows); df["name_key"]=df["name"].map(norm_name); df["team_key_2026"]=df["team_2026"].map(norm_team)
    return df.drop_duplicates(["name_key","position"],keep="first")

def build_team_context(team_hist):
    hist=team_hist.copy(); hist["team_key"]=hist["team"].map(norm_team)
    for c in ["attempts","carries","passing_yards","passing_tds","interceptions","rushing_yards","rushing_tds"]:
        if c in hist.columns:hist[f"{c}_per_game"]=pd.to_numeric(hist[c],errors="coerce")/TEAM_GAMES
    metrics=[c for c in ["attempts_per_game","carries_per_game","pass_yards_per_attempt","pass_td_rate","interception_rate","rush_yards_per_carry","rush_td_rate","pass_rate_proxy","offensive_opportunities"] if c in hist.columns]
    latest=hist[hist["season"].eq(2025)]; league={m:float(pd.to_numeric(latest[m],errors="coerce").mean()) for m in metrics}; rows=[]
    for team_key,g in hist.groupby("team_key"):
        row={"team":team_key,"team_key":team_key,"projection_season":2026}
        for metric in metrics:
            vals=[(int(r.season),getattr(r,metric),12) for r in g[["season",metric]].itertuples(index=False)]; raw=weighted(vals)
            row[f"history_{metric}"]=raw; row[f"projected_{metric}"]=league_regress(raw,league[metric])
        rows.append(row)
    out=pd.DataFrame(rows)
    if "projected_attempts_per_game" in out:out["projected_pass_attempts"]=out["projected_attempts_per_game"]*TEAM_GAMES
    if "projected_carries_per_game" in out:out["projected_rush_attempts"]=out["projected_carries_per_game"]*TEAM_GAMES
    return out.sort_values("team")

def build_history_aggregate(player_hist):
    hist=player_hist.copy(); hist["name_key"]=hist["player_display_name"].fillna(hist.get("player_name","")).map(norm_name); hist["team_key_hist"]=hist["team"].map(norm_team)
    totals=hist.groupby(["season","team_key_hist"],dropna=False).agg(team_targets=("targets","sum"),team_carries=("carries","sum"),team_attempts=("attempts","sum")).reset_index(); hist=hist.merge(totals,on=["season","team_key_hist"],how="left")
    for num,den,out in [("targets","team_targets","hist_target_share_team"),("carries","team_carries","hist_carry_share_team"),("attempts","team_attempts","hist_qb_attempt_share_team")]: hist[out]=pd.to_numeric(hist[num],errors="coerce")/pd.to_numeric(hist[den],errors="coerce").replace(0,np.nan)
    rows=[]
    for (name_key,pos),g in hist.groupby(["name_key","position"],dropna=False):
        g=g.sort_values("season"); last=g.iloc[-1]
        player_ids=g.get("player_id",pd.Series(dtype=object)).dropna().astype(str)
        canonical_id=player_ids.iloc[-1] if len(player_ids) else np.nan
        row={"name_key":name_key,"position":pos,"player_id":canonical_id,"history_last_season":int(last["season"]),"team_2025":last.get("team"),"team_key_2025":last.get("team_key_hist"),"games":last.get("games"),"has_2025_history":bool((g["season"]==2025).any()),"history_season_count":int(g["season"].nunique()),"historical_target_share_team":last.get("hist_target_share_team"),"historical_carry_share_team":last.get("hist_carry_share_team"),"historical_qb_attempt_share_team":last.get("hist_qb_attempt_share_team")}
        for field in PLAYER_HISTORY_FIELDS:
            if field in g.columns:
                vals=[(int(r.season),getattr(r,field),getattr(r,"games",12)) for r in g[["season","games",field]].itertuples(index=False)]; row[field]=weighted(vals)
        latest_games=float(last.get("games")) if pd.notna(last.get("games")) else 0; recency={2025:1.0,2024:.80,2023:.60}.get(int(last["season"]),.5); row["history_confidence"]=min(max(latest_games/12,0),1)*recency; rows.append(row)
    return pd.DataFrame(rows)

def build_player_context(current,player_hist,teams):
    history=build_history_aggregate(player_hist)
    team_cols=["team_key","projected_pass_attempts","projected_rush_attempts","projected_pass_yards_per_attempt","projected_pass_td_rate","projected_rush_yards_per_carry","projected_rush_td_rate"]
    team_lookup=teams[[c for c in team_cols if c in teams.columns]].rename(columns={"team_key":"team_key_2026"})
    merged=current.merge(history,on=["name_key","position"],how="left").merge(team_lookup,on="team_key_2026",how="left")
    merged["has_history"]=merged["history_last_season"].notna(); merged["changed_team"]=merged["team_key_2025"].notna()&merged["team_key_2026"].notna()&merged["team_key_2025"].ne(merged["team_key_2026"]); merged["has_team_context"]=merged["projected_pass_attempts"].notna()|merged["projected_rush_attempts"].notna(); merged["needs_rookie_or_manual_role"]=merged["rookie"]|~merged["has_history"]|~merged["has_team_context"]
    haircut=np.where(merged["changed_team"],.92,1.0)
    for src,dst in [("historical_target_share_team","role_target_share_2026"),("historical_carry_share_team","role_carry_share_2026"),("historical_qb_attempt_share_team","role_qb_attempt_share_2026")]: merged[dst]=pd.to_numeric(merged[src],errors="coerce")*haircut
    merged["role_confidence"]=pd.to_numeric(merged["history_confidence"],errors="coerce").fillna(0); merged.loc[merged["changed_team"],"role_confidence"]*=.80; merged.loc[merged["needs_rookie_or_manual_role"],"role_confidence"]=0.0
    keep=[c for c in ["name","name_key","player_id","position","team_2026","team_key_2026","team_2025","team_key_2025","rookie","changed_team","has_history","has_2025_history","history_last_season","history_season_count","has_team_context","needs_rookie_or_manual_role","games","ppr_per_game","targets_per_game","carries_per_game","attempts_per_game","target_share","air_yards_share","wopr","catch_rate","yards_per_target","rec_td_per_target","yards_per_carry","pass_yards_per_attempt","pass_td_rate","interception_rate","rush_td_per_attempt","passing_epa_per_attempt","rushing_epa_per_attempt","receiving_epa_per_target","historical_target_share_team","historical_carry_share_team","historical_qb_attempt_share_team","role_target_share_2026","role_carry_share_2026","role_qb_attempt_share_2026","projected_pass_attempts","projected_rush_attempts","projected_pass_yards_per_attempt","projected_pass_td_rate","projected_rush_yards_per_carry","projected_rush_td_rate","history_confidence","role_confidence","trade_value","aw_rank","analytics","analytics_score","scarcity_score","market_score"] if c in merged.columns]
    return merged[keep].sort_values(["position","trade_value"],ascending=[True,False])

def main():
    p=argparse.ArgumentParser(); p.add_argument("--player-features",type=Path,default=Path("data/projections/player_features_2023_2025.csv")); p.add_argument("--team-features",type=Path,default=Path("data/projections/team_features_2023_2025.csv")); p.add_argument("--players",type=Path,default=Path("players.json")); p.add_argument("--out-dir",type=Path,default=Path("data/projections")); a=p.parse_args()
    player_hist=pd.read_csv(a.player_features); team_hist=pd.read_csv(a.team_features); current=load_current_players(a.players); teams=build_team_context(team_hist); players=build_player_context(current,player_hist,teams); a.out_dir.mkdir(parents=True,exist_ok=True); teams.to_csv(a.out_dir/"team_context_2026.csv",index=False); players.to_csv(a.out_dir/"player_role_context_2026.csv",index=False)
    print(f"2026 teams: {len(teams)}"); print(f"Current fantasy players: {len(players)}"); print(f"Matched any 2023-2025 history: {int(players['has_history'].sum())}"); print(f"Matched 2025 history: {int(players['has_2025_history'].fillna(False).sum())}"); print(f"Fallback veterans from 2023-2024: {int((players['has_history'] & ~players['has_2025_history'].fillna(False) & ~players['rookie']).sum())}"); print(f"Team changers: {int(players['changed_team'].sum())}"); print(f"Missing team context: {int((~players['has_team_context']).sum())}"); print(f"Rookie/manual-role pathway: {int(players['needs_rookie_or_manual_role'].sum())}"); print(f"Canonical player IDs preserved: {int(players['player_id'].notna().sum()) if 'player_id' in players else 0}")
if __name__=="__main__":main()
