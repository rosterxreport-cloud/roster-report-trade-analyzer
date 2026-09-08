#!/usr/bin/env python3
"""Reconcile TE volume to a team TE target budget, then allocate within the room.

The TE profile layer supplies player-level earning evidence (target share, prior
production, air-yard/YAC profile and coaching). This layer prevents those signals
from multiplicatively inflating already-high target baselines: it estimates a
bounded team TE target budget and allocates that budget across the team's TEs.
No player-specific overrides.
"""
from pathlib import Path
import numpy as np, pandas as pd
P=Path('data/projections/stat_projections_2026.csv'); R=Path('data/projections/player_role_context_2026.csv'); G=17.
def n(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except:return d
def pts(r,rec=1.):
    z=lambda k:n(r.get(k),0.); return .1*z('projected_rushing_yards')+6*z('projected_rushing_tds')+rec*z('projected_receptions')+.1*z('projected_receiving_yards')+6*z('projected_receiving_tds')+.04*z('projected_passing_yards')+4*z('projected_passing_tds')-2*z('projected_interceptions')
def main():
    m=pd.read_csv(P); r=pd.read_csv(R)
    elig=m.position.eq('TE')&m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for c in ['te_budget_reconciled','te_team_target_budget','te_team_target_rate','te_budget_player_share','te_budget_multiplier']:
        m[c]=False if c=='te_budget_reconciled' else np.nan
    for team,idx in m[elig].groupby('team').groups.items():
        idx=list(idx); base=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0).clip(lower=0)
        rt=r[r.team_2026.eq(team)] if 'team_2026' in r else pd.DataFrame()
        pa=np.nan
        if len(rt) and 'projected_pass_attempts' in rt:
            q=pd.to_numeric(rt.projected_pass_attempts,errors='coerce').dropna()
            if len(q): pa=float(q.iloc[0])
        if not np.isfinite(pa):
            # Infer a conservative pass budget from current skill-player targets.
            allidx=m.index[m.team.eq(team)&m.position.isin(['RB','WR','TE'])&m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])]
            pa=float(pd.to_numeric(m.loc[allidx,'projected_targets'],errors='coerce').fillna(0).sum()/0.961) if len(allidx) else 550.
        coach=np.clip(n(m.loc[idx,'coaching_position_share_multiplier'].dropna().median() if 'coaching_position_share_multiplier' in m else 1.,1.),.93,1.07)
        # Baseline TE room share comes from the pre-budget projection but is shrunk toward
        # a broad NFL TE target-rate anchor. This preserves team/personnel context while
        # preventing one player's profile multiplier from creating new team opportunity.
        base_rate=float(base.sum()/max(pa*.961,1.)); anchor=.205
        rate=np.clip(.58*base_rate+.42*anchor, .145, .285)
        rate=np.clip(rate*(.65+.35*coach),.145,.285)
        budget=pa*.961*rate
        earn=pd.to_numeric(m.loc[idx,'te_target_earning_score'],errors='coerce').fillna(.5).clip(0,1)
        prior=base/base.sum() if base.sum()>0 else pd.Series(1/len(idx),index=idx)
        merit=(.72*prior+.28*(np.exp((earn-.5)*1.6)/np.exp((earn-.5)*1.6).sum()))
        share=merit/merit.sum(); proposed=budget*share
        # Preserve a modest floor/ceiling around the evidence-driven pre-budget role.
        lo=base*.78; hi=base*1.08
        proposed=np.minimum(np.maximum(proposed,lo),hi)
        # If clipping changed the room total, redistribute remaining budget only where capacity exists.
        for _ in range(5):
            diff=budget-proposed.sum()
            if abs(diff)<.05: break
            cap=(hi-proposed).clip(lower=0) if diff>0 else (proposed-lo).clip(lower=0)
            if cap.sum()<=0: break
            proposed += np.sign(diff)*np.minimum(cap,abs(diff)*cap/cap.sum())
        for i in idx:
            old=max(n(m.at[i,'projected_targets'],0),1e-9); new=max(float(proposed.loc[i]),0); mult=new/old
            m.at[i,'projected_targets']=new
            m.at[i,'projected_receptions']=n(m.at[i,'projected_receptions'],0)*mult
            # Preserve TE profile efficiency; yardage follows volume only here.
            m.at[i,'projected_receiving_yards']=n(m.at[i,'projected_receiving_yards'],0)*mult
            m.at[i,'projected_receiving_tds']=n(m.at[i,'projected_receiving_tds'],0)*(.70+.30*mult)
            m.at[i,'te_budget_reconciled']=True; m.at[i,'te_team_target_budget']=budget; m.at[i,'te_team_target_rate']=rate; m.at[i,'te_budget_player_share']=share.loc[i]; m.at[i,'te_budget_multiplier']=mult
            d=m.loc[i].to_dict(); m.at[i,'ppr_points']=pts(d,1); m.at[i,'half_ppr_points']=pts(d,.5); m.at[i,'standard_points']=pts(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/G; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/G; m.at[i,'standard_per_game']=m.at[i,'standard_points']/G
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        m[fc.replace('_points','_overall_rank')]=m[fc].rank(method='min',ascending=False); pc=fc.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(P,index=False)
    print(m[elig].sort_values('ppr_points',ascending=False).head(30)[['name','team','projected_targets','projected_receptions','projected_receiving_yards','projected_receiving_tds','ppr_points','ppr_pos_rank','te_team_target_budget','te_team_target_rate','te_budget_player_share','te_budget_multiplier']].to_dict('records'))
if __name__=='__main__':main()
