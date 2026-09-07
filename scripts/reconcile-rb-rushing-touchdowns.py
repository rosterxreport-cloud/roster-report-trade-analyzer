#!/usr/bin/env python3
"""Reconcile RB rushing TDs with high-value role, team scoring environment, QB competition and sustainable player scoring."""
from pathlib import Path
import re, unicodedata
import numpy as np
import pandas as pd
STATS=Path('data/projections/stat_projections_2026.csv'); ROLES=Path('data/projections/player_role_context_2026.csv'); FEATURES=Path('data/projections/player_features_2023_2025.csv'); TEAM=Path('data/projections/team_context_2026.csv'); GAMES=17.
def num(v,d=0.):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except (TypeError,ValueError): return d
def norm(v):
    t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower(); t=re.sub(r'\b(jr|sr|ii|iii|iv)\.?\b','',t); return re.sub(r'[^a-z0-9]','',t)
def points(r,rec=1.):
    x=lambda k:num(r.get(k),0); return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')
def main():
    s=pd.read_csv(STATS); roles=pd.read_csv(ROLES); f=pd.read_csv(FEATURES) if FEATURES.exists() else pd.DataFrame(); tc=pd.read_csv(TEAM) if TEAM.exists() else pd.DataFrame()
    keep=[c for c in ['name','position','team_2026','depth_rank','depth_starter','rookie','draft_pick','role_confidence'] if c in roles]; rr=roles[keep].rename(columns={'team_2026':'team'}); m=s.merge(rr,on=['name','position','team'],how='left',suffixes=('','_role')); elig=m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])&m.position.eq('RB')
    sustain={}
    if len(f):
        ff=f[f.position.eq('RB')].copy(); ff['nk']=ff.player_display_name.fillna(ff.get('player_name','')).map(norm)
        for nk,g in ff.groupby('nk'):
            g=g[g.season.isin([2024,2025])].copy(); rates=pd.to_numeric(g.get('rush_td_per_attempt'),errors='coerce'); att=pd.to_numeric(g.get('carries'),errors='coerce').fillna(0); ok=rates.notna()&(att>=80)
            if ok.any():
                vals=rates[ok].to_numpy(); w=np.sqrt(att[ok].to_numpy()).clip(1,None); avg=float(np.average(vals,weights=w)); seasons=len(vals); consistency=float(np.min(vals)) if seasons>=2 else .035
                sustain[nk]=float(np.clip(.65*(avg/.035)+.35*(consistency/.035),.65,1.75))
    teamctx={row.team:row for _,row in tc.iterrows()} if len(tc) and 'team' in tc.columns else {}
    # League scoring baseline for a bounded team-environment index.
    team_total_tds=[]
    for _,r in tc.iterrows() if len(tc) else []:
        team_total_tds.append(num(r.get('projected_pass_attempts'))*num(r.get('projected_pass_td_rate')) + num(r.get('projected_rush_attempts'))*num(r.get('projected_rush_td_rate')))
    lg_total_td=float(np.nanmedian(team_total_tds)) if team_total_tds else 40.
    for c in ['rb_rush_td_reconciled','rb_rush_td_share','rb_rush_td_team_budget','rb_goal_line_score','rb_goal_line_proxy_used','rb_rush_td_sanity_adjusted','rb_td_sustainability_score','rb_team_scoring_index','rb_team_rush_td_expectation','rb_qb_rush_td_competition','rb_team_td_budget_blend']:
        m[c]=False if c in ['rb_rush_td_reconciled','rb_goal_line_proxy_used','rb_rush_td_sanity_adjusted'] else np.nan
    for team,g in m[elig].groupby('team'):
        idx=list(g.index); old_td=pd.to_numeric(m.loc[idx,'projected_rushing_tds'],errors='coerce').fillna(0.); carries=pd.to_numeric(m.loc[idx,'projected_rush_attempts'],errors='coerce').fillna(0.)
        if carries.sum()<=0: continue
        old_budget=float(old_td.sum()); ctx=teamctx.get(team); team_rush_td=np.nan; scoring_idx=1.; qb_comp=0.
        if ctx is not None:
            pra=max(num(ctx.get('projected_rush_attempts'),0),1.); team_rush_td=pra*num(ctx.get('projected_rush_td_rate'),0); team_pass_td=num(ctx.get('projected_pass_attempts'),0)*num(ctx.get('projected_pass_td_rate'),0); scoring_idx=float(np.clip((team_rush_td+team_pass_td)/max(lg_total_td,1.),.82,1.20))
            q=m[(m.team.eq(team))&(m.position.eq('QB'))&m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])]; qb_comp=float(pd.to_numeric(q.get('projected_rushing_tds'),errors='coerce').fillna(0).max()) if len(q) else 0.
            rb_carry_share=float(np.clip(carries.sum()/pra,.45,.92)); environment_budget=max(1.2,(team_rush_td-.70*qb_comp)*np.clip(.88+.16*rb_carry_share,.82,1.03)); environment_budget*=np.clip(.92+.08*scoring_idx,.88,1.08)
            budget=.52*old_budget+.48*environment_budget
        else: budget=old_budget
        budget=float(np.clip(budget,max(1.5,carries.sum()*.012),max(3.,carries.sum()*.060)))
        cshare=(carries/carries.sum()).to_numpy(); weights=[]; proxies=[]; glscores=[]; sust=[]
        for j,i in enumerate(idx):
            row=m.loc[i]; rank=max(1,int(num(row.get('depth_rank'),4))); starter=bool(row.get('depth_starter',False)); depth={1:1.,2:.58,3:.28,4:.12}.get(rank,.08)*(1.10 if starter else 1.); att=max(num(row.get('projected_rush_attempts'),0),1.); old_rate=num(row.get('projected_rushing_tds'),0)/att; reg_rate=np.clip(old_rate/.035,.65,1.35); ss=sustain.get(norm(row['name']),1.)
            gl=num(row.get('goal_line_carries'),np.nan); iz5=num(row.get('inside_5_carries'),np.nan); rz=num(row.get('red_zone_carries'),np.nan); iz10=num(row.get('inside_10_carries'),np.nan); explicit=[x for x in [gl,iz5,rz,iz10] if np.isfinite(x) and x>=0]
            if explicit: glscore=max(.01,1.*(iz5 if np.isfinite(iz5) else 0)+.75*(gl if np.isfinite(gl) else 0)+.45*(iz10 if np.isfinite(iz10) else 0)+.20*(rz if np.isfinite(rz) else 0)); proxy=False
            else: glscore=max(.01,.72*cshare[j]+.28*(depth/1.10)); proxy=True
            rookie=bool(row.get('rookie',False)); pick=num(row.get('draft_pick'),999); capital=1.08 if rookie and pick<=32 else (1.04 if rookie and pick<=64 else 1.)
            hist_w=.14 if ss>=1.15 else .06; core=(.53*glscore+.30*cshare[j]+.17*(depth/1.10)); hist_signal=.50*reg_rate+.50*ss; w=((1-hist_w)*core+hist_w*hist_signal)*capital
            weights.append(max(.001,w)); proxies.append(proxy); glscores.append(glscore); sust.append(ss)
        w=np.asarray(weights,float); w/=w.sum()
        if len(w)>1 and w.max()>.74:
            k=int(w.argmax()); excess=w[k]-.74; w[k]=.74; oth=np.arange(len(w))!=k; w[oth]+=excess*w[oth]/w[oth].sum()
        tds=budget*w; caps=[]
        for j,i in enumerate(idx):
            att=max(carries.iloc[j],1.); elite_env=scoring_idx>=1.08; cap_rate=.070 if sust[j]>=1.15 and cshare[j]>=.55 and elite_env else (.066 if sust[j]>=1.15 and cshare[j]>=.55 else (.060 if cshare[j]>=.55 else (.050 if cshare[j]>=.35 else .042))); caps.append(max(1.5,att*cap_rate))
        caps=np.asarray(caps); excess=float(np.maximum(tds-caps,0).sum()); clipped=tds>caps; tds=np.minimum(tds,caps)
        for _ in range(4):
            room=np.maximum(caps-tds,0); mask=room>1e-9
            if excess<=1e-9 or not mask.any(): break
            rw=w*mask; rw=rw/rw.sum(); add=np.minimum(room,excess*rw); tds+=add; excess-=add.sum()
        for j,i in enumerate(idx):
            m.at[i,'projected_rushing_tds']=tds[j]; m.at[i,'rb_rush_td_reconciled']=True; m.at[i,'rb_rush_td_share']=tds[j]/max(budget,1e-9); m.at[i,'rb_rush_td_team_budget']=budget; m.at[i,'rb_goal_line_score']=glscores[j]; m.at[i,'rb_goal_line_proxy_used']=proxies[j]; m.at[i,'rb_rush_td_sanity_adjusted']=bool(clipped[j]); m.at[i,'rb_td_sustainability_score']=sust[j]; m.at[i,'rb_team_scoring_index']=scoring_idx; m.at[i,'rb_team_rush_td_expectation']=team_rush_td; m.at[i,'rb_qb_rush_td_competition']=qb_comp; m.at[i,'rb_team_td_budget_blend']=budget
    for i in m[m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])].index:
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=points(d,1); m.at[i,'half_ppr_points']=points(d,.5); m.at[i,'standard_points']=points(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/GAMES; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/GAMES; m.at[i,'standard_per_game']=m.at[i,'standard_points']/GAMES
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        m[fc.replace('_points','_overall_rank')]=m[fc].rank(method='min',ascending=False); pc=fc.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    drop=[c for c in m.columns if c.endswith('_role') or c in {'depth_rank','depth_starter','rookie','draft_pick','role_confidence'}]; m=m.drop(columns=drop,errors='ignore'); nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(STATS,index=False)
if __name__=='__main__': main()
