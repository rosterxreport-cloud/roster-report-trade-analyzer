#!/usr/bin/env python3
"""Apply a bounded WR receiving-efficiency adjustment using 2025 YPC and YPRR.

This is a projection-only efficiency layer. Opportunity (targets/receptions) is left
unchanged. Projected receiving yards are adjusted from a blended standardized signal
of yards per route run and yards per catch, with YPRR receiving slightly more weight.
Small samples are shrunk toward neutral and the adjustment is deliberately bounded.
"""
from pathlib import Path
import argparse, re, unicodedata
import numpy as np
import pandas as pd

GAMES=17.0
YPRR_URL='https://statrankings.com/nfl/advanced/players/receiving/yards-per-route-run'
YPRR_WEIGHT=.60
YPC_WEIGHT=.40
MAX_ADJ=.12
MIN_TARGETS=20.0
FULL_SAMPLE_TARGETS=70.0


def norm(v):
    t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower()
    t=re.sub(r'\b(jr|sr|ii|iii|iv)\.?\b','',t)
    return re.sub(r'[^a-z0-9]','',t)


def num(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except:return d


def points(r,rec):
    x=lambda k:num(r.get(k),0)
    return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')


def zscore(s):
    s=pd.to_numeric(s,errors='coerce')
    mu=s.mean(); sd=s.std(ddof=0)
    if not np.isfinite(sd) or sd<=0:return pd.Series(0.0,index=s.index)
    return ((s-mu)/sd).clip(-2.25,2.25)


def load_yprr(url):
    tables=pd.read_html(url)
    candidates=[]
    for t in tables:
        cols=[str(c).strip() for c in t.columns]
        if 'Player' in cols and 'Position' in cols and '2025' in cols:
            x=t.copy(); x.columns=cols; candidates.append(x)
    if not candidates:
        raise RuntimeError('Could not locate StatRankings YPRR table')
    y=pd.concat(candidates,ignore_index=True).drop_duplicates()
    y=y[y['Position'].astype(str).eq('WR')].copy()
    y['name_key']=y['Player'].astype(str).str.replace(r'([a-z])([A-Z])',r'\1|\2',regex=True).str.split('|').str[0].map(norm)
    y['yprr_2025']=pd.to_numeric(y['2025'],errors='coerce')
    y=y[y.yprr_2025.notna()][['name_key','yprr_2025']].drop_duplicates('name_key')
    if len(y)<40:
        raise RuntimeError(f'YPRR source unexpectedly small: {len(y)} WR rows')
    return y


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--stats',type=Path,default=Path('data/projections/stat_projections_2026.csv'))
    ap.add_argument('--features',type=Path,default=Path('data/projections/player_features_2023_2025.csv'))
    ap.add_argument('--out',type=Path,default=Path('data/projections/stat_projections_2026.csv'))
    ap.add_argument('--yprr-url',default=YPRR_URL)
    a=ap.parse_args()

    s=pd.read_csv(a.stats); f=pd.read_csv(a.features)
    h=f[(f.season.eq(2025)) & f.position.eq('WR')].copy()
    h['name_key']=h['player_display_name'].fillna(h.get('player_name','')).map(norm)
    rec=pd.to_numeric(h.get('receptions'),errors='coerce')
    yds=pd.to_numeric(h.get('receiving_yards'),errors='coerce')
    h['ypc_2025']=yds/rec.where(rec>0)
    h['targets_2025']=pd.to_numeric(h.get('targets'),errors='coerce')
    hist=h[['name_key','ypc_2025','targets_2025']].drop_duplicates('name_key')
    yprr=load_yprr(a.yprr_url)
    hist=hist.merge(yprr,on='name_key',how='left')

    wr_hist=hist[hist.targets_2025.ge(MIN_TARGETS)].copy()
    ypc_mu=wr_hist.ypc_2025.mean(); ypc_sd=wr_hist.ypc_2025.std(ddof=0)
    yprr_mu=wr_hist.yprr_2025.mean(); yprr_sd=wr_hist.yprr_2025.std(ddof=0)

    m=s.copy(); m['name_key_eff']=m.name.map(norm)
    m=m.merge(hist,on='name_key_eff',how='left')
    m['wr_efficiency_multiplier']=1.0
    m['wr_efficiency_score']=np.nan
    m['wr_yprr_2025']=m['yprr_2025']
    m['wr_ypc_2025']=m['ypc_2025']

    eligible=m.position.eq('WR') & m.projection_status.isin(['modeled_veteran','returning_fallback'])
    for i in m[eligible].index:
        ypc=num(m.at[i,'ypc_2025']); yprr=num(m.at[i,'yprr_2025']); tg=num(m.at[i,'targets_2025'],0)
        if tg<MIN_TARGETS or (not np.isfinite(ypc) and not np.isfinite(yprr)):continue
        zy=0.0 if not np.isfinite(ypc) or not np.isfinite(ypc_sd) or ypc_sd<=0 else float(np.clip((ypc-ypc_mu)/ypc_sd,-2.25,2.25))
        zr=0.0 if not np.isfinite(yprr) or not np.isfinite(yprr_sd) or yprr_sd<=0 else float(np.clip((yprr-yprr_mu)/yprr_sd,-2.25,2.25))
        # Missing one input reduces signal strength rather than treating missing as elite/poor.
        observed=(1 if np.isfinite(yprr) else 0)+(1 if np.isfinite(ypc) else 0)
        score=YPRR_WEIGHT*zr+YPC_WEIGHT*zy
        if observed==1:score*=.65
        sample=float(np.clip((tg-MIN_TARGETS)/(FULL_SAMPLE_TARGETS-MIN_TARGETS),0,1))
        shrink=.45+.55*sample
        adj=float(np.clip(score*.055*shrink,-MAX_ADJ,MAX_ADJ))
        mult=1.0+adj
        old=num(m.at[i,'projected_receiving_yards'])
        if np.isfinite(old):m.at[i,'projected_receiving_yards']=old*mult
        m.at[i,'wr_efficiency_multiplier']=mult;m.at[i,'wr_efficiency_score']=score

    for i in m[eligible].index:
        d=m.loc[i].to_dict();m.at[i,'ppr_points']=points(d,1);m.at[i,'half_ppr_points']=points(d,.5);m.at[i,'standard_points']=points(d,0);m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/GAMES;m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/GAMES;m.at[i,'standard_per_game']=m.at[i,'standard_points']/GAMES
    for fmt in ['ppr_points','half_ppr_points','standard_points']:
        m[fmt.replace('_points','_overall_rank')]=m[fmt].rank(method='min',ascending=False);pc=fmt.replace('_points','_pos_rank');m[pc]=np.nan
        for pos in ['QB','RB','WR','TE']:
            mask=m.position.eq(pos)&m[fmt].notna();m.loc[mask,pc]=m.loc[mask,fmt].rank(method='min',ascending=False)

    m=m.drop(columns=['name_key_eff','name_key','ypc_2025','targets_2025','yprr_2025'],errors='ignore')
    nums=m.select_dtypes(include=[np.number]).columns;m[nums]=m[nums].round(3);m.to_csv(a.out,index=False)
    watch=m[m.name.isin(['Puka Nacua','Jaxon Smith-Njigba','Zay Flowers','Jameson Williams','Jaylen Waddle','Jerry Jeudy'])]
    print(watch[['name','wr_yprr_2025','wr_ypc_2025','wr_efficiency_multiplier','projected_receiving_yards','ppr_points','ppr_pos_rank']].sort_values('ppr_pos_rank').to_dict('records'))
    print('WR efficiency adjusted:',int((m.wr_efficiency_multiplier.ne(1.0)).sum()))
    print(f'Wrote YPC/YPRR-weighted projections to {a.out}')

if __name__=='__main__':main()
