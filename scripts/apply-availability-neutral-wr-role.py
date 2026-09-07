#!/usr/bin/env python3
"""Restore WR opportunity when seasonal totals understate on-field role.

Uses 2025 routes/game and targets per route run (TPRR) to estimate an
availability-neutral 17-game target pace. This is a bounded, team-budget-neutral
opportunity layer: it can restore share lost because of missed games or an overly
harsh season-total prior, but cannot create extra team targets. YPRR supplies
secondary evidence that the route-earned role was productive. Later depth-chart
and competition guardrails still reconcile the final team opportunity.
"""
from pathlib import Path
from html.parser import HTMLParser
from urllib.request import Request, urlopen
import argparse, re, unicodedata
import numpy as np
import pandas as pd

GAMES=17.0
SOURCE='https://sumersports.com/players/wide-receiver/?plays=98'
MIN_MATCHES=60
MIN_GAMES=6
MIN_TARGETS=30
MAX_MULT=1.25


def norm(v):
    t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower()
    t=re.sub(r'\b(jr|sr|ii|iii|iv)\.?\b','',t)
    return re.sub(r'[^a-z0-9]','',t)


def num(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except:return d


def scale(m,i,ratio):
    for c in ['projected_targets','projected_receptions','projected_receiving_yards','projected_receiving_tds']:
        if c in m.columns and np.isfinite(num(m.at[i,c])): m.at[i,c]=num(m.at[i,c],0)*ratio


def points(r,rec):
    x=lambda k:num(r.get(k),0)
    return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')


class TextCollector(HTMLParser):
    def __init__(self):
        super().__init__(); self.tokens=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript'): self.skip+=1
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript') and self.skip:self.skip-=1
    def handle_data(self,data):
        if self.skip:return
        t=' '.join(data.split())
        if t:self.tokens.append(t)


def load_route_metrics(url,known_names):
    rows=[]
    req=Request(url,headers={'User-Agent':'Mozilla/5.0'})
    html=urlopen(req,timeout=30).read().decode('utf-8','ignore')
    p=TextCollector(); p.feed(html); toks=p.tokens
    for i,tok in enumerate(toks):
        candidates=[tok,re.sub(r'^\s*\d+\s*\.\s*','',tok)]
        key=next((norm(v) for v in candidates if norm(v) in known_names),None)
        if not key: continue
        j=None
        for q in range(i+1,min(i+18,len(toks))):
            if toks[q].strip()=='2025': j=q; break
        if j is None: continue
        vals=[]
        for q in range(j+1,min(j+55,len(toks))):
            s=toks[q].replace(',','').replace('%','').strip()
            if re.fullmatch(r'\d+\s*\.',s): continue
            try: vals.append(float(s))
            except: continue
            if len(vals)>=11: break
        if len(vals)>=11:
            routes,tprr,yprr=vals[0],vals[9],vals[10]
            if routes>=1 and 0.01<=tprr<=1.0 and .2<=yprr<=6.0:
                rows.append((key,routes,tprr,yprr))
    x=pd.DataFrame(rows,columns=['name_key','routes_2025','tprr_2025','yprr_role_2025']).drop_duplicates('name_key',keep='last')
    if len(x)<MIN_MATCHES: raise RuntimeError(f'Route metric coverage too small: {len(x)}; need {MIN_MATCHES}')
    print('Availability-neutral WR route matches:',len(x))
    return x


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--stats',type=Path,default=Path('data/projections/stat_projections_2026.csv')); ap.add_argument('--features',type=Path,default=Path('data/projections/player_features_2023_2025.csv')); ap.add_argument('--source',default=SOURCE); ap.add_argument('--out',type=Path,default=Path('data/projections/stat_projections_2026.csv')); a=ap.parse_args()
    s=pd.read_csv(a.stats); f=pd.read_csv(a.features)
    h=f[(f.season.eq(2025)) & f.position.eq('WR')].copy(); h['name_key']=h['player_display_name'].fillna(h.get('player_name','')).map(norm)
    h['games_2025']=pd.to_numeric(h.get('games'),errors='coerce'); h['targets_2025_role']=pd.to_numeric(h.get('targets'),errors='coerce')
    hist=h[['name_key','games_2025','targets_2025_role']].drop_duplicates('name_key')
    route=load_route_metrics(a.source,set(hist.name_key)); hist=hist.merge(route,on='name_key',how='left')
    valid=hist[(hist.games_2025.ge(MIN_GAMES)) & hist.tprr_2025.notna()]
    tprr_med=float(valid.tprr_2025.median()); yprr_med=float(valid.yprr_role_2025.median())

    m=s.copy(); m['name_key_avail']=m.name.map(norm); m=m.merge(hist,left_on='name_key_avail',right_on='name_key',how='left')
    m['availability_neutral_multiplier']=1.0; m['availability_neutral_target_pace']=np.nan; m['availability_neutral_evidence']=np.nan; m['availability_neutral_applied']=False; m['wr_routes_per_game_2025']=np.nan; m['wr_tprr_2025']=m.get('tprr_2025'); m['wr_role_yprr_2025']=m.get('yprr_role_2025')
    eligible=m.position.eq('WR') & m.projection_status.isin(['modeled_veteran','returning_fallback'])
    original_targets=pd.to_numeric(m['projected_targets'],errors='coerce').copy()
    team_wr_budget={team:float(pd.to_numeric(g.projected_targets,errors='coerce').fillna(0).sum()) for team,g in m[eligible].groupby('team')}

    for i in m[eligible].index:
        gp=num(m.at[i,'games_2025']); tg=num(m.at[i,'targets_2025_role']); routes=num(m.at[i,'routes_2025']); tprr=num(m.at[i,'tprr_2025']); yprr=num(m.at[i,'yprr_role_2025']); cur=num(m.at[i,'projected_targets'])
        if gp<MIN_GAMES or tg<MIN_TARGETS or routes<=0 or tprr<=0 or cur<=0: continue
        rpg=routes/gp; pace=rpg*tprr*GAMES
        direct=(tg/gp)*GAMES; pace=.65*pace+.35*direct
        m.at[i,'wr_routes_per_game_2025']=rpg; m.at[i,'availability_neutral_target_pace']=pace
        tscore=float(np.clip((tprr/max(tprr_med,.01)-.85)/.45,0,1))
        yscore=float(np.clip((yprr/max(yprr_med,.01)-.75)/.65,0,1)) if np.isfinite(yprr) else .5
        evidence=.72*tscore+.28*yscore; m.at[i,'availability_neutral_evidence']=evidence
        if pace<=cur*1.03 or evidence<.40: continue
        missed=float(np.clip((17-gp)/10,0,1))
        restore=(.30+.45*missed)*evidence
        desired=cur+restore*(pace-cur)
        desired=min(desired,pace*1.02,cur*MAX_MULT)
        if desired<=cur*1.01: continue
        ratio=desired/cur; scale(m,i,ratio); m.at[i,'availability_neutral_applied']=True

    # Preserve each team's pre-layer WR target budget. This converts restored volume
    # into target-share redistribution rather than adding opportunity to the offense.
    for team,idx in m[eligible].groupby('team').groups.items():
        idx=list(idx); before=team_wr_budget.get(team,0.0); after=float(pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0).sum())
        if before>0 and after>before+1e-9:
            factor=before/after
            for i in idx: scale(m,i,factor)

    # Store the final net multiplier after team-budget reconciliation.
    for i in m[eligible].index:
        old=num(original_targets.loc[i]); new=num(m.at[i,'projected_targets'])
        if old>0 and new>0:
            ratio=new/old; m.at[i,'availability_neutral_multiplier']=ratio
            if ratio<=1.005: m.at[i,'availability_neutral_applied']=False

    for i in m[eligible].index:
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=points(d,1); m.at[i,'half_ppr_points']=points(d,.5); m.at[i,'standard_points']=points(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/GAMES; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/GAMES; m.at[i,'standard_per_game']=m.at[i,'standard_points']/GAMES
    for fmt in ['ppr_points','half_ppr_points','standard_points']:
        m[fmt.replace('_points','_overall_rank')]=m[fmt].rank(method='min',ascending=False); pc=fmt.replace('_points','_pos_rank'); m[pc]=np.nan
        for pos in ['QB','RB','WR','TE']:
            mask=m.position.eq(pos)&m[fmt].notna(); m.loc[mask,pc]=m.loc[mask,fmt].rank(method='min',ascending=False)
    m=m.drop(columns=['name_key_avail','name_key','games_2025','targets_2025_role','routes_2025','tprr_2025','yprr_role_2025'],errors='ignore'); nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(a.out,index=False)
    watch=m[m.name.isin(['Jameson Williams','Christian Watson','Zay Flowers','Jerry Jeudy'])]
    print(watch[['name','projected_targets','wr_routes_per_game_2025','wr_tprr_2025','wr_role_yprr_2025','availability_neutral_target_pace','availability_neutral_evidence','availability_neutral_multiplier','availability_neutral_applied','ppr_points','ppr_pos_rank']].sort_values('ppr_pos_rank').to_dict('records'))
    print('Availability-neutral WR adjustments:',int(m.availability_neutral_applied.sum())); print(f'Wrote availability-neutral projections to {a.out}')

if __name__=='__main__': main()
