#!/usr/bin/env python3
"""TE v1: blend previous production, target/air-yard earning, YAC and coaching scheme.

Uses 2023-25 nflverse history with recency weighting. Current projection remains the
baseline; this layer applies bounded, position-specific adjustments rather than
copying prior-year totals. Coaching context is already generated upstream and is
used here as supporting evidence. No player-specific overrides.
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
        games=pd.to_numeric(g.games,errors='coerce').fillna(0); wt=g.season.map(W).fillna(0)*np.sqrt(games.clip(lower=1)/12).clip(upper=1); ok=wt.gt(0)&games.gt(0)
        def av(c,per_game=False):
            if c not in g:return np.nan
            x=pd.to_numeric(g[c],errors='coerce'); x=x/games.where(games>0) if per_game else x; good=ok&x.notna(); return float(np.average(x[good],weights=wt[good])) if good.any() else np.nan
        hist[nk]={'tshare':av('target_share'),'ashare':av('air_yards_share'),'yacpr':av('yac_per_reception'),'aypt':av('air_yards_per_target'),'ypg':av('receiving_yards',True),'tpg':av('targets',True),'ppg':av('ppr_per_game')}
    for c in ['te_profile_applied','te_target_earning_score','te_air_yard_score','te_yac_score','te_previous_production_score','te_coaching_score','te_target_multiplier','te_yardage_multiplier']:
        m[c]=False if c=='te_profile_applied' else np.nan
    elig=m.position.eq('TE')&m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    # Position-relative historical anchors. Percentile-like smooth scores reduce sensitivity to outliers.
    hs=pd.DataFrame(hist).T
    meds={c:n(pd.to_numeric(hs[c],errors='coerce').median()) for c in ['tshare','ashare','yacpr','aypt','ypg','tpg','ppg']}
    def score(x,med,scale): return float(np.clip(.5+(n(x,med)-med)/scale,0,1))
    for i in m.index[elig]:
        h=hist.get(norm(m.at[i,'name']))
        # Rookies/no-history stay close to baseline; coaching still contributes lightly.
        coach=np.clip(n(m.at[i,'coaching_position_share_multiplier'],1.),.93,1.07); coach_score=np.clip(.5+(coach-1)/.14,0,1)
        if h:
            ts=score(h['tshare'],meds['tshare'],.22); air=.60*score(h['ashare'],meds['ashare'],.20)+.40*score(h['aypt'],meds['aypt'],8.0); yac=score(h['yacpr'],meds['yacpr'],7.0); prod=.55*score(h['ypg'],meds['ypg'],70.)+.25*score(h['tpg'],meds['tpg'],8.)+.20*score(h['ppg'],meds['ppg'],18.)
            earning=.46*ts+.19*air+.13*yac+.17*prod+.05*coach_score
            tm=np.clip(1+(earning-.5)*.30,.88,1.12)
            # Yardage combines target volume with downfield/YAC profile; keep efficiency bounded.
            eff=.55*air+.45*yac; ym=np.clip(tm*(1+(eff-.5)*.16),.84,1.16)
        else:
            ts=air=yac=prod=.5; earning=.5+.05*(coach_score-.5); tm=np.clip(1+(coach_score-.5)*.04,.98,1.02); ym=tm
        oldt=max(n(m.at[i,'projected_targets'],0),1e-9); newt=oldt*tm; tr=newt/oldt
        m.at[i,'projected_targets']=newt
        # Catch volume follows targets; yardage gets separate air/YAC efficiency treatment. TDs only lightly correlate.
        m.at[i,'projected_receptions']=n(m.at[i,'projected_receptions'],0)*tr
        oldy=n(m.at[i,'projected_receiving_yards'],0); m.at[i,'projected_receiving_yards']=oldy*ym
        m.at[i,'projected_receiving_tds']=n(m.at[i,'projected_receiving_tds'],0)*(.65+.35*tr)
        m.at[i,'te_profile_applied']=True; m.at[i,'te_target_earning_score']=earning; m.at[i,'te_air_yard_score']=air; m.at[i,'te_yac_score']=yac; m.at[i,'te_previous_production_score']=prod; m.at[i,'te_coaching_score']=coach_score; m.at[i,'te_target_multiplier']=tm; m.at[i,'te_yardage_multiplier']=ym
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=pts(d,1); m.at[i,'half_ppr_points']=pts(d,.5); m.at[i,'standard_points']=pts(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/G; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/G; m.at[i,'standard_per_game']=m.at[i,'standard_points']/G
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        m[fc.replace('_points','_overall_rank')]=m[fc].rank(method='min',ascending=False); pc=fc.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(P,index=False)
    print(m[elig].sort_values('ppr_points',ascending=False).head(30)[['name','team','projected_targets','projected_receptions','projected_receiving_yards','projected_receiving_tds','ppr_points','ppr_pos_rank','te_target_earning_score','te_target_multiplier','te_yardage_multiplier']].to_dict('records'))
if __name__=='__main__':main()
