#!/usr/bin/env python3
"""Apply an evidence-sensitive age curve to veteran RB projections.

Uses nflverse players data for birth dates. Identity resolution is deliberately robust:
try every stable ID shared by the projection and nflverse tables first, then multiple
unambiguous normalized name forms. Age is calculated on 2026-09-01. No player overrides.
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
    d=pd.Timestamp(dob); return ASOF.year-d.year-((ASOF.month,ASOF.day)<(d.month,d.day))
def main():
    m=pd.read_csv(P); p=pd.read_csv(PLAYERS_URL,low_memory=False)
    birth_col=next((c for c in ['birth_date','birthdate','date_of_birth'] if c in p.columns),None)
    if birth_col is None: raise SystemExit('nflverse players dataset missing birth date')
    p[birth_col]=pd.to_datetime(p[birth_col],errors='coerce'); p['_age']=p[birth_col].map(age_on)
    m['rb_age_2026']=np.nan; m['rb_age_match_method']='unmatched'
    # Stable identifiers, in preferred order. nflverse documents gsis_id as its primary key.
    aliases=[('gsis_id','gsis_id'),('player_id','gsis_id'),('espn_id','espn_id'),('pfr_id','pfr_id'),('pff_id','pff_id'),('nfl_id','nfl_id'),('smart_id','smart_id'),('esb_id','esb_id')]
    for mc,pc in aliases:
        if mc not in m.columns or pc not in p.columns: continue
        src=p[[pc,'_age']].dropna().copy(); src[pc]=src[pc].astype(str).str.strip(); src=src[src[pc].ne('')]
        # Never use an ambiguous identifier.
        counts=src.groupby(pc)['_age'].nunique(); valid=set(counts[counts.eq(1)].index); src=src[src[pc].isin(valid)].drop_duplicates(pc)
        lookup=dict(zip(src[pc],src['_age']))
        for i in m.index[m['rb_age_2026'].isna()]:
            v=m.at[i,mc]
            if pd.notna(v) and str(v).strip() in lookup:
                m.at[i,'rb_age_2026']=lookup[str(v).strip()]; m.at[i,'rb_age_match_method']=f'{mc}->{pc}'
    # Name fallback across every useful nflverse name representation, only when unambiguous.
    name_cols=[c for c in ['display_name','full_name','football_name','short_name'] if c in p.columns]
    if {'first_name','last_name'}.issubset(p.columns): p['_constructed_name']=p['first_name'].fillna('')+' '+p['last_name'].fillna(''); name_cols.append('_constructed_name')
    if {'common_first_name','last_name'}.issubset(p.columns): p['_common_name']=p['common_first_name'].fillna('')+' '+p['last_name'].fillna(''); name_cols.append('_common_name')
    pairs=[]
    for c in name_cols:
        q=p[[c,'_age']].dropna().copy(); q['_key']=q[c].map(norm_name); q=q[q['_key'].ne('')]; pairs.append(q[['_key','_age']])
    if pairs:
        q=pd.concat(pairs,ignore_index=True).drop_duplicates(); counts=q.groupby('_key')['_age'].nunique(); valid=set(counts[counts.eq(1)].index); q=q[q['_key'].isin(valid)].drop_duplicates('_key'); lookup=dict(zip(q['_key'],q['_age']))
        for i in m.index[m['rb_age_2026'].isna()]:
            key=norm_name(m.at[i,'name'])
            if key in lookup: m.at[i,'rb_age_2026']=lookup[key]; m.at[i,'rb_age_match_method']='unambiguous_name'
    m['rb_age_curve_applied']=False; m['rb_age_baseline_multiplier']=1.; m['rb_age_evidence_recovery']=0.; m['rb_age_workload_multiplier']=1.; m['rb_age_efficiency_multiplier']=1.
    elig=m.position.eq('RB') & m.projection_status.isin(['modeled_veteran','returning_fallback']); base={29:.99,30:.95,31:.90,32:.84,33:.78}
    for i in m.index[elig]:
        age=n(m.at[i,'rb_age_2026'],np.nan)
        if not np.isfinite(age) or age<29: continue
        a=int(age); b=base.get(a,.74 if a>=34 else 1.); ppg=n(m.at[i,'ppr_per_game']); touches=n(m.at[i,'projected_rush_attempts'])+n(m.at[i,'projected_targets']); role=n(m.at[i,'rb_achievability_role_factor'],1.) if 'rb_achievability_role_factor' in m else 1.; comp=max(n(m.at[i,'rb_competition_carry_score'],.5) if 'rb_competition_carry_score' in m else .5,n(m.at[i,'rb_competition_target_score'],.5) if 'rb_competition_target_score' in m else .5)
        elite=np.clip((ppg-12)/10,0,1)*.45+np.clip((touches-230)/170,0,1)*.30+np.clip((role-.85)/.25,0,1)*.25; recovery=np.clip(elite*(1-.45*comp),0,.80); workload=b+(1-b)*recovery; eff=1-(1-workload)*.35
        for c in ['projected_rush_attempts','projected_targets','projected_receptions']: m.at[i,c]=n(m.at[i,c])*workload
        m.at[i,'projected_rushing_yards']=n(m.at[i,'projected_rushing_yards'])*workload*eff; m.at[i,'projected_receiving_yards']=n(m.at[i,'projected_receiving_yards'])*workload*(1-(1-workload)*.18); m.at[i,'projected_rushing_tds']=n(m.at[i,'projected_rushing_tds'])*workload; m.at[i,'projected_receiving_tds']=n(m.at[i,'projected_receiving_tds'])*workload
        m.at[i,'rb_age_curve_applied']=True; m.at[i,'rb_age_baseline_multiplier']=b; m.at[i,'rb_age_evidence_recovery']=recovery; m.at[i,'rb_age_workload_multiplier']=workload; m.at[i,'rb_age_efficiency_multiplier']=eff
    projected=m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for i in m.index[projected]:
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=score(d,1); m.at[i,'half_ppr_points']=score(d,.5); m.at[i,'standard_points']=score(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/17; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/17; m.at[i,'standard_per_game']=m.at[i,'standard_points']/17
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        m[fc.replace('_points','_overall_rank')]=m[fc].rank(method='min',ascending=False); pc=fc.replace('_points','_pos_rank'); m[pc]=np.nan
        for pos in ['QB','RB','WR','TE']:
            mask=m.position.eq(pos)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(P,index=False)
    watch=['Christian McCaffrey','Derrick Henry','Alvin Kamara','Aaron Jones Sr.']; print(m[m.name.isin(watch)][['name','rb_age_2026','rb_age_match_method','rb_age_baseline_multiplier','rb_age_evidence_recovery','rb_age_workload_multiplier','ppr_points','ppr_pos_rank']].to_dict('records')); print('RB age matches',m.loc[elig,'rb_age_match_method'].value_counts(dropna=False).to_dict()); print('unmatched veteran RBs',m.loc[elig & m.rb_age_2026.isna(),'name'].tolist())
if __name__=='__main__': main()
