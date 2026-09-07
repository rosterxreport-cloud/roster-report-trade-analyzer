#!/usr/bin/env python3
"""Apply regressed veteran RB talent/efficiency adjustments without changing workload.

Uses 2023-2025 NFL production plus optional richer RB metrics when available.
Workload (carries/targets) is preserved; only rushing/receiving efficiency is adjusted.
"""
from pathlib import Path
import numpy as np
import pandas as pd

STATS=Path('data/projections/stat_projections_2026.csv')
FEATS=Path('data/projections/player_features_2023_2025.csv')
GAMES=17.0

def num(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except (TypeError,ValueError): return d

def score(r,rec=1.0):
    x=lambda k:num(r.get(k),0.0)
    return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')

def zclip(x,mean,sd):
    if not np.isfinite(x) or not np.isfinite(mean) or not np.isfinite(sd) or sd<=0: return 0.0
    return float(np.clip((x-mean)/sd,-2.0,2.0))

def main():
    s=pd.read_csv(STATS); f=pd.read_csv(FEATS,low_memory=False)
    f=f[(f.position.eq('RB')) & f.season.isin([2023,2024,2025])].copy()
    if f.empty: raise SystemExit('No RB feature history')
    # Recency-weight player metrics; richer columns are used automatically if added later.
    weights={2023:.20,2024:.30,2025:.50}; f['_w']=f.season.map(weights).fillna(.0)
    candidates=['yards_per_carry','rushing_epa_per_attempt','rushing_first_down_rate','yards_after_contact_per_attempt','missed_tackles_forced_per_attempt','explosive_run_rate','yards_created_per_attempt','success_rate','yards_per_route_run','receiving_epa_per_target','yac_per_reception','yards_per_target','catch_rate']
    avail=[c for c in candidates if c in f.columns]
    rows=[]
    name_col='player_display_name' if 'player_display_name' in f.columns else 'player_name'
    for name,g in f.groupby(name_col):
        d={'name':name}
        w=g['_w'].to_numpy(float); ws=w.sum() or 1.0
        for c in avail:
            v=pd.to_numeric(g[c],errors='coerce').to_numpy(float); mask=np.isfinite(v)
            d[c]=float(np.average(v[mask],weights=w[mask])) if mask.any() else np.nan
        rows.append(d)
    hist=pd.DataFrame(rows)
    league={c:(pd.to_numeric(hist[c],errors='coerce').mean(),pd.to_numeric(hist[c],errors='coerce').std()) for c in avail}
    m=s.merge(hist,on='name',how='left',suffixes=('','_hist'))
    m['rb_talent_efficiency_applied']=False; m['rb_talent_rush_multiplier']=1.0; m['rb_talent_rec_multiplier']=1.0
    # Weights sum to 1 within rushing/receiving talent scores; unavailable fields simply drop out and re-normalize.
    rush_w={'yards_per_carry':.18,'rushing_epa_per_attempt':.18,'rushing_first_down_rate':.14,'yards_after_contact_per_attempt':.16,'missed_tackles_forced_per_attempt':.12,'explosive_run_rate':.10,'yards_created_per_attempt':.06,'success_rate':.06}
    rec_w={'yards_per_route_run':.34,'receiving_epa_per_target':.22,'yards_per_target':.18,'yac_per_reception':.14,'catch_rate':.12}
    elig=m.position.eq('RB') & m.projection_status.isin(['modeled_veteran','returning_fallback'])
    for i in m.index[elig]:
        def composite(wmap):
            vals=[]; ws=[]
            for c,w in wmap.items():
                if c in avail:
                    x=num(m.at[i,c],np.nan); mu,sd=league[c]
                    if np.isfinite(x): vals.append(zclip(x,mu,sd)); ws.append(w)
            return float(np.average(vals,weights=ws)) if ws else 0.0
        rz=composite(rush_w); qz=composite(rec_w)
        # Bounded so talent refines, never overwhelms, workload projection.
        rush_mult=float(np.clip(1+.055*rz,.90,1.10)); rec_mult=float(np.clip(1+.045*qz,.92,1.08))
        m.at[i,'projected_rushing_yards']=num(m.at[i,'projected_rushing_yards'],0)*rush_mult
        m.at[i,'projected_receiving_yards']=num(m.at[i,'projected_receiving_yards'],0)*rec_mult
        m.at[i,'rb_talent_efficiency_applied']=True; m.at[i,'rb_talent_rush_multiplier']=rush_mult; m.at[i,'rb_talent_rec_multiplier']=rec_mult
    all_elig=m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for i in m.index[all_elig]:
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=score(d,1); m.at[i,'half_ppr_points']=score(d,.5); m.at[i,'standard_points']=score(d,0)
        m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/GAMES; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/GAMES; m.at[i,'standard_per_game']=m.at[i,'standard_points']/GAMES
    for fcol in ['ppr_points','half_ppr_points','standard_points']:
        m[fcol.replace('_points','_overall_rank')]=m[fcol].rank(method='min',ascending=False); pc=fcol.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[fcol].notna(); m.loc[mask,pc]=m.loc[mask,fcol].rank(method='min',ascending=False)
    drop=[c for c in avail if c in m.columns and c not in s.columns]
    m=m.drop(columns=drop,errors='ignore'); nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(STATS,index=False)
    cols=['name','projected_rush_attempts','projected_rushing_yards','projected_targets','projected_receiving_yards','ppr_points','ppr_pos_rank','rb_talent_rush_multiplier','rb_talent_rec_multiplier']
    print(m[elig].sort_values('ppr_points',ascending=False)[cols].head(20).to_dict('records'))
if __name__=='__main__': main()
