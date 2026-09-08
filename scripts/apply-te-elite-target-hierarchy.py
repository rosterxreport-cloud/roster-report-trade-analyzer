#!/usr/bin/env python3
"""Calibrated TE target hierarchy.

Uses 2023-25 target share plus recent full-season workload to keep elite earning
rates available-neutral while preventing ordinary 20-21% shares from turning into
140-150 target projections. No player-specific overrides.
"""
from pathlib import Path
import re, unicodedata
import numpy as np, pandas as pd
P=Path('data/projections/stat_projections_2026.csv'); F=Path('data/projections/player_features_2023_2025.csv'); G=17.; W={2023:.15,2024:.30,2025:.55}
def n(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except:return d
def norm(v):
    t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower(); t=re.sub(r'\b(jr|sr|ii|iii|iv)\.?\b','',t); return re.sub(r'[^a-z0-9]','',t)
def pts(r,rec=1.):
    z=lambda k:n(r.get(k),0.); return .1*z('projected_rushing_yards')+6*z('projected_rushing_tds')+rec*z('projected_receptions')+.1*z('projected_receiving_yards')+6*z('projected_receiving_tds')+.04*z('projected_passing_yards')+4*z('projected_passing_tds')-2*z('projected_interceptions')
def main():
    m=pd.read_csv(P); f=pd.read_csv(F,low_memory=False); f=f[(f.position.eq('TE'))&f.season.isin(W)].copy(); nc='player_display_name' if 'player_display_name' in f else 'player_name'; f['nk']=f[nc].map(norm)
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
        y25=g[g.season.eq(2025)]; y24=g[g.season.eq(2024)]
        t25=n(pd.to_numeric(y25.targets,errors='coerce').sum(),np.nan) if len(y25) else np.nan; g25=n(pd.to_numeric(y25.games,errors='coerce').max(),np.nan) if len(y25) else np.nan
        s25=n(pd.to_numeric(y25.target_share,errors='coerce').mean(),np.nan) if len(y25) else np.nan; s24=n(pd.to_numeric(y24.target_share,errors='coerce').mean(),np.nan) if len(y24) else np.nan
        hist[nk]={'target_share':ts,'tprr':tprr,'targets25':t25,'games25':g25,'share25':s25,'share24':s24}
    audit=['te_elite_hierarchy_applied','te_hist_target_share','te_hist_tprr','te_route_target_estimate','te_hierarchy_strength','te_hierarchy_multiplier','te_recent_target_cap','te_target_share_trend','te_full_season_guardrail']
    for c in audit:m[c]=False if c in ['te_elite_hierarchy_applied','te_full_season_guardrail'] else np.nan
    elig=m.position.eq('TE')&m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for i in m.index[elig]:
        h=hist.get(norm(m.at[i,'name']));
        if not h:continue
        ts=n(h['target_share']); tprr=n(h['tprr']); old=max(n(m.at[i,'projected_targets'],0),1e-9)
        # Continuous calibration: 20% is strong, but true elite protection does not saturate until ~25%+.
        ts_score=np.clip((ts-.12)/.16,0,1) if np.isfinite(ts) else .35
        rr_score=np.clip((tprr-.14)/.16,0,1) if np.isfinite(tprr) else .35
        strength=.68*ts_score+.32*rr_score
        base_rate=np.clip(tprr if np.isfinite(tprr) else .19,.16,.28); inferred_routes=old/.20; route_est=inferred_routes*base_rate
        blend=.12+.28*strength; proposed=(1-blend)*old+blend*route_est
        floor_mult=.86+.14*strength; new=float(np.clip(proposed,old*floor_mult,old*1.14))
        # Full-season persistence guardrail. Healthy 2025 TEs need exceptional rate evidence to jump >8-16%; injury-shortened seasons are exempt.
        cap=np.nan; trend=np.nan; guarded=False
        if np.isfinite(h['share25']) and np.isfinite(h['share24']): trend=h['share25']-h['share24']
        if np.isfinite(h['targets25']) and np.isfinite(h['games25']) and h['games25']>=15:
            growth=.08+.08*strength
            if np.isfinite(trend) and trend<-.015:growth-=.04
            if np.isfinite(trend) and trend>.025:growth+=.03
            cap=h['targets25']*(1+np.clip(growth,.04,.18)); guarded=new>cap; new=min(new,cap)
        mult=new/old
        m.at[i,'projected_targets']=new; m.at[i,'projected_receptions']=n(m.at[i,'projected_receptions'],0)*mult; m.at[i,'projected_receiving_yards']=n(m.at[i,'projected_receiving_yards'],0)*mult; m.at[i,'projected_receiving_tds']=n(m.at[i,'projected_receiving_tds'],0)*(.72+.28*mult)
        m.at[i,'te_elite_hierarchy_applied']=True; m.at[i,'te_hist_target_share']=ts; m.at[i,'te_hist_tprr']=tprr; m.at[i,'te_route_target_estimate']=route_est; m.at[i,'te_hierarchy_strength']=strength; m.at[i,'te_hierarchy_multiplier']=mult; m.at[i,'te_recent_target_cap']=cap; m.at[i,'te_target_share_trend']=trend; m.at[i,'te_full_season_guardrail']=guarded
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=pts(d,1); m.at[i,'half_ppr_points']=pts(d,.5); m.at[i,'standard_points']=pts(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/G; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/G; m.at[i,'standard_per_game']=m.at[i,'standard_points']/G
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        m[fc.replace('_points','_overall_rank')]=m[fc].rank(method='min',ascending=False); pc=fc.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(P,index=False)
    print(m[elig].sort_values('ppr_points',ascending=False).head(30)[['name','team','projected_targets','ppr_points','ppr_pos_rank','te_hist_target_share','te_hierarchy_strength','te_recent_target_cap','te_target_share_trend','te_full_season_guardrail']].to_dict('records'))
if __name__=='__main__':main()
