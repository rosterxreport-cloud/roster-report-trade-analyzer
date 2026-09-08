#!/usr/bin/env python3
"""Reconcile TE volume to team target budgets using calibrated individual earning evidence.

Key principles:
- team pass volume still limits total TE opportunity;
- target share / TPRR are continuous signals rather than saturated buckets;
- recent production is more predictive than old peak seasons;
- large year-over-year target growth requires strong evidence;
- veteran age reduces persistence without hard-coding any player.
"""
from pathlib import Path
import re, unicodedata
import numpy as np, pandas as pd
P=Path('data/projections/stat_projections_2026.csv'); R=Path('data/projections/player_role_context_2026.csv'); F=Path('data/projections/player_features_2023_2025.csv'); G=17.; W={2023:.10,2024:.25,2025:.65}
def n(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except:return d
def norm(v):
    t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower(); t=re.sub(r'\b(jr|sr|ii|iii|iv)\.?\b','',t); return re.sub(r'[^a-z0-9]','',t)
def pts(r,rec=1.):
    z=lambda k:n(r.get(k),0.); return .1*z('projected_rushing_yards')+6*z('projected_rushing_tds')+rec*z('projected_receptions')+.1*z('projected_receiving_yards')+6*z('projected_receiving_tds')+.04*z('projected_passing_yards')+4*z('projected_passing_tds')-2*z('projected_interceptions')
def pct(v,arr,default=.5):
    a=np.asarray([x for x in arr if np.isfinite(x)],dtype=float)
    if not np.isfinite(v) or len(a)<5:return default
    return float(np.clip((a<=v).mean(),0,1))
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
            if good.any(): tprr=float(np.average(tg[good]/rr[good],weights=wt[good]))
        g25=g[g.season.eq(2025)]
        if len(g25):
            q=g25.iloc[-1]; gm=max(n(q.get('games'),0),1); prev_t=n(q.get('targets'),np.nan); prev17=prev_t*17/gm if np.isfinite(prev_t) else np.nan; recent_ts=n(q.get('target_share'),np.nan); age=n(q.get('age'),np.nan)
            if np.isfinite(age): age+=1
        else: prev17=recent_ts=age=np.nan
        hist[nk]={'ts':ts,'tprr':tprr,'recent_ts':recent_ts,'prev17':prev17,'age':age}
    tsvals=[v['ts'] for v in hist.values()]; rrvals=[v['tprr'] for v in hist.values()]
    elig=m.position.eq('TE')&m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    audit=['te_budget_reconciled','te_team_target_budget','te_team_target_rate','te_budget_player_share','te_budget_multiplier','te_budget_earning_strength','te_target_share_prior','te_target_growth_cap','te_age_persistence_multiplier']
    for c in audit:m[c]=False if c=='te_budget_reconciled' else np.nan
    for team,idx in m[elig].groupby('team').groups.items():
        idx=list(idx); base=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0).clip(lower=0)
        rt=r[r.team_2026.eq(team)] if 'team_2026' in r else pd.DataFrame(); pa=np.nan
        if len(rt) and 'projected_pass_attempts' in rt:
            q=pd.to_numeric(rt.projected_pass_attempts,errors='coerce').dropna(); pa=float(q.iloc[0]) if len(q) else np.nan
        if not np.isfinite(pa):
            allidx=m.index[m.team.eq(team)&m.position.isin(['RB','WR','TE'])&m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])]
            pa=float(pd.to_numeric(m.loc[allidx,'projected_targets'],errors='coerce').fillna(0).sum()/0.961) if len(allidx) else 550.
        team_targets=max(pa*.961,1.)
        coach=np.clip(n(m.loc[idx,'coaching_position_share_multiplier'].dropna().median() if 'coaching_position_share_multiplier' in m else 1.,1.),.93,1.07)
        base_rate=float(base.sum()/team_targets); rate=np.clip((.52*base_rate+.48*.205)*(.70+.30*coach),.145,.275); budget=team_targets*rate
        profile=pd.to_numeric(m.loc[idx,'te_target_earning_score'],errors='coerce').fillna(.5).clip(0,1)
        strength=pd.Series(index=idx,dtype=float); share_prior=pd.Series(index=idx,dtype=float); growth_cap=pd.Series(index=idx,dtype=float); age_mult=pd.Series(index=idx,dtype=float)
        for i in idx:
            h=hist.get(norm(m.at[i,'name']),{}); ts=n(h.get('ts')); rr=n(h.get('tprr')); recent=n(h.get('recent_ts')); prev17=n(h.get('prev17')); age=n(h.get('age'))
            ts_p=pct(ts,tsvals); rr_p=pct(rr,rrvals); s=.62*ts_p+.38*rr_p
            # Recent target share anchors the actual pass-game role; multi-year share stabilizes it.
            raw_share=.58*recent+.42*ts if np.isfinite(recent) and np.isfinite(ts) else (ts if np.isfinite(ts) else np.nan)
            if not np.isfinite(raw_share): raw_share=np.clip(base.loc[i]/team_targets,.08,.22)
            # Regression prevents every good season from becoming a 25%+ projection.
            prior_share=.72*raw_share+.28*.155
            # Age-adjusted persistence begins gradually at 31 and steepens for 34+ veterans.
            am=1.0
            if np.isfinite(age):
                if age>=34: am=max(.80,1-.045*(age-33))
                elif age>=31: am=1-.018*(age-30)
            prior_share*=am
            # Growth allowance is continuous: elite earners can grow more, but not automatically by 35-45%.
            evidence=.55*s+.45*n(profile.loc[i],.5)
            allowed=.10+.14*evidence
            cap=prev17*(1+allowed) if np.isfinite(prev17) and prev17>0 else np.inf
            strength.loc[i]=s; share_prior.loc[i]=np.clip(prior_share,.07,.285); growth_cap.loc[i]=cap; age_mult.loc[i]=am
        # Individual target estimate from projected team attempts + calibrated target-share persistence.
        indiv=team_targets*share_prior
        prior=base/base.sum() if base.sum()>0 else pd.Series(1/len(idx),index=idx)
        merit=.45*prior+.55*(indiv/indiv.sum() if indiv.sum()>0 else prior); share=merit/merit.sum(); proposed=budget*share
        # Blend team-budget allocation with individual pass-game target-share estimate.
        proposed=.52*proposed+.48*indiv
        lo=base*(.82+.10*strength); hi=base*(1.04+.10*strength)
        proposed=np.minimum(np.maximum(proposed,lo),hi)
        proposed=np.minimum(proposed,growth_cap)
        # Do not let the sum materially exceed the calibrated team TE budget.
        if proposed.sum()>budget*1.04 and proposed.sum()>0: proposed*=budget*1.04/proposed.sum()
        for i in idx:
            old=max(n(m.at[i,'projected_targets'],0),1e-9); new=max(float(proposed.loc[i]),0); mult=new/old
            m.at[i,'projected_targets']=new; m.at[i,'projected_receptions']=n(m.at[i,'projected_receptions'],0)*mult; m.at[i,'projected_receiving_yards']=n(m.at[i,'projected_receiving_yards'],0)*mult; m.at[i,'projected_receiving_tds']=n(m.at[i,'projected_receiving_tds'],0)*(.72+.28*mult)
            m.at[i,'te_budget_reconciled']=True; m.at[i,'te_team_target_budget']=budget; m.at[i,'te_team_target_rate']=rate; m.at[i,'te_budget_player_share']=share.loc[i]; m.at[i,'te_budget_multiplier']=mult; m.at[i,'te_budget_earning_strength']=strength.loc[i]; m.at[i,'te_target_share_prior']=share_prior.loc[i]; m.at[i,'te_target_growth_cap']=growth_cap.loc[i] if np.isfinite(growth_cap.loc[i]) else np.nan; m.at[i,'te_age_persistence_multiplier']=age_mult.loc[i]
            d=m.loc[i].to_dict(); m.at[i,'ppr_points']=pts(d,1); m.at[i,'half_ppr_points']=pts(d,.5); m.at[i,'standard_points']=pts(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/G; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/G; m.at[i,'standard_per_game']=m.at[i,'standard_points']/G
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        m[fc.replace('_points','_overall_rank')]=m[fc].rank(method='min',ascending=False); pc=fc.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(P,index=False)
    print(m[elig].sort_values('ppr_points',ascending=False).head(30)[['name','team','projected_targets','ppr_points','ppr_pos_rank','te_target_share_prior','te_target_growth_cap','te_age_persistence_multiplier','te_budget_multiplier']].to_dict('records'))
if __name__=='__main__':main()
