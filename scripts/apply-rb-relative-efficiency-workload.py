#!/usr/bin/env python3
"""Adjust RB workload modestly for backfield-relative rushing talent and use dynamic carry ceilings.

This layer sits after current-role workload reconciliation. It does not manufacture team RB carries;
it redistributes them based on within-backfield efficiency evidence. Rich metrics such as explosive-run
rate, missed tackles forced/attempt and yards after contact/attempt are consumed automatically when
present. Current nflverse fallbacks are YPC, rushing EPA/attempt and first-down rate.
"""
from pathlib import Path
import re, unicodedata
import numpy as np
import pandas as pd

STATS=Path('data/projections/stat_projections_2026.csv')
FEATS=Path('data/projections/player_features_2023_2025.csv')
GAMES=17.0
SW={2023:.20,2024:.30,2025:.50}

def num(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except (TypeError,ValueError): return d

def norm(v):
    t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower()
    t=re.sub(r'\b(jr|sr|ii|iii|iv)\.?\b','',t)
    return re.sub(r'[^a-z0-9]','',t)

def score(r,rec=1.0):
    x=lambda k:num(r.get(k),0.0)
    return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')

def z(x,mu,sd):
    if not np.isfinite(x) or not np.isfinite(mu) or not np.isfinite(sd) or sd<=0: return 0.0
    return float(np.clip((x-mu)/sd,-2.5,2.5))

def main():
    s=pd.read_csv(STATS); f=pd.read_csv(FEATS,low_memory=False)
    f=f[(f.position.eq('RB')) & f.season.isin([2023,2024,2025])].copy()
    name_col='player_display_name' if 'player_display_name' in f.columns else 'player_name'
    f['nk']=f[name_col].map(norm); f['_w']=f.season.map(SW).fillna(0.0)
    metrics={
        'explosive_run_rate':.24,
        'missed_tackles_forced_per_attempt':.20,
        'yards_after_contact_per_attempt':.18,
        'rushing_epa_per_attempt':.14,
        'rushing_first_down_rate':.10,
        'success_rate':.08,
        'yards_per_carry':.06,
    }
    avail=[c for c in metrics if c in f.columns]
    rows=[]
    for nk,g in f.groupby('nk'):
        d={'nk':nk}
        for c in avail:
            vals=pd.to_numeric(g[c],errors='coerce').to_numpy(float); w=g['_w'].to_numpy(float); ok=np.isfinite(vals)&(w>0)
            d[c]=float(np.average(vals[ok],weights=w[ok])) if ok.any() else np.nan
        rows.append(d)
    h=pd.DataFrame(rows)
    league={c:(pd.to_numeric(h[c],errors='coerce').mean(),pd.to_numeric(h[c],errors='coerce').std()) for c in avail}
    h['eff_z']=0.0
    if len(h):
        vals=[]
        for _,r in h.iterrows():
            zz=[]; ww=[]
            for c in avail:
                x=num(r.get(c),np.nan)
                if np.isfinite(x):
                    mu,sd=league[c]; zz.append(z(x,mu,sd)); ww.append(metrics[c])
            vals.append(float(np.average(zz,weights=ww)) if ww else 0.0)
        h['eff_z']=vals
    m=s.copy(); m['nk']=m['name'].map(norm); m=m.merge(h[['nk','eff_z']],on='nk',how='left'); m['eff_z']=m['eff_z'].fillna(0.0)
    for c in ['rb_relative_efficiency_applied','rb_relative_efficiency_z','rb_relative_workload_multiplier','rb_dynamic_carry_ceiling']:
        m[c]=False if c=='rb_relative_efficiency_applied' else np.nan
    elig=m.position.eq('RB') & m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for team,g in m[elig].groupby('team'):
        idx=list(g.index)
        if len(idx)<2: continue
        carries=pd.to_numeric(m.loc[idx,'projected_rush_attempts'],errors='coerce').fillna(0.0).to_numpy(float)
        budget=float(carries.sum())
        if budget<=0: continue
        shares=carries/budget
        ez=m.loc[idx,'eff_z'].to_numpy(float)
        # Within-backfield talent delta matters more than league rank itself.
        centered=ez-np.average(ez,weights=np.maximum(carries,1.0))
        mult=np.clip(1.0+.085*centered,.90,1.12)
        raw=shares*mult; raw=raw/raw.sum()
        # Dynamic ceiling: 72% is now a soft threshold, not a hard cap.
        # Strongly concentrated backs with weak recorded competition can reach 78-80%; committees remain unrestricted below 60%.
        comp=pd.to_numeric(m.loc[idx].get('rb_competition_carry_score',pd.Series(np.nan,index=idx)),errors='coerce').to_numpy(float)
        lead=int(np.argmax(raw)); cscore=comp[lead] if np.isfinite(comp[lead]) else .50
        lead_eff=centered[lead]
        if cscore<=.28 and lead_eff>=0: ceiling=.80
        elif cscore<=.40: ceiling=.78
        elif cscore<=.55: ceiling=.75
        else: ceiling=.72
        # Only cap if necessary; there is deliberately no artificial 60% floor for depth-chart RB1s.
        if raw[lead]>ceiling and len(raw)>1:
            excess=raw[lead]-ceiling; raw[lead]=ceiling; oth=np.arange(len(raw))!=lead; pool=raw[oth].sum(); raw[oth]+=excess*raw[oth]/pool
        for j,i in enumerate(idx):
            old=max(num(m.at[i,'projected_rush_attempts'],0),1e-6); new=budget*raw[j]; ratio=new/old
            m.at[i,'projected_rush_attempts']=new
            m.at[i,'projected_rushing_yards']=num(m.at[i,'projected_rushing_yards'],0)*ratio
            m.at[i,'projected_rushing_tds']=num(m.at[i,'projected_rushing_tds'],0)*ratio
            m.at[i,'rb_relative_efficiency_applied']=True
            m.at[i,'rb_relative_efficiency_z']=ez[j]
            m.at[i,'rb_relative_workload_multiplier']=mult[j]
            m.at[i,'rb_dynamic_carry_ceiling']=ceiling if j==lead else np.nan
    for i in m.index[m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])]:
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=score(d,1); m.at[i,'half_ppr_points']=score(d,.5); m.at[i,'standard_points']=score(d,0)
        m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/GAMES; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/GAMES; m.at[i,'standard_per_game']=m.at[i,'standard_points']/GAMES
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        m[fc.replace('_points','_overall_rank')]=m[fc].rank(method='min',ascending=False); pc=fc.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    m=m.drop(columns=['nk','eff_z'],errors='ignore'); nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(STATS,index=False)
    watch=['TreVeyon Henderson','Rhamondre Stevenson','Rico Dowdle','Jaylen Warren','Omarion Hampton','Jeremiyah Love','Kenneth Walker III']
    cols=['name','team','projected_rush_attempts','projected_rushing_yards','ppr_points','ppr_pos_rank','rb_relative_efficiency_z','rb_relative_workload_multiplier','rb_dynamic_carry_ceiling']
    print(m[m.name.isin(watch)][cols].to_dict('records'))
if __name__=='__main__': main()
