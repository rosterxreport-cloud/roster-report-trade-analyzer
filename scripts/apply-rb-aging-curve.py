#!/usr/bin/env python3
"""Apply an evidence-sensitive age curve to veteran RB projections.

Uses nflverse's players dataset for birth dates. Age is calculated on 2026-09-01.
The curve is deliberately modest at age 30 and accelerates thereafter. Recent elite
production/workload and secure role can earn back much of the baseline penalty.
No player-specific overrides.
"""
from pathlib import Path
import re, unicodedata
import numpy as np
import pandas as pd

P=Path('data/projections/stat_projections_2026.csv')
PLAYERS_URL='https://github.com/nflverse/nflverse-data/releases/download/players/players.csv'
ASOF=pd.Timestamp('2026-09-01')

def n(v,d=0.):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except: return d

def norm_name(v):
    t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower()
    t=re.sub(r'\b(jr|sr|ii|iii|iv|v)\.?\b','',t)
    return re.sub(r'[^a-z0-9]','',t)

def score(r,rec=1.):
    return .1*n(r.get('projected_rushing_yards'))+6*n(r.get('projected_rushing_tds'))+rec*n(r.get('projected_receptions'))+.1*n(r.get('projected_receiving_yards'))+6*n(r.get('projected_receiving_tds'))+.04*n(r.get('projected_passing_yards'))+4*n(r.get('projected_passing_tds'))-2*n(r.get('projected_interceptions'))

def age_on(dob):
    if pd.isna(dob): return np.nan
    d=pd.Timestamp(dob)
    return ASOF.year-d.year-((ASOF.month,ASOF.day)<(d.month,d.day))

def main():
    m=pd.read_csv(P)
    p=pd.read_csv(PLAYERS_URL,low_memory=False)
    birth_col=next((c for c in ['birth_date','birthdate','date_of_birth'] if c in p.columns),None)
    id_col=next((c for c in ['gsis_id','player_id'] if c in p.columns),None)
    name_col=next((c for c in ['display_name','player_display_name','full_name'] if c in p.columns),None)
    if birth_col is None: raise SystemExit('nflverse players dataset missing birth date')
    p[birth_col]=pd.to_datetime(p[birth_col],errors='coerce')
    p['rb_age_2026_source']=p[birth_col].map(age_on)
    m['rb_age_2026']=np.nan
    m['rb_age_match_method']='unmatched'

    # First pass: stable GSIS/player ID where possible.
    if 'player_id' in m.columns and id_col:
        ages=p[[id_col,'rb_age_2026_source']].dropna(subset=[id_col,'rb_age_2026_source']).drop_duplicates(id_col).rename(columns={id_col:'player_id'})
        lookup=dict(zip(ages['player_id'].astype(str),ages['rb_age_2026_source']))
        for i in m.index:
            pid=m.at[i,'player_id']
            if pd.notna(pid) and str(pid) in lookup:
                m.at[i,'rb_age_2026']=lookup[str(pid)]
                m.at[i,'rb_age_match_method']='player_id'

    # Second pass: normalized display-name fallback only for unmatched rows.
    if name_col is not None:
        pn=p[[name_col,'rb_age_2026_source']].dropna(subset=[name_col,'rb_age_2026_source']).copy()
        pn['name_key']=pn[name_col].map(norm_name)
        # Use only unambiguous normalized names to avoid false matches.
        counts=pn.groupby('name_key')['rb_age_2026_source'].nunique()
        valid=set(counts[counts.eq(1)].index)
        pn=pn[pn['name_key'].isin(valid)].drop_duplicates('name_key')
        name_lookup=dict(zip(pn['name_key'],pn['rb_age_2026_source']))
        for i in m.index[m['rb_age_2026'].isna()]:
            key=norm_name(m.at[i,'name'])
            if key in name_lookup:
                m.at[i,'rb_age_2026']=name_lookup[key]
                m.at[i,'rb_age_match_method']='normalized_name'

    m['rb_age_curve_applied']=False; m['rb_age_baseline_multiplier']=1.; m['rb_age_evidence_recovery']=0.; m['rb_age_workload_multiplier']=1.; m['rb_age_efficiency_multiplier']=1.
    elig=m.position.eq('RB') & m.projection_status.isin(['modeled_veteran','returning_fallback'])
    base={29:.99,30:.95,31:.90,32:.84,33:.78}
    for i in m.index[elig]:
        age=n(m.at[i,'rb_age_2026'],np.nan)
        if not np.isfinite(age) or age<29: continue
        a=int(age); b=base.get(a,.74 if a>=34 else 1.)
        ppg=n(m.at[i,'ppr_per_game'],0); touches=n(m.at[i,'projected_rush_attempts'])+n(m.at[i,'projected_targets'])
        role=n(m.at[i,'rb_achievability_role_factor'],1.) if 'rb_achievability_role_factor' in m else 1.
        comp=max(n(m.at[i,'rb_competition_carry_score'],.5) if 'rb_competition_carry_score' in m else .5,n(m.at[i,'rb_competition_target_score'],.5) if 'rb_competition_target_score' in m else .5)
        elite=np.clip((ppg-12)/10,0,1)*.45 + np.clip((touches-230)/170,0,1)*.30 + np.clip((role-.85)/.25,0,1)*.25
        recovery=np.clip(elite*(1-.45*comp),0,.80)
        workload=b+(1-b)*recovery
        eff=1-(1-workload)*.35
        for c in ['projected_rush_attempts','projected_targets','projected_receptions']:
            m.at[i,c]=n(m.at[i,c])*workload
        m.at[i,'projected_rushing_yards']=n(m.at[i,'projected_rushing_yards'])*workload*eff
        m.at[i,'projected_receiving_yards']=n(m.at[i,'projected_receiving_yards'])*workload*(1-(1-workload)*.18)
        m.at[i,'projected_rushing_tds']=n(m.at[i,'projected_rushing_tds'])*workload
        m.at[i,'projected_receiving_tds']=n(m.at[i,'projected_receiving_tds'])*workload
        m.at[i,'rb_age_curve_applied']=True; m.at[i,'rb_age_baseline_multiplier']=b; m.at[i,'rb_age_evidence_recovery']=recovery; m.at[i,'rb_age_workload_multiplier']=workload; m.at[i,'rb_age_efficiency_multiplier']=eff
    for i in m.index[m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])]:
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=score(d,1); m.at[i,'half_ppr_points']=score(d,.5); m.at[i,'standard_points']=score(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/17; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/17; m.at[i,'standard_per_game']=m.at[i,'standard_points']/17
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        m[fc.replace('_points','_overall_rank')]=m[fc].rank(method='min',ascending=False); pc=fc.replace('_points','_pos_rank'); m[pc]=np.nan
        for pos in ['QB','RB','WR','TE']:
            mask=m.position.eq(pos)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(P,index=False)
    watch=['Christian McCaffrey','Derrick Henry','Alvin Kamara','Aaron Jones Sr.']
    print(m[m.name.isin(watch)][['name','rb_age_2026','rb_age_match_method','rb_age_baseline_multiplier','rb_age_evidence_recovery','rb_age_workload_multiplier','ppr_points','ppr_pos_rank']].to_dict('records'))
    print('RB age matches',m.loc[elig,'rb_age_match_method'].value_counts(dropna=False).to_dict())
if __name__=='__main__': main()
