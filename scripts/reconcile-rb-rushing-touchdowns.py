#!/usr/bin/env python3
"""Reconcile RB rushing TDs using high-value opportunity, hierarchy and team TD budget.

Uses explicit red-zone/goal-line fields when available; otherwise falls back to current
carry share + depth hierarchy proxies. Team RB rushing-TD budget is preserved.
"""
from pathlib import Path
import numpy as np
import pandas as pd

STATS=Path('data/projections/stat_projections_2026.csv')
ROLES=Path('data/projections/player_role_context_2026.csv')
GAMES=17.0

def num(v,d=0.0):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except (TypeError,ValueError): return d

def points(r,rec=1.0):
    x=lambda k:num(r.get(k),0)
    return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')

def main():
    s=pd.read_csv(STATS); roles=pd.read_csv(ROLES)
    keep=[c for c in ['name','position','team_2026','depth_rank','depth_starter','rookie','draft_pick','role_confidence'] if c in roles]
    rr=roles[keep].rename(columns={'team_2026':'team'})
    m=s.merge(rr,on=['name','position','team'],how='left',suffixes=('','_role'))
    elig=m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model']) & m.position.eq('RB')
    for c in ['rb_rush_td_reconciled','rb_rush_td_share','rb_rush_td_team_budget','rb_goal_line_score','rb_goal_line_proxy_used','rb_rush_td_sanity_adjusted']:
        m[c]=False if c in ['rb_rush_td_reconciled','rb_goal_line_proxy_used','rb_rush_td_sanity_adjusted'] else np.nan
    for team,g in m[elig].groupby('team'):
        idx=list(g.index)
        if not idx: continue
        old_td=pd.to_numeric(m.loc[idx,'projected_rushing_tds'],errors='coerce').fillna(0.0)
        carries=pd.to_numeric(m.loc[idx,'projected_rush_attempts'],errors='coerce').fillna(0.0)
        if carries.sum()<=0: continue
        budget=float(np.clip(old_td.sum(), max(1.5,carries.sum()*.012), max(3.0,carries.sum()*.055)))
        cshare=(carries/carries.sum()).to_numpy()
        weights=[]; proxies=[]; glscores=[]
        for j,i in enumerate(idx):
            row=m.loc[i]; rank=max(1,int(num(row.get('depth_rank'),4))); starter=bool(row.get('depth_starter',False))
            depth={1:1.00,2:.58,3:.28,4:.12}.get(rank,.08); depth*=1.10 if starter else 1.0
            att=max(num(row.get('projected_rush_attempts'),0),1.0)
            old_rate=num(row.get('projected_rushing_tds'),0)/att; reg_rate=np.clip(old_rate/.035,.65,1.35)
            # Prefer explicit high-value opportunity if it exists in future feeds.
            gl=num(row.get('goal_line_carries'),np.nan); iz5=num(row.get('inside_5_carries'),np.nan); rz=num(row.get('red_zone_carries'),np.nan); iz10=num(row.get('inside_10_carries'),np.nan)
            explicit=[x for x in [gl,iz5,rz,iz10] if np.isfinite(x) and x>=0]
            if explicit:
                hv=(1.00*(iz5 if np.isfinite(iz5) else 0)+.75*(gl if np.isfinite(gl) else 0)+.45*(iz10 if np.isfinite(iz10) else 0)+.20*(rz if np.isfinite(rz) else 0))
                glscore=max(.01,hv)
                proxy=False
            else:
                # Proxy high-value work from current carry share + current hierarchy, not old TD totals.
                glscore=max(.01,.72*cshare[j]+.28*(depth/1.10))
                proxy=True
            rookie=bool(row.get('rookie',False)); pick=num(row.get('draft_pick'),999); capital=1.08 if rookie and pick<=32 else (1.04 if rookie and pick<=64 else 1.0)
            # 50% high-value opportunity, 30% carry share, 15% hierarchy, 5% regressed conversion history.
            w=(.50*glscore+.30*cshare[j]+.15*(depth/1.10)+.05*reg_rate)*capital
            weights.append(max(.001,w)); proxies.append(proxy); glscores.append(glscore)
        w=np.asarray(weights,float); w=w/w.sum()
        if len(w)>1 and w.max()>.72:
            k=int(w.argmax()); excess=w[k]-.72; w[k]=.72; oth=np.arange(len(w))!=k; w[oth]+=excess*w[oth]/w[oth].sum()
        tds=budget*w
        # Sanity: backs without explicit goal-line evidence cannot own extreme TD rates on small workloads.
        caps=[]
        for j,i in enumerate(idx):
            att=max(carries.iloc[j],1.0); cap_rate=.060 if cshare[j]>=.55 else (.050 if cshare[j]>=.35 else .042)
            cap=max(1.5,att*cap_rate); caps.append(cap)
        caps=np.asarray(caps); excess=float(np.maximum(tds-caps,0).sum()); clipped=tds>caps; tds=np.minimum(tds,caps)
        # redistribute clipped TDs to uncapped backs by remaining allocation weight
        for _ in range(3):
            room=np.maximum(caps-tds,0); mask=room>1e-9
            if excess<=1e-9 or not mask.any(): break
            rw=w*mask; rw=rw/rw.sum(); add=np.minimum(room,excess*rw); tds+=add; excess-=add.sum()
        if excess>1e-6: tds*=budget/max(tds.sum(),1e-9)
        for j,i in enumerate(idx):
            m.at[i,'projected_rushing_tds']=tds[j]; m.at[i,'rb_rush_td_reconciled']=True; m.at[i,'rb_rush_td_share']=tds[j]/max(budget,1e-9); m.at[i,'rb_rush_td_team_budget']=budget; m.at[i,'rb_goal_line_score']=glscores[j]; m.at[i,'rb_goal_line_proxy_used']=proxies[j]; m.at[i,'rb_rush_td_sanity_adjusted']=bool(clipped[j])
    for i in m[m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])].index:
        d=m.loc[i].to_dict()
        for rec,f in [(1,'ppr_points'),(.5,'half_ppr_points'),(0,'standard_points')]: m.at[i,f]=points(d,rec)
        m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/GAMES; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/GAMES; m.at[i,'standard_per_game']=m.at[i,'standard_points']/GAMES
    for f in ['ppr_points','half_ppr_points','standard_points']:
        m[f.replace('_points','_overall_rank')]=m[f].rank(method='min',ascending=False); pc=f.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[f].notna(); m.loc[mask,pc]=m.loc[mask,f].rank(method='min',ascending=False)
    drop=[c for c in m.columns if c.endswith('_role') or c in {'depth_rank','depth_starter','rookie','draft_pick','role_confidence'}]
    m=m.drop(columns=drop,errors='ignore'); nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(STATS,index=False)
    watch=['Jeremiyah Love','Kenneth Walker III','David Montgomery','Rhamondre Stevenson','Justice Hill']
    print(m[m.name.isin(watch)][['name','team','projected_rush_attempts','projected_rushing_tds','rb_rush_td_share','rb_goal_line_proxy_used','rb_rush_td_sanity_adjusted','ppr_points','ppr_pos_rank']].to_dict('records'))

if __name__=='__main__': main()
