#!/usr/bin/env python3
"""Apply dynamic RB concentration plus backfield-relative rushing efficiency.

True bell cows can exceed the old 72% soft threshold when competition is weak, while
committee leads are allowed below 60%. Within-backfield rushing efficiency modestly shifts
opportunity toward more explosive/effective runners. Rich metrics are consumed when present;
current nflverse fallbacks are YPC, rushing EPA/attempt and rushing first-down rate.
"""
from pathlib import Path
import re, unicodedata
import numpy as np
import pandas as pd

STATS=Path('data/projections/stat_projections_2026.csv')
ROLES=Path('data/projections/player_role_context_2026.csv')
COACH=Path('data/projections/coaching_scheme_context_2026.csv')
FEATS=Path('data/projections/player_features_2023_2025.csv')
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
    s=pd.read_csv(STATS); r=pd.read_csv(ROLES); c=pd.read_csv(COACH) if COACH.exists() else pd.DataFrame(); f=pd.read_csv(FEATS,low_memory=False) if FEATS.exists() else pd.DataFrame()
    keep=[x for x in ['name','position','team_2026','depth_rank','depth_starter','role_confidence','carries_per_game'] if x in r]
    rr=r[keep].rename(columns={'team_2026':'team'})
    m=s.merge(rr,on=['name','position','team'],how='left',suffixes=('','_role'))
    elig=m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model']) & m.position.eq('RB')
    coach={row.team:row for _,row in c.iterrows()} if len(c) else {}

    # Build recency-weighted RB rushing talent. Rich fields are used automatically when available.
    talent={}
    metric_w={'explosive_run_rate':.24,'missed_tackles_forced_per_attempt':.20,'yards_after_contact_per_attempt':.18,'rushing_epa_per_attempt':.14,'rushing_first_down_rate':.10,'success_rate':.08,'yards_per_carry':.06}
    if len(f):
        f=f[(f.position.eq('RB')) & f.season.isin([2023,2024,2025])].copy(); nc='player_display_name' if 'player_display_name' in f.columns else 'player_name'; f['nk']=f[nc].map(norm); f['_w']=f.season.map(SW).fillna(0.0)
        avail=[x for x in metric_w if x in f.columns]
        rows=[]
        for nk,g in f.groupby('nk'):
            d={'nk':nk}
            for col in avail:
                vals=pd.to_numeric(g[col],errors='coerce').to_numpy(float); ww=g['_w'].to_numpy(float); ok=np.isfinite(vals)&(ww>0)
                d[col]=float(np.average(vals[ok],weights=ww[ok])) if ok.any() else np.nan
            rows.append(d)
        h=pd.DataFrame(rows)
        league={col:(pd.to_numeric(h[col],errors='coerce').mean(),pd.to_numeric(h[col],errors='coerce').std()) for col in avail}
        for _,row in h.iterrows():
            zz=[]; ww=[]
            for col in avail:
                x=num(row.get(col),np.nan)
                if np.isfinite(x): mu,sd=league[col]; zz.append(z(x,mu,sd)); ww.append(metric_w[col])
            talent[row['nk']]=float(np.average(zz,weights=ww)) if ww else 0.0

    for col in ['rb_relative_efficiency_z','rb_relative_workload_multiplier','rb_dynamic_carry_ceiling']:
        m[col]=np.nan

    for team,g in m[elig].groupby('team'):
        idx=list(g.index); old=pd.to_numeric(m.loc[idx,'projected_rush_attempts'],errors='coerce').fillna(0.0); budget=float(old.sum())
        if budget<=0 or len(idx)<2: continue
        shares=(old/budget).to_numpy(copy=True); ranks=[]; starters=[]; rook=[]; picks=[]; hist=[]; ez=[]
        for i in idx:
            row=m.loc[i]; ranks.append(max(1,int(num(row.get('depth_rank'),4)))); starters.append(bool(row.get('depth_starter',False))); rook.append(row.get('projection_status')=='rookie_model'); picks.append(num(row.get('rb_workload_draft_pick'),999)); hist.append(max(0,num(row.get('carries_per_game'),0))); ez.append(talent.get(norm(row['name']),0.0))
        ez=np.asarray(ez,float); centered=ez-np.average(ez,weights=np.maximum(old.to_numpy(float),1.0)); eff_mult=np.clip(1+.085*centered,.90,1.12); shares*=eff_mult; shares/=shares.sum()
        leads=[j for j,(rk,st) in enumerate(zip(ranks,starters)) if rk==1 and st]
        cr=coach.get(team); rush_scheme=1.0
        if cr is not None:
            pri=num(cr.get('coach_pass_rate_index'),1.0); pvi=num(cr.get('coach_pass_volume_index'),1.0); conf=np.clip(num(cr.get('coaching_confidence'),0),0,1); rush_scheme=float(np.clip(1 + conf*(.55*(1-pri)+.25*(1-pvi)), .94, 1.08))
        if len(leads)==1:
            k=leads[0]
            comp=num(m.iloc[idx[k]].get('rb_competition_carry_score'),.50)
            # No automatic 60% floor. Strong competition can produce a real 1A/1B split.
            floor=float(np.clip(.50+.17*(1-comp)+.22*(rush_scheme-1),.48,.67))
            if rook[k] and picks[k]<=32: floor=max(floor,.58)
            if shares[k]<floor:
                need=floor-shares[k]; oth=np.arange(len(shares))!=k; pool=shares[oth].sum(); shares[oth]*=max(0,pool-need)/pool; shares[k]=floor
            # 72% becomes a soft tier. Weak competition + strong role can reach 75-80%.
            if comp<=.28 and centered[k]>=0: ceiling=.80
            elif comp<=.40: ceiling=.78
            elif comp<=.55: ceiling=.75
            else: ceiling=.72
            if shares[k]>ceiling:
                excess=shares[k]-ceiling; shares[k]=ceiling; oth=np.arange(len(shares))!=k; shares[oth]+=excess*shares[oth]/shares[oth].sum()
        else:
            floor=np.nan; ceiling=np.nan; k=-1
        for j,i in enumerate(idx):
            row=m.loc[i]; oc=max(num(row.get('projected_rush_attempts'),0),1e-6); nc=budget*shares[j]; ratio=nc/oc
            m.at[i,'projected_rush_attempts']=nc
            for col in ['projected_rushing_yards','projected_rushing_tds']: m.at[i,col]=num(row.get(col),0)*ratio
            m.at[i,'rb_bellcow_scheme_applied']=True; m.at[i,'rb_bellcow_carry_share']=shares[j]; m.at[i,'rb_bellcow_lead_floor']=floor if j==k else np.nan; m.at[i,'rb_rush_scheme_multiplier']=rush_scheme
            m.at[i,'rb_relative_efficiency_z']=ez[j]; m.at[i,'rb_relative_workload_multiplier']=eff_mult[j]; m.at[i,'rb_dynamic_carry_ceiling']=ceiling if j==k else np.nan
    all_elig=m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for i in m.index[all_elig]:
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=score(d,1); m.at[i,'half_ppr_points']=score(d,.5); m.at[i,'standard_points']=score(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/17; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/17; m.at[i,'standard_per_game']=m.at[i,'standard_points']/17
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        m[fc.replace('_points','_overall_rank')]=m[fc].rank(method='min',ascending=False); pc=fc.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    drop=[x for x in m.columns if x.endswith('_role') or x in {'depth_rank','depth_starter','role_confidence','carries_per_game'}]; m=m.drop(columns=drop,errors='ignore'); nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(STATS,index=False)
    watch=['TreVeyon Henderson','Rhamondre Stevenson','Rico Dowdle','Jaylen Warren','Jeremiyah Love','Omarion Hampton','Kenneth Walker III']
    cols=['name','team','projected_rush_attempts','projected_rushing_yards','ppr_points','ppr_pos_rank','rb_bellcow_carry_share','rb_relative_efficiency_z','rb_relative_workload_multiplier','rb_dynamic_carry_ceiling']
    print(m[m.name.isin(watch)][cols].to_dict('records'))
if __name__=='__main__': main()
