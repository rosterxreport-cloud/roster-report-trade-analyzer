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
    cols={"player_display_name","position","games","fantasy_points","fantasy_points_ppr","attempts","carries","targets"};require(data,cols,"2026 player stats")
    f=data[data.position.isin(CORE)].copy();games=pd.to_numeric(f.games,errors="coerce").replace(0,np.nan);std=pd.to_numeric(f.fantasy_points,errors="coerce");ppr=pd.to_numeric(f.fantasy_points_ppr,errors="coerce");points=ppr if scoring=="ppr" else std if scoring=="standard" else (std+ppr)/2
    f["production"]=points/games;f["volume"]=(pd.to_numeric(f.attempts,errors="coerce").fillna(0)+pd.to_numeric(f.carries,errors="coerce").fillna(0)+pd.to_numeric(f.targets,errors="coerce").fillna(0))/games
    f["score"]=0.0
    for pos,g in f.groupby("position"):f.loc[g.index,"score"]=(.7*pct(g.production)+.3*pct(g.volume)).values
    return dict(zip(f.player_display_name.map(namekey),f.score))

def special(nm,tm,pos,d,rank):
    return {"rank":rank,"name":nm,"team":tm,"pos":pos,"value":round(d["value"],2),"awRank":None,"analytics":round(d["score"],2),"analyticsScore":round(d["score"],2),"posRank":0,"scarcity":round(d["score"],2),"market":round(d["value"],2),"rookie":False}

def update(records,scoring,kickers,kvals,dvals,p26,special_only,baseline):
    old={(p["pos"],team(p["team"])):p for p in records if p["pos"] in {"K","DST"}};scores={} if special_only else live_scores(p26,scoring);out=[]
    for p in records:
        if p["pos"] in {"K","DST"}:continue
        q=copy.deepcopy(p);base=baseline.get(scoring,{}).get(p["name"])
        if base:q.update(value=base["value"],analyticsScore=base["analyticsScore"],rank=base["rank"])
        if not special_only and p["pos"] in CORE and p.get("analyticsScore") is not None and namekey(p["name"]) in scores:
            games=float(p26.loc[p26.player_display_name.map(namekey).eq(namekey(p["name"])),"games"].max() or 0);w=min(.5,.5*games/17);prior=float(q["analyticsScore"]);new=(1-w)*prior+w*scores[namekey(p["name"])];q["analyticsScore"]=round(new,2);q["value"]=round(float(q["value"])+.35*(new-prior),2)
        out.append(q)
    next_rank=251
    for pos,source,names in (("K",kvals,kickers),("DST",dvals,{v:k for k,v in TEAMS.items()})):
        for tm,nm in names.items():
            prior=old.get((pos,tm));rank=prior["rank"] if prior else next_rank
            if not prior:next_rank+=1
            out.append(special(nm,tm,pos,source[tm],rank))
        for i,p in enumerate(sorted([x for x in out if x["pos"]==pos],key=lambda x:(-x["value"],x["name"])),1):p["posRank"]=i
    if not special_only:
        for i,p in enumerate(sorted([x for x in out if x["rank"]<=250],key=lambda x:(-x["value"],x["rank"])),1):p["rank"]=i
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

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--players",type=Path,default=Path("players.json"));ap.add_argument("--baseline",type=Path,default=Path("data/live-refresh-baseline.json"));ap.add_argument("--summary",type=Path,default=Path("refresh-summary.md"));ap.add_argument("--special-teams-only",action="store_true");a=ap.parse_args();before=json.loads(a.players.read_text());baseline=json.loads(a.baseline.read_text())
    for scoring,rows in before.items():
        if len(rows)<250 or sum(int(p["rank"])<=250 for p in rows)!=250 or any(set(p)!=SCHEMA for p in rows):raise RuntimeError(f"Locked {scoring} Top 250 baseline/schema invalid")
        if set(baseline.get(scoring,{}))!={p["name"] for p in rows if p["pos"] in CORE}:raise RuntimeError(f"Immutable core baseline coverage invalid in {scoring}")
    kickers=primary_kickers(fetch(DEPTH_URL));p25,p26=stats(PLAYER_URL,2025),stats(PLAYER_URL,2026);t25,t26=stats(TEAM_URL,2025),stats(TEAM_URL,2026);schedules=pd.read_csv(SCHEDULE_URL,low_memory=False);kvals=kicker_model(kickers,p25,p26,t25,t26);dvals=dst_model(t25,t26,schedules)
    after={s:update(before[s],s,kickers,kvals,dvals,p26,a.special_teams_only,baseline) for s in FORMATS};validate(after);oldk={team(p["team"]):p["name"] for p in before["half"] if p["pos"]=="K"};rendered=json.dumps(after,indent=2,ensure_ascii=False)+"\n";changed=rendered!=a.players.read_text();a.players.write_text(rendered);a.summary.write_text(make_summary(before,after,oldk,kickers,changed));print(f"Validated {len(after['half'])} records per format; verified 32 K and 32 D/ST")
if __name__=="__main__":main()
