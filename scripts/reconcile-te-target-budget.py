#!/usr/bin/env python3
"""Reconcile TE volume to a team target budget with individual earning evidence."""
from pathlib import Path
import re, unicodedata
import numpy as np, pandas as pd
P=Path('data/projections/stat_projections_2026.csv'); R=Path('data/projections/player_role_context_2026.csv'); F=Path('data/projections/player_features_2023_2025.csv'); G=17.; W={2023:.15,2024:.30,2025:.55}
def n(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except:return d
def norm(v):
    t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower(); t=re.sub(r'\b(jr|sr|ii|iii|iv)\.?\b','',t); return re.sub(r'[^a-z0-9]','',t)
def pts(r,rec=1.):
    z=lambda k:n(r.get(k),0.); return .1*z('projected_rushing_yards')+6*z('projected_rushing_tds')+rec*z('projected_receptions')+.1*z('projected_receiving_yards')+6*z('projected_receiving_tds')+.04*z('projected_passing_yards')+4*z('projected_passing_tds')-2*z('projected_interceptions')
def main():
    m=pd.read_csv(P); r=pd.read_csv(R); f=pd.read_csv(F,low_memory=False)
    f=f[(f.position.eq('TE'))&f.season.isin(W)].copy(); nc='player_display_name' if 'player_display_name' in f else 'player_name'; f['nk']=f[nc].map(norm)
    hist={}
    for nk,g in f.groupby('nk'):
        games=pd.to_numeric(g.games,errors='coerce').fillna(0); wt=g.season.map(W).fillna(0)*np.sqrt(games.clip(lower=1)/12).clip(upper=1)
        def av(c):
            if c not in g:return np.nan
            x=pd.to_numeric(g[c],errors='coerce'); good=x.notna()&wt.gt(0); return float(np.average(x[good],weights=wt[good])) if good.any() else np.nan
        ts=av('target_share'); tprr=av('targets_per_route_run')
        if not np.isfinite(tprr) and 'routes_run' in g and 'targets' in g:
            rr=pd.to_numeric(g.routes_run,errors='coerce'); tg=pd.to_numeric(g.targets,errors='coerce'); good=rr.gt(0)&tg.notna()&wt.gt(0)
            if good.any(): tprr=float(np.average((tg[good]/rr[good]),weights=wt[good]))
        hist[nk]=(ts,tprr)
    elig=m.position.eq('TE')&m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for c in ['te_budget_reconciled','te_team_target_budget','te_team_target_rate','te_budget_player_share','te_budget_multiplier','te_budget_earning_strength']:
        m[c]=False if c=='te_budget_reconciled' else np.nan
    for team,idx in m[elig].groupby('team').groups.items():
        idx=list(idx); base=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0).clip(lower=0)
        rt=r[r.team_2026.eq(team)] if 'team_2026' in r else pd.DataFrame(); pa=np.nan
        if len(rt) and 'projected_pass_attempts' in rt:
            q=pd.to_numeric(rt.projected_pass_attempts,errors='coerce').dropna(); pa=float(q.iloc[0]) if len(q) else np.nan
        if not np.isfinite(pa):
            allidx=m.index[m.team.eq(team)&m.position.isin(['RB','WR','TE'])&m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])]
            pa=float(pd.to_numeric(m.loc[allidx,'projected_targets'],errors='coerce').fillna(0).sum()/0.961) if len(allidx) else 550.
        coach=np.clip(n(m.loc[idx,'coaching_position_share_multiplier'].dropna().median() if 'coaching_position_share_multiplier' in m else 1.,1.),.93,1.07)
        base_rate=float(base.sum()/max(pa*.961,1.)); rate=np.clip((.58*base_rate+.42*.205)*(.65+.35*coach),.145,.285); budget=pa*.961*rate
        profile=pd.to_numeric(m.loc[idx,'te_target_earning_score'],errors='coerce').fillna(.5).clip(0,1)
        strength=pd.Series(index=idx,dtype=float)
        for i in idx:
            ts,tprr=hist.get(norm(m.at[i,'name']),(np.nan,np.nan)); ts_s=np.clip((ts-.14)/.12,0,1) if np.isfinite(ts) else .35; rr_s=np.clip((tprr-.15)/.12,0,1) if np.isfinite(tprr) else .35
            strength.loc[i]=.58*ts_s+.42*rr_s
        prior=base/base.sum() if base.sum()>0 else pd.Series(1/len(idx),index=idx)
        evidence=.55*profile+.45*strength
        merit=.52*prior+.48*(np.exp((evidence-.5)*2.2)/np.exp((evidence-.5)*2.2).sum()); share=merit/merit.sum(); proposed=budget*share
        # Evidence-sensitive bounds: generic TEs remain constrained, elite persistent earners can resist compression.
        lo=base*(.78+.18*strength); hi=base*(1.08+.12*strength)
        proposed=np.minimum(np.maximum(proposed,lo),hi)
        for _ in range(6):
            diff=budget-proposed.sum()
            if abs(diff)<.05: break
            cap=(hi-proposed).clip(lower=0) if diff>0 else (proposed-lo).clip(lower=0)
            if cap.sum()<=0: break
            proposed += np.sign(diff)*np.minimum(cap,abs(diff)*cap/cap.sum())
        for i in idx:
            old=max(n(m.at[i,'projected_targets'],0),1e-9); new=max(float(proposed.loc[i]),0); mult=new/old
            m.at[i,'projected_targets']=new; m.at[i,'projected_receptions']=n(m.at[i,'projected_receptions'],0)*mult; m.at[i,'projected_receiving_yards']=n(m.at[i,'projected_receiving_yards'],0)*mult; m.at[i,'projected_receiving_tds']=n(m.at[i,'projected_receiving_tds'],0)*(.70+.30*mult)
            m.at[i,'te_budget_reconciled']=True; m.at[i,'te_team_target_budget']=budget; m.at[i,'te_team_target_rate']=rate; m.at[i,'te_budget_player_share']=share.loc[i]; m.at[i,'te_budget_multiplier']=mult; m.at[i,'te_budget_earning_strength']=strength.loc[i]
            d=m.loc[i].to_dict(); m.at[i,'ppr_points']=pts(d,1); m.at[i,'half_ppr_points']=pts(d,.5); m.at[i,'standard_points']=pts(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/G; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/G; m.at[i,'standard_per_game']=m.at[i,'standard_points']/G
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        m[fc.replace('_points','_overall_rank')]=m[fc].rank(method='min',ascending=False); pc=fc.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(P,index=False)
if __name__=='__main__':main()
