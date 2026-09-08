#!/usr/bin/env python3
"""Availability-neutral TE target hierarchy and route-rate reconciliation.

Uses 2023-25 per-game target share/TPRR evidence to protect elite receiving TEs
from being compressed by generic team TE budgets. Blends a routes x TPRR target
estimate with the existing budget projection. No player-specific overrides.
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
        if not np.isfinite(tprr):
            # Derive TPRR from available target and route columns when necessary.
            vals=[]; ws=[]
            for j,row in g.iterrows():
                routes=n(row.get('routes_run')); targets=n(row.get('targets')); w=n(wt.loc[j],0)
                if np.isfinite(routes) and routes>0 and np.isfinite(targets) and w>0: vals.append(targets/routes); ws.append(w)
            tprr=float(np.average(vals,weights=ws)) if vals else np.nan
        hist[nk]={'target_share':ts,'tprr':tprr}
    for c in ['te_elite_hierarchy_applied','te_hist_target_share','te_hist_tprr','te_route_target_estimate','te_hierarchy_strength','te_hierarchy_multiplier']:
        m[c]=False if c=='te_elite_hierarchy_applied' else np.nan
    elig=m.position.eq('TE')&m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for i in m.index[elig]:
        h=hist.get(norm(m.at[i,'name']));
        if not h: continue
        ts=n(h['target_share']); tprr=n(h['tprr']); old=max(n(m.at[i,'projected_targets'],0),1e-9)
        # Availability-neutral: shares/rates are per opportunity, not season totals.
        ts_score=np.clip((ts-.14)/.12,0,1) if np.isfinite(ts) else .35
        rr_score=np.clip((tprr-.15)/.12,0,1) if np.isfinite(tprr) else .35
        strength=.58*ts_score+.42*rr_score
        # Infer routes from current targets and a conservative TE target rate when direct route projection is unavailable.
        base_rate=np.clip(tprr if np.isfinite(tprr) else .19,.16,.28)
        inferred_routes=old/.20
        route_est=inferred_routes*base_rate
        # Blend budget target projection with route-rate estimate; elite earners receive stronger persistence.
        blend=.18+.32*strength
        proposed=(1-blend)*old+blend*route_est
        # Elite hierarchy protection: strong historical target earners cannot be compressed far below their rate evidence.
        floor_mult=.90+.14*strength
        ceiling_mult=1.18
        new=float(np.clip(proposed,old*floor_mult,old*ceiling_mult))
        mult=new/old
        m.at[i,'projected_targets']=new; m.at[i,'projected_receptions']=n(m.at[i,'projected_receptions'],0)*mult; m.at[i,'projected_receiving_yards']=n(m.at[i,'projected_receiving_yards'],0)*mult; m.at[i,'projected_receiving_tds']=n(m.at[i,'projected_receiving_tds'],0)*(.72+.28*mult)
        m.at[i,'te_elite_hierarchy_applied']=True; m.at[i,'te_hist_target_share']=ts; m.at[i,'te_hist_tprr']=tprr; m.at[i,'te_route_target_estimate']=route_est; m.at[i,'te_hierarchy_strength']=strength; m.at[i,'te_hierarchy_multiplier']=mult
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=pts(d,1); m.at[i,'half_ppr_points']=pts(d,.5); m.at[i,'standard_points']=pts(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/G; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/G; m.at[i,'standard_per_game']=m.at[i,'standard_points']/G
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        m[fc.replace('_points','_overall_rank')]=m[fc].rank(method='min',ascending=False); pc=fc.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(P,index=False)
    print(m[elig].sort_values('ppr_points',ascending=False).head(30)[['name','team','projected_targets','ppr_points','ppr_pos_rank','te_hist_target_share','te_hist_tprr','te_hierarchy_strength','te_hierarchy_multiplier']].to_dict('records'))
if __name__=='__main__':main()
