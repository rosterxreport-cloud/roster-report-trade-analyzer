#!/usr/bin/env python3
"""Reconcile RB workload using current hierarchy plus continuous competition strength.

Current role is the anchor. Competition strength is evaluated separately for carries and
receiving so a back can face a rushing 1B, a passing-down specialist, both, or neither.
Team RB opportunity is preserved and no player-specific overrides are used.
"""
from pathlib import Path
import re, unicodedata
import numpy as np
import pandas as pd

GAMES=17.0
STATS=Path('data/projections/stat_projections_2026.csv')
ROLES=Path('data/projections/player_role_context_2026.csv')
DRAFT=Path('data/projections/draft_picks_normalized.csv')

def num(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except (TypeError,ValueError): return d

def norm_name(v):
    t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower()
    t=re.sub(r'\b(jr|sr|ii|iii|iv)\.?\b','',t)
    return re.sub(r'[^a-z0-9]','',t)

def score(r,rec=1.0):
    x=lambda k:num(r.get(k),0.0)
    return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')

def draft_signal(pick):
    if pick<=32: return 1.0
    if pick<=64: return .78
    if pick<=120: return .55
    if pick<=180: return .35
    return .18

def main():
    s=pd.read_csv(STATS); r=pd.read_csv(ROLES)
    keep=[c for c in ['name','position','team_2026','depth_rank','depth_starter','role_carry_share_2026','role_target_share_2026','carries_per_game','targets_per_game','projected_rush_attempts','projected_pass_attempts','rookie','role_confidence'] if c in r]
    rr=r[keep].copy().rename(columns={'team_2026':'team'}); rr['name_key']=rr['name'].map(norm_name)
    if DRAFT.exists():
        d=pd.read_csv(DRAFT,low_memory=False)
        if {'full_name','pick'}.issubset(d.columns):
            d=d.copy(); d['name_key']=d['full_name'].map(norm_name)
            if 'season' in d.columns:
                season=pd.to_numeric(d['season'],errors='coerce'); d=d[season.isin([2025,2026])]
            d['draft_pick_direct']=pd.to_numeric(d['pick'],errors='coerce')
            d=d.sort_values('draft_pick_direct').drop_duplicates('name_key',keep='first')
            rr=rr.merge(d[['name_key','draft_pick_direct']],on='name_key',how='left')
    if 'draft_pick_direct' not in rr: rr['draft_pick_direct']=np.nan
    m=s.merge(rr.drop(columns=['name_key']),on=['name','position','team'],how='left',suffixes=('','_role'))
    eligible=m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model']) & m.position.eq('RB')
    for col in ['rb_competition_carry_score','rb_competition_target_score','rb_competition_adjustment']:
        m[col]=np.nan

    for team,g in m[eligible].groupby('team'):
        idx=list(g.index)
        if not idx: continue
        team_rush=num(g['projected_rush_attempts_role'].dropna().iloc[0],np.nan) if 'projected_rush_attempts_role' in g and g['projected_rush_attempts_role'].notna().any() else np.nan
        old_c=pd.to_numeric(m.loc[idx,'projected_rush_attempts'],errors='coerce').fillna(0.0)
        old_t=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0.0)
        carry_budget=min(old_c.sum(),team_rush*.86) if np.isfinite(team_rush) else old_c.sum(); target_budget=old_t.sum()
        if carry_budget<=0: continue
        cw=[]; tw=[]; ranks=[]; starters=[]; picks=[]; role_cs=[]; role_ts=[]; cpgs=[]; tpgs=[]; confs=[]
        for i in idx:
            row=m.loc[i]; rank=max(1,int(num(row.get('depth_rank'),4))); starter=bool(row.get('depth_starter',False)); conf=np.clip(num(row.get('role_confidence'),.55),0,1)
            depth_c={1:1.00,2:.58,3:.32,4:.18}.get(rank,.10); depth_t={1:1.00,2:.68,3:.42,4:.25}.get(rank,.15)
            if starter: depth_c*=1.10; depth_t*=1.06
            role_c=np.clip(num(row.get('role_carry_share_2026'),.12),.01,.90); role_t=np.clip(num(row.get('role_target_share_2026'),.04),.005,.35)
            cpg=max(0,num(row.get('carries_per_game'),0)); tpg=max(0,num(row.get('targets_per_game'),0)); hist_c=cpg*GAMES; hist_t=tpg*GAMES
            # Historical usage decays quickly when current depth position is reduced.
            hist_decay={1:1.0,2:.62,3:.38,4:.22}.get(rank,.15)
            hist_c_share=(hist_c/max(hist_c+90,1))*hist_decay; hist_t_share=(hist_t/max(hist_t+45,1))*hist_decay
            rookie=bool(row.get('rookie',False)) or row.get('projection_status')=='rookie_model'; pick=num(row.get('draft_pick_direct'),999)
            capital=1.22 if rookie and pick<=32 else (1.12 if rookie and pick<=64 else (1.05 if rookie and pick<=120 else 1.0))
            c=(.60*depth_c+.25*(role_c/.35)+.15*hist_c_share)*capital
            t=(.55*depth_t+.25*(role_t/.10)+.20*hist_t_share)*(1.10 if rookie and pick<=32 else 1.0)
            cw.append(max(.01,c)); tw.append(max(.01,t)); ranks.append(rank); starters.append(starter); picks.append(pick); role_cs.append(role_c); role_ts.append(role_t); cpgs.append(cpg); tpgs.append(tpg); confs.append(conf)
        cw=np.asarray(cw,float); tw=np.asarray(tw,float); cw/=cw.sum(); tw/=tw.sum()

        lead=[j for j,(rk,st) in enumerate(zip(ranks,starters)) if rk==1 and st]
        lead_floor=np.nan; lead_t_floor=np.nan; carry_comp=np.nan; target_comp=np.nan
        if len(lead)==1 and len(idx)>1:
            k=lead[0]
            backup_c=[]; backup_t=[]
            for j in range(len(idx)):
                if j==k: continue
                depth_sig={2:.90,3:.55,4:.28}.get(ranks[j],.18)
                ds=draft_signal(picks[j])
                carry_claim=.30*np.clip(role_cs[j]/.30,0,1)+.25*np.clip(cpgs[j]/13,0,1)+.18*depth_sig+.12*ds+.15*confs[j]
                target_claim=.30*np.clip(role_ts[j]/.10,0,1)+.25*np.clip(tpgs[j]/4.0,0,1)+.18*depth_sig+.12*ds+.15*confs[j]
                backup_c.append(float(np.clip(carry_claim,0,1))); backup_t.append(float(np.clip(target_claim,0,1)))
            def combine(vals):
                vals=sorted(vals,reverse=True)
                if not vals: return 0.0
                return float(np.clip(.72*vals[0]+(.28*vals[1] if len(vals)>1 else 0),0,1))
            carry_comp=combine(backup_c); target_comp=combine(backup_t)
            # Continuous concentration: weak competition earns a stronger floor, strong 1B competition lowers it.
            lead_floor=float(np.clip(.54+.15*(1-carry_comp),.54,.69))
            if picks[k]<=32: lead_floor=min(.70,lead_floor+.025)
            lead_t_floor=float(np.clip(.38+.18*(1-target_comp),.38,.56))
            # Competition also nudges the unconstrained allocation rather than only acting as a hard floor.
            c_adj=float(np.clip(1+.22*(.50-carry_comp),.88,1.12)); t_adj=float(np.clip(1+.20*(.50-target_comp),.90,1.10))
            cw[k]*=c_adj; tw[k]*=t_adj; cw/=cw.sum(); tw/=tw.sum()
            if cw[k]<lead_floor:
                need=lead_floor-cw[k]; oth=np.arange(len(cw))!=k; pool=cw[oth].sum(); cw[oth]*=max(0,pool-need)/pool; cw[k]=lead_floor
            if tw[k]<lead_t_floor:
                need=lead_t_floor-tw[k]; oth=np.arange(len(tw))!=k; pool=tw[oth].sum(); tw[oth]*=max(0,pool-need)/pool; tw[k]=lead_t_floor
            m.at[idx[k],'rb_competition_carry_score']=carry_comp; m.at[idx[k],'rb_competition_target_score']=target_comp; m.at[idx[k],'rb_competition_adjustment']=c_adj

        if len(cw)>1 and cw.max()>.72:
            k=int(cw.argmax()); excess=cw[k]-.72; cw[k]=.72; oth=np.arange(len(cw))!=k; cw[oth]+=excess*cw[oth]/cw[oth].sum()
        if len(tw)>1 and tw.max()>.68:
            k=int(tw.argmax()); excess=tw[k]-.68; tw[k]=.68; oth=np.arange(len(tw))!=k; tw[oth]+=excess*tw[oth]/tw[oth].sum()

        for j,i in enumerate(idx):
            row=m.loc[i]; oc=max(num(row.get('projected_rush_attempts'),0),1e-6); ot=max(num(row.get('projected_targets'),0),1e-6)
            nc=carry_budget*cw[j]; nt=target_budget*tw[j]; cr=nc/oc; tr=nt/ot
            m.at[i,'projected_rush_attempts']=nc
            for c in ['projected_rushing_yards','projected_rushing_tds']: m.at[i,c]=num(row.get(c),0)*cr
            m.at[i,'projected_targets']=nt
            for c in ['projected_receptions','projected_receiving_yards','projected_receiving_tds']: m.at[i,c]=num(row.get(c),0)*tr
            m.at[i,'rb_workload_hierarchy_applied']=True; m.at[i,'rb_workload_carry_share']=cw[j]; m.at[i,'rb_workload_target_share']=tw[j]
            m.at[i,'rb_workload_draft_pick']=picks[j] if picks[j]<999 else np.nan
            m.at[i,'rb_lead_carry_floor']=lead_floor if j in lead and np.isfinite(lead_floor) else np.nan
            m.at[i,'rb_lead_target_floor']=lead_t_floor if j in lead and np.isfinite(lead_t_floor) else np.nan
            if j not in lead:
                m.at[i,'rb_competition_carry_score']=carry_comp; m.at[i,'rb_competition_target_score']=target_comp

    all_elig=m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for i in m.index[all_elig]:
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=score(d,1); m.at[i,'half_ppr_points']=score(d,.5); m.at[i,'standard_points']=score(d,0)
        m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/GAMES; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/GAMES; m.at[i,'standard_per_game']=m.at[i,'standard_points']/GAMES
    for f in ['ppr_points','half_ppr_points','standard_points']:
        m[f.replace('_points','_overall_rank')]=m[f].rank(method='min',ascending=False); pc=f.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[f].notna(); m.loc[mask,pc]=m.loc[mask,f].rank(method='min',ascending=False)
    drop=[c for c in m.columns if c.endswith('_role') or c in {'depth_rank','depth_starter','role_carry_share_2026','role_target_share_2026','carries_per_game','targets_per_game','rookie_role','role_confidence','draft_pick_direct'}]
    m=m.drop(columns=drop,errors='ignore'); nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(STATS,index=False)
    watch=['Jeremiyah Love','Omarion Hampton','Jaylen Warren','Tony Pollard','Alvin Kamara']
    cols=['name','team','projected_rush_attempts','projected_targets','ppr_points','ppr_pos_rank','rb_workload_carry_share','rb_workload_target_share','rb_competition_carry_score','rb_competition_target_score','rb_lead_carry_floor','rb_lead_target_floor']
    print(m[m.name.isin(watch)][cols].to_dict('records'))
if __name__=='__main__': main()
