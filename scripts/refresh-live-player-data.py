#!/usr/bin/env python3
"""Fail-closed 2026 live-data refresh for the trade analyzer."""
from __future__ import annotations
import argparse, copy, json, math, re, unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

FORMATS=("half","ppr","standard"); CORE={"QB","RB","WR","TE"}
TEAMS={
"Arizona Cardinals":"ARI","Atlanta Falcons":"ATL","Baltimore Ravens":"BAL","Buffalo Bills":"BUF","Carolina Panthers":"CAR","Chicago Bears":"CHI","Cincinnati Bengals":"CIN","Cleveland Browns":"CLE","Dallas Cowboys":"DAL","Denver Broncos":"DEN","Detroit Lions":"DET","Green Bay Packers":"GB","Houston Texans":"HOU","Indianapolis Colts":"IND","Jacksonville Jaguars":"JAX","Kansas City Chiefs":"KC","Las Vegas Raiders":"LV","Los Angeles Chargers":"LAC","Los Angeles Rams":"LAR","Miami Dolphins":"MIA","Minnesota Vikings":"MIN","New England Patriots":"NE","New Orleans Saints":"NO","New York Giants":"NYG","New York Jets":"NYJ","Philadelphia Eagles":"PHI","Pittsburgh Steelers":"PIT","San Francisco 49ers":"SF","Seattle Seahawks":"SEA","Tampa Bay Buccaneers":"TB","Tennessee Titans":"TEN","Washington Commanders":"WAS"}
ALIASES={"LA":"LAR","JAC":"JAX","WSH":"WAS","OAK":"LV","SD":"LAC","STL":"LAR"}
DEPTH_URL="https://www.profootballnetwork.com/nfl-hq/depth-charts"
PLAYER_URL="https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_reg_{season}.csv"
TEAM_URL="https://github.com/nflverse/nflverse-data/releases/download/stats_team/stats_team_reg_{season}.csv"
SNAP_URL="https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_{season}.csv"
PBP_URL="https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet"
PFR_RUSH_URL="https://github.com/nflverse/nflverse-data/releases/download/pfr_advstats/advstats_week_rush_{season}.csv"
SCHEDULE_URL="https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
SCHEMA={"rank","name","team","pos","value","awRank","analytics","analyticsScore","posRank","scarcity","market","rookie"}

def team(v):
    v=str(v or "").strip().upper(); return ALIASES.get(v,v)
def namekey(v):
    v=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9]","",re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b","",v))
def fetch(url):
    with urlopen(Request(url,headers={"User-Agent":"RosterReportDataRefresh/1.0"}),timeout=60) as r:
        if r.status!=200: raise RuntimeError(f"HTTP {r.status}: {url}")
        return r.read().decode()
def stats(url,season): return pd.read_csv(url.format(season=season),low_memory=False)
def snap_stats(season):
    try:
        df=pd.read_csv(SNAP_URL.format(season=season),low_memory=False)
    except Exception as e:
        raise RuntimeError(f"2026 snap-count feed unavailable: {e}")
    require(df,{"player","position","offense_snaps","offense_pct"},"2026 snap counts")
    df=df[df.position.isin(CORE)].copy()
    df["name_key"]=df.player.map(namekey)
    df["offense_snaps"]=pd.to_numeric(df.offense_snaps,errors="coerce").fillna(0)
    df["offense_pct"]=pd.to_numeric(df.offense_pct,errors="coerce").fillna(0)
    # PFR game-level snap rows -> season totals plus snap-weighted share.
    agg=df.groupby("name_key",as_index=False).agg(offense_snaps=("offense_snaps","sum"),snap_games=("offense_snaps",lambda s:int((s>0).sum())))
    pct=df.groupby("name_key").apply(lambda g: np.average(g.offense_pct,weights=g.offense_snaps.clip(lower=1)) if len(g) else 0,include_groups=False).reset_index(name="offense_pct")
    return agg.merge(pct,on="name_key",how="left")
def rb_creation_stats(season):
    # Explosive runs are calculated directly from play-by-play (10+ yards).
    pbp=pd.read_parquet(PBP_URL.format(season=season),columns=["rusher_player_name","rush_attempt","yards_gained"])
    rush=pbp[pd.to_numeric(pbp.rush_attempt,errors="coerce").fillna(0).eq(1)].copy()
    rush["name_key"]=rush.rusher_player_name.map(namekey)
    rush["explosive"]=pd.to_numeric(rush.yards_gained,errors="coerce").fillna(0).ge(10).astype(int)
    ex=rush.groupby("name_key",as_index=False).agg(rb_pbp_carries=("explosive","size"),explosive_runs=("explosive","sum"))
    ex["explosive_run_rate"]=ex.explosive_runs/ex.rb_pbp_carries.replace(0,np.nan)

    # PFR advanced rushing supplies broken tackles and yards after contact.
    adv=pd.read_csv(PFR_RUSH_URL.format(season=season),low_memory=False)
    namecol=next((x for x in ("player","player_name","name") if x in adv.columns),None)
    if not namecol: raise RuntimeError("PFR advanced rushing missing player name")
    def col(*names):
        return next((x for x in names if x in adv.columns),None)
    att=col("attempts","att","rushing_attempts")
    brk=col("brk_tkl","broken_tackles","brk_tkl_rush")
    yac=col("yards_after_contact","yac","rush_yac")
    if not att or not brk: raise RuntimeError(f"PFR advanced rushing missing attempts/broken tackles; columns={list(adv.columns)}")
    adv["name_key"]=adv[namecol].map(namekey)
    adv["_att"]=pd.to_numeric(adv[att],errors="coerce").fillna(0)
    adv["_brk"]=pd.to_numeric(adv[brk],errors="coerce").fillna(0)
    adv["_yac"]=pd.to_numeric(adv[yac],errors="coerce").fillna(0) if yac else 0
    ag=adv.groupby("name_key",as_index=False).agg(adv_carries=("_att","sum"),broken_tackles=("_brk","sum"),yards_after_contact=("_yac","sum"))
    ag["broken_tackle_rate"]=ag.broken_tackles/ag.adv_carries.replace(0,np.nan)
    ag["yac_per_attempt"]=ag.yards_after_contact/ag.adv_carries.replace(0,np.nan)
    return ex.merge(ag,on="name_key",how="outer")

def require(df,cols,label):
    missing=sorted(set(cols)-set(df.columns))
    if missing: raise RuntimeError(f"{label} missing required source columns: {missing}")
def pct(s,ascending=True):
    s=pd.to_numeric(s,errors="coerce"); s=s.fillna(s.median() if s.notna().any() else 0)
    return s.rank(method="average",pct=True,ascending=ascending)*100

def primary_kickers(html):
    soup=BeautifulSoup(html,"html.parser"); result={}
    for h in soup.find_all("h2"):
        label=h.get_text(" ",strip=True)
        if label not in TEAMS: continue
        node=h.find_next()
        while node and node.name!="h2":
            if node.get_text(" ",strip=True)=="Kicker":
                link=node.find_next("a"); result[TEAMS[label]]=link.get_text(" ",strip=True) if link else ""; break
            node=node.find_next()
    if set(result)!=set(TEAMS.values()) or len(set(result.values()))!=32 or not all(result.values()):
        raise RuntimeError(f"Depth-chart kicker coverage invalid: resolved {len(result)} unique teams and {len(set(result.values()))} unique kickers")
    return result

def weighted(rows,col,default=0):
    if rows.empty or col not in rows:return default
    values=pd.to_numeric(rows[col],errors="coerce"); ok=values.notna()
    weights=rows.season.map({2025:.65,2026:.35}).fillna(0)*pd.to_numeric(rows.games,errors="coerce").fillna(1).clip(lower=1)
    return float(np.average(values[ok],weights=weights[ok])) if ok.any() else default

def kicker_model(kickers,p25,p26,t25,t26):
    cols={"player_display_name","position","recent_team","games","fg_att","fg_made","fg_pct","fg_made_40_49","fg_made_50_59","fg_made_60_","pat_att","pat_made"}
    require(p25,cols,"2025 player stats");require(p26,cols,"2026 player stats")
    allk=pd.concat([p25.assign(season=2025),p26.assign(season=2026)],ignore_index=True)
    allk=allk[allk.position.eq("K")].copy();allk["team_key"]=allk.recent_team.map(team);allk["name_key"]=allk.player_display_name.map(namekey)
    t=pd.concat([t25.assign(season=2025),t26.assign(season=2026)],ignore_index=True); require(t,{"team","games","passing_tds","rushing_tds","fg_att"},"team stats");t["team_key"]=t.team.map(team)
    rows=[]
    for tm,nm in kickers.items():
        m=allk[(allk.team_key.eq(tm))&allk.name_key.eq(namekey(nm))]
        if m.empty:m=allk[allk.name_key.eq(namekey(nm))]
        games=max(1,weighted(m,"games",1)); made=weighted(m,"fg_made"); long40=weighted(m,"fg_made_40_49")+weighted(m,"fg_made_50_59")+weighted(m,"fg_made_60_"); long50=weighted(m,"fg_made_50_59")+weighted(m,"fg_made_60_")
        tmrows=t[t.team_key.eq(tm)]; env=(weighted(tmrows,"passing_tds")+weighted(tmrows,"rushing_tds")+.35*weighted(tmrows,"fg_att"))/max(1,weighted(tmrows,"games",1))
        rows.append({"team":tm,"name":nm,"fantasy":(3*made+long40+long50+weighted(m,"pat_made"))/games,"attempts":weighted(m,"fg_att")/games,"accuracy":weighted(m,"fg_pct",.8),"long":(long40+long50)/games,"xp":weighted(m,"pat_att")/games,"offense":env})
    f=pd.DataFrame(rows);f["score"]=.35*pct(f.fantasy)+.20*pct(f.attempts)+.15*pct(f.accuracy)+.15*pct(f.long)+.10*pct(f.xp)+.05*pct(f.offense);f["value"]=(6+18*f.score/100).round(2)
    return {r.team:r.to_dict() for _,r in f.iterrows()}

def points_allowed(schedules,season,tm):
    g=schedules[(schedules.season.eq(season))&schedules.game_type.eq("REG")].copy();g=g[(g.home_team.map(team).eq(tm))|g.away_team.map(team).eq(tm)];g=g[g.home_score.notna()&g.away_score.notna()]
    return [float(r.away_score if team(r.home_team)==tm else r.home_score) for _,r in g.iterrows()]

def dst_model(t25,t26,schedules):
    cols={"team","games","attempts","def_sacks","def_qb_hits","def_interceptions","def_fumbles_forced","def_tds","fumble_recovery_tds","def_safeties","def_punt_blocks","def_pat_blocks","def_fg_blocks","passing_tds","rushing_tds"}
    require(t25,cols,"2025 team stats");require(t26,cols,"2026 team stats")
    require(schedules,{"season","game_type","home_team","away_team","home_score","away_score"},"schedule data")
    data=pd.concat([t25.assign(season=2025),t26.assign(season=2026)],ignore_index=True);data["team_key"]=data.team.map(team);rows=[]
    for tm in TEAMS.values():
        g=data[data.team_key.eq(tm)];games=max(1,weighted(g,"games",1));sacks=weighted(g,"def_sacks");take=weighted(g,"def_interceptions")+.55*weighted(g,"def_fumbles_forced");td=weighted(g,"def_tds")+weighted(g,"fumble_recovery_tds");blocks=weighted(g,"def_punt_blocks")+weighted(g,"def_pat_blocks")+weighted(g,"def_fg_blocks");safe=weighted(g,"def_safeties")
        pa25=points_allowed(schedules,2025,tm);pa26=points_allowed(schedules,2026,tm);pa=(.65*np.mean(pa25) if pa25 else 0)+(.35*np.mean(pa26) if pa26 else .35*(np.mean(pa25) if pa25 else 21));pa_points=lambda x:10 if x==0 else 7 if x<=6 else 4 if x<=13 else 1 if x<=20 else 0 if x<=27 else -1 if x<=34 else -4
        fantasy=(sacks+2*take+6*td+2*blocks+2*safe)/games+.65*(np.mean([pa_points(x) for x in pa25]) if pa25 else 0)+.35*(np.mean([pa_points(x) for x in pa26]) if pa26 else (np.mean([pa_points(x) for x in pa25]) if pa25 else 0))
        rows.append({"team":tm,"fantasy":fantasy,"sacks":sacks/games,"takeaways":take/games,"touchdowns":td/games,"points_allowed":pa,"pressure":(weighted(g,"def_qb_hits")+sacks)/max(1,weighted(g,"attempts"))})
    f=pd.DataFrame(rows);f["score"]=.35*pct(f.fantasy)+.15*pct(f.sacks)+.15*pct(f.takeaways)+.10*pct(f.touchdowns)+.10*pct(f.points_allowed,False)+.10*pct(f.pressure)+.05*pct(f.fantasy);f["value"]=(8+20*f.score/100).round(2)
    return {r.team:r.to_dict() for _,r in f.iterrows()}

def live_scores(data,scoring):
    """Position-specific 2026 signal using the established Roster Report formulas.

    Each metric is converted to a within-position percentile before weighting.
    The caller still controls sample-size influence (games / 17), so this
    replaces only the generic 70/30 live signal and does not rewrite the
    preseason/AW/market/scarcity framework.
    """
    common={"player_display_name","position","games","fantasy_points","fantasy_points_ppr"}
    require(data,common,"2026 player stats")
    f=data[data.position.isin(CORE)].copy()
    games=pd.to_numeric(f.games,errors="coerce").replace(0,np.nan)

    def num(col,default=0):
        if col not in f.columns:return pd.Series(default,index=f.index,dtype=float)
        return pd.to_numeric(f[col],errors="coerce").fillna(default)

    # Per-game / rate building blocks. Missing advanced source fields fail
    # gracefully to neutral inputs; source availability is recorded by the
    # formula through only metrics nflverse publishes in the season summary.
    std=num("fantasy_points"); ppr=num("fantasy_points_ppr")
    fp=ppr if scoring=="ppr" else std if scoring=="standard" else (std+ppr)/2
    f["_fp_g"]=fp/games
    for col in ("carries","rushing_yards","rushing_tds","targets","receptions",
                "receiving_yards","receiving_tds","receiving_first_downs",
                "passing_yards","passing_tds","interceptions","rushing_first_downs"):
        f[f"_{col}_g"]=num(col)/games
    f["_ypc"]=num("rushing_yards")/num("carries").replace(0,np.nan)
    f["_rb_td_rate"]=(num("rushing_tds")+num("receiving_tds"))/(num("carries")+num("targets")).replace(0,np.nan)
    f["_rec_td_rate"]=num("receiving_tds")/num("targets").replace(0,np.nan)
    f["_completion_pct"]=num("completions")/num("attempts").replace(0,np.nan)
    f["_int_avoid"]=-(num("interceptions")/num("attempts").replace(0,np.nan))
    f["_epa_g"]=(num("passing_epa")+num("rushing_epa")+num("receiving_epa"))/games
    f["_qb_epa_g"]=(num("passing_epa")+num("rushing_epa"))/games
    f["_rec_epa_g"]=num("receiving_epa")/games
    f["_first_down_g"]=(num("receiving_first_downs")+num("rushing_first_downs"))/games
    f["_explosive_run_rate"]=num("explosive_run_rate",np.nan)
    f["_broken_tackle_rate"]=num("broken_tackle_rate",np.nan)
    f["_yac_per_attempt"]=num("yac_per_attempt",np.nan)

    # nflverse season summaries expose these as rate/share fields when
    # available. A neutral 50th percentile is used if a field is absent.
    share_cols=("target_share","air_yards_share","wopr")
    for col in share_cols:
        f[f"_{col}"]=num(col,np.nan)

    weights={
      "RB":[("_fp_g",.32),("_carries_g",.18),("_rushing_yards_g",.09),("_ypc",.07),
            ("_rb_td_rate",.10),("_targets_g",.07),("_receptions_g",.04),
            ("_receiving_yards_g",.03),("_target_share",.03),("_first_down_g",.03),("_epa_g",.04)],
      "WR":[("_fp_g",.30),("_targets_g",.18),("_receptions_g",.08),("_receiving_yards_g",.15),
            ("_rec_td_rate",.08),("_target_share",.08),("_air_yards_share",.04),("_wopr",.05),
            ("_rec_epa_g",.02),("_receiving_first_downs_g",.02)],
      "TE":[("_fp_g",.32),("_targets_g",.20),("_receptions_g",.09),("_receiving_yards_g",.11),
            ("_receiving_tds_g",.09),("_target_share",.07),("_air_yards_share",.03),("_wopr",.04),
            ("_rec_epa_g",.03),("_receiving_first_downs_g",.02)],
      "QB":[("_fp_g",.36),("_passing_yards_g",.14),("_passing_tds_g",.12),("_int_avoid",.05),
            ("_rushing_yards_g",.10),("_rushing_tds_g",.08),("_completion_pct",.05),("_qb_epa_g",.10)]
    }
    f["score"]=50.0
    for pos,g in f.groupby("position"):
        score=pd.Series(0.0,index=g.index)
        for metric,w in weights[pos]:
            s=pd.to_numeric(g[metric],errors="coerce")
            if s.notna().any():
                ranked=s.rank(method="average",pct=True,ascending=True)*100
                ranked=ranked.fillna(50)
            else:
                ranked=pd.Series(50.0,index=g.index)
            score=score+w*ranked
        f.loc[g.index,"score"]=score
    return dict(zip(f.player_display_name.map(namekey),f.score))

def role_reality_modifier(p, matches):
    """2026 role check using participation when the data supports it.

    Prefer snaps/routes over games-played denominators so an injury-shortened
    appearance is not mistaken for a role collapse. Fall back conservatively
    to per-game opportunity only when participation fields are unavailable.
    """
    if matches.empty or p.get("pos") not in CORE:
        return 1.0
    row=matches.iloc[-1]
    def n(col):
        try: return max(0.0,float(row.get(col,0) or 0))
        except (TypeError,ValueError): return 0.0
    def first(*cols):
        for col in cols:
            v=n(col)
            if v>0:return v
        return 0.0
    pos=p["pos"]
    snaps=first("offense_snaps","offensive_snaps","snap_count","snaps")
    snap_pct=first("offense_pct","offensive_snap_pct","snap_pct","snap_share")
    if snap_pct>1.5:snap_pct/=100.0
    routes=first("routes","routes_run","route_count")
    team_routes=first("team_routes","team_routes_run")
    if pos=="RB":
        opp=n("carries")+n("targets")
        if snaps>0:
            opp_rate=opp/snaps
            participation=max(0.0,min(1.0,snap_pct if snap_pct>0 else snaps/55.0))
            involvement=max(0.0,min(1.0,opp_rate/.38))
            role=.55*participation+.45*involvement
        elif snap_pct>0:
            involvement=max(0.0,min(1.0,(opp/max(1.0,n("games"))-4.0)/14.0))
            role=.60*max(0.0,min(1.0,snap_pct))+.40*involvement
        else:
            g=max(1.0,n("games"));per_game=opp/g
            role=max(0.0,min(1.0,(per_game-5.0)/13.0))
    elif pos in {"WR","TE"}:
        targets=n("targets")
        if routes>0:
            route_part=max(0.0,min(1.0,(routes/team_routes) if team_routes>0 else routes/32.0))
            tprr=max(0.0,min(1.0,(targets/routes)/.25))
            role=.65*route_part+.35*tprr
        elif snaps>0 or snap_pct>0:
            participation=max(0.0,min(1.0,snap_pct if snap_pct>0 else snaps/60.0))
            tgt_rate=max(0.0,min(1.0,(targets/max(1.0,snaps))/.14)) if snaps>0 else .5
            role=.70*participation+.30*tgt_rate
        else:
            g=max(1.0,n("games"));tpg=targets/g;rpg=n("receptions")/g;ypg=n("receiving_yards")/g
            role=.65*max(0.0,min(1.0,(tpg-2.0)/6.0))+.15*max(0.0,min(1.0,rpg/5.0))+.20*max(0.0,min(1.0,ypg/65.0))
    else:
        g=max(1.0,n("games"));attempts=n("attempts")/g;rush=n("carries")/g
        role=max(0.0,min(1.0,.85*(attempts/30.0)+.15*(rush/6.0)))
    penalty=.25*((1.0-role)**2)
    return max(.75,1.0-penalty)

def special(nm,tm,pos,d,rank):
    return {"rank":rank,"name":nm,"team":tm,"pos":pos,"value":round(d["value"],2),"awRank":None,"analytics":round(d["score"],2),"analyticsScore":round(d["score"],2),"posRank":0,"scarcity":round(d["score"],2),"market":round(d["value"],2),"rookie":False}

def update(records,scoring,kickers,kvals,dvals,p26,snaps26,special_only,baseline,injuries):
    old={(p["pos"],team(p["team"])):p for p in records if p["pos"] in {"K","DST"}};scores={} if special_only else live_scores(p26,scoring);out=[]
    for p in records:
        if p["pos"] in {"K","DST"}:continue
        q=copy.deepcopy(p);base=baseline.get(scoring,{}).get(p["name"])
        if base:q.update(value=base["value"],analyticsScore=base["analyticsScore"],rank=base["rank"])
        if not special_only and p["pos"] in CORE and p.get("analyticsScore") is not None:
            matches=p26.loc[p26.player_display_name.map(namekey).eq(namekey(p["name"]))].copy();sk=namekey(p["name"]);sr=snaps26.loc[snaps26.name_key.eq(sk)];
            if not matches.empty and not sr.empty:
                matches.loc[:,"offense_snaps"]=float(sr.iloc[0].offense_snaps);matches.loc[:,"offense_pct"]=float(sr.iloc[0].offense_pct)
            games=float(matches["games"].max() or 0) if not matches.empty else 0.0;prior=float(q["analyticsScore"]);has_live=namekey(p["name"]) in scores;live=scores[namekey(p["name"])] if has_live else prior;scarcity=float(q.get("scarcity") or prior);market=float(q.get("market") or q["value"]);preseason=max(0.0,min(100.0,float(q["value"])));context=max(0.0,min(100.0,.60*market+.40*scarcity));season_w=.45 if games>=2 else .30 if games==1 else 0.0;pre_w=.40 if games>=2 else .50 if games==1 else .65;ctx_w=1-season_w-pre_w;sample_reliability=100.0;ctx_adj=context;new=pre_w*prior+season_w*live+ctx_w*ctx_adj;raw_value=season_w*live+pre_w*preseason+ctx_w*ctx_adj
            # Early-season downside guardrail: through two games, performance alone
            # cannot erase more than 12 value points from the preseason prior.
            # Missing games affect only the amount of live-season evidence; injury/availability is handled once by the explicit injury layer.
            if games>=2: raw_value=max(raw_value,preseason-12.0)
            # Role Reality is applied after the blend/guardrail but before the
            # injury layer. That keeps poor healthy usage distinct from missed
            # time and prevents injury from being counted twice.
            role_mod=role_reality_modifier(p,matches)
            adj=injuries.get(p["name"])
            # Injury-shortened games can masquerade as role loss in season
            # totals. When the injury file shows an active availability/workload
            # concern, soften only the Role Reality downside; the dedicated
            # injury deduction below still prices the injury exactly once.
            if adj and role_mod<1.0:
                a=max(0.0,min(1.0,float(adj.get("availability",1))))
                w=max(0.0,min(1.0,float(adj.get("workload",1))))
                injury_context=max(0.0,min(1.0,1.0-(a*.55+w*.45)))
                role_mod=role_mod+(1.0-role_mod)*min(.80,injury_context*1.6)
            raw_value*=role_mod
            q["analyticsScore"]=round(max(0.0,min(100.0,new)),2);q["value"]=round(max(0.0,min(100.0,raw_value)),2);q["value"]=round(max(0.0,q["value"]-injury_deduction(adj)),2) if adj else q["value"]
        out.append(q)
    next_rank=251
    for pos,source,names in (("K",kvals,kickers),("DST",dvals,{v:k for k,v in TEAMS.items()})):
        for tm,nm in names.items():
            prior=old.get((pos,tm));rank=prior["rank"] if prior else next_rank
            if not prior:next_rank+=1
            out.append(special(nm,tm,pos,source[tm],rank))
        for i,p in enumerate(sorted([x for x in out if x["pos"]==pos],key=lambda x:(-x["value"],x["name"])),1):p["posRank"]=i
    if not special_only:
        # Temporary elite-preseason buffer through Week 3. Protect only the
        # Roster Report preseason Top 15; do not rewrite their values/analytics.
        # Major injury/availability or role-loss profiles can override it.
        candidates=[x for x in out if x["rank"]<=250]
        ordered=sorted(candidates,key=lambda x:(-x["value"],x["rank"]))
        provisional={p["name"]:i for i,p in enumerate(ordered,1)}
        max_drop=15  # Weeks 1-2; loosen to 20-25 for Week 3, remove Week 4+
        protected={}
        for p in ordered:
            b=baseline.get(scoring,{}).get(p["name"],{})
            pre_rank=int(b.get("rank",999))
            if pre_rank>15: continue
            adj=injuries.get(p["name"])
            status=str((adj or {}).get("status","")).lower()
            on_ir=("injured reserve" in status or "reserve/injured" in status or status.startswith("ir ") or status.startswith("ir -") or " pup" in (" "+status))
            severe=bool(adj and (float(adj.get("availability",1))<=.35 or float(adj.get("longTermRisk",1))<=.45))
            matches=p26.loc[p26.player_display_name.map(namekey).eq(namekey(p["name"]))]
            role_mod=role_reality_modifier(p,matches)
            major_role_loss=role_mod<=.82
            # IR/PUP explicitly overrides the early elite buffer. Those players
            # may fall as far as their normal model + injury deduction dictates.
            if not on_ir and not severe and not major_role_loss:
                protected[p["name"]]=min(250,pre_rank+max_drop)
        # Stable insertion enforces only a rank floor; underlying values remain
        # untouched so the 2026 signal is still visible and auditable.
        final=list(ordered)
        for nm,floor_rank in sorted(protected.items(),key=lambda z:z[1]):
            idx=next((i for i,p in enumerate(final) if p["name"]==nm),None)
            if idx is not None and idx+1>floor_rank:
                player=final.pop(idx);final.insert(floor_rank-1,player)
        for i,p in enumerate(final,1):p["rank"]=i
    return sorted(out,key=lambda p:(p["rank"],p["pos"],p["name"]))

def validate(data):
    if set(data)!=set(FORMATS):raise RuntimeError("Expected Half-PPR, Full-PPR and Standard datasets")
    for scoring,rows in data.items():
        if not isinstance(rows,list) or any(set(p)!=SCHEMA for p in rows):raise RuntimeError(f"Unexpected output schema in {scoring}")
        if len({p["name"] for p in rows})!=len(rows):raise RuntimeError(f"Duplicate player records in {scoring}")
        if sum(int(p["rank"])<=250 for p in rows)!=250:raise RuntimeError(f"{scoring} core Top 250 unexpectedly dropped below 250")
        if any(not isinstance(p["value"],(int,float)) or not math.isfinite(p["value"]) for p in rows):raise RuntimeError(f"NaN/invalid trade value in {scoring}")
        for pos,ceiling in (("K",24),("DST",28)):
            group=[p for p in rows if p["pos"]==pos]
            if len(group)!=32 or len({p["team"] for p in group})!=32:raise RuntimeError(f"Incomplete {pos} coverage in {scoring}")
            if max(p["value"] for p in group)>ceiling:raise RuntimeError(f"{pos} compression ceiling failed")

def make_summary(before,after,oldk,newk,changed):
    old={p["name"]:p["rank"] for p in before["half"]};new={p["name"]:p["rank"] for p in after["half"]};moves=sorted(((old[n]-new[n],n,old[n],new[n]) for n in old.keys()&new if old[n]!=new[n]),reverse=True);changes=[(t,oldk.get(t),newk[t]) for t in sorted(newk) if oldk.get(t)!=newk[t]]
    lines=["# Roster Report refresh summary","",f"Generated: {datetime.now(timezone.utc).isoformat()}",f"Website dataset updated: **{'yes' if changed else 'no'}**","","## Biggest ranking risers"]+[f"- {n}: {a} → {b} ({d:+d})" for d,n,a,b in moves[:10]]+["","## Biggest ranking fallers"]+[f"- {n}: {a} → {b} ({d:+d})" for d,n,a,b in sorted(moves)[:10]]+["","## Kicker changes"]+[f"- {t}: {a or 'not previously present'} → {b}" for t,a,b in changes]+["","## Data-quality warnings","- None. All fail-closed validations passed.",""]
    return "\n".join(lines)

def injury_deduction(adj):
    if not adj:return 0.0
    a=max(0,min(1,float(adj.get("availability",1))))
    w=max(0,min(1,float(adj.get("workload",1))))
    r=max(0,min(1,float(adj.get("longTermRisk",1))))
    severity=1.0-(a*.50+w*.30+r*.20)
    # Soft ROS penalty: ordinary injuries are capped at six value points.
    # Only clearly severe/long-term profiles can extend toward 12.
    cap=12.0 if (a<=.35 or r<=.45) else 6.0
    return min(cap,max(0.0,severity*25.0))

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--players",type=Path,default=Path("players.json"));ap.add_argument("--baseline",type=Path,default=Path("data/live-refresh-baseline.json"));ap.add_argument("--summary",type=Path,default=Path("refresh-summary.md"));ap.add_argument("--special-teams-only",action="store_true");a=ap.parse_args();before=json.loads(a.players.read_text());baseline=json.loads(a.baseline.read_text());injury_path=a.players.parent/"injury-adjustments.json";injuries=(json.loads(injury_path.read_text()).get("players",{}) if injury_path.exists() else {})
    for scoring,rows in before.items():
        if len(rows)<250 or sum(int(p["rank"])<=250 for p in rows)!=250 or any(set(p)!=SCHEMA for p in rows):raise RuntimeError(f"Locked {scoring} Top 250 baseline/schema invalid")
        if set(baseline.get(scoring,{}))!={p["name"] for p in rows if p["pos"] in CORE}:raise RuntimeError(f"Immutable core baseline coverage invalid in {scoring}")
    kickers=primary_kickers(fetch(DEPTH_URL));p25,p26=stats(PLAYER_URL,2025),stats(PLAYER_URL,2026);snaps26=snap_stats(2026);rbx=rb_creation_stats(2026);p26["name_key"]=p26.player_display_name.map(namekey);p26=p26.merge(rbx,on="name_key",how="left");t25,t26=stats(TEAM_URL,2025),stats(TEAM_URL,2026);schedules=pd.read_csv(SCHEDULE_URL,low_memory=False);kvals=kicker_model(kickers,p25,p26,t25,t26);dvals=dst_model(t25,t26,schedules)
    after={s:update(before[s],s,kickers,kvals,dvals,p26,snaps26,a.special_teams_only,baseline,injuries) for s in FORMATS};validate(after);oldk={team(p["team"]):p["name"] for p in before["half"] if p["pos"]=="K"};rendered=json.dumps(after,indent=2,ensure_ascii=False)+"\n";changed=rendered!=a.players.read_text();a.players.write_text(rendered);a.summary.write_text(make_summary(before,after,oldk,kickers,changed));print(f"Validated {len(after['half'])} records per format; verified 32 K and 32 D/ST")
if __name__=="__main__":main()
