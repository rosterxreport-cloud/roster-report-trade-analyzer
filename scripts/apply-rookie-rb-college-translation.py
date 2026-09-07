#!/usr/bin/env python3
"""Blend player-specific college RB production into 2026 rookie NFL efficiency priors.

This layer changes efficiency, not workload. Current NFL depth/coaching/workload layers
still determine carries and targets. College production is translated conservatively
and regressed toward recent NFL rookie RB outcomes so college rates are never copied
straight into NFL projections.
"""
from __future__ import annotations
import argparse,re,unicodedata
from pathlib import Path
import numpy as np
import pandas as pd

GAMES=17.0
NFL_PRIOR={"ypc":4.20,"catch":.73,"ypt":5.80,"rush_td_rate":.025,"rec_td_rate":.022}


def norm_name(v):
    t=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().lower()
    t=re.sub(r"\b(jr|sr|ii|iii|iv)\.?\b","",t)
    return re.sub(r"[^a-z0-9]","",t)

def num(v,default=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else default
    except (TypeError,ValueError): return default

def points(r,rec=1.0):
    x=lambda k:num(r.get(k),0.0)
    return .04*x("projected_passing_yards")+4*x("projected_passing_tds")-2*x("projected_interceptions")+.1*x("projected_rushing_yards")+6*x("projected_rushing_tds")+rec*x("projected_receptions")+.1*x("projected_receiving_yards")+6*x("projected_receiving_tds")

def clip(v,lo,hi): return float(np.clip(v,lo,hi))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--stats',type=Path,default=Path('data/projections/stat_projections_2026.csv'))
    ap.add_argument('--college',type=Path,default=Path('data/rookie_rb_college_2026.csv'))
    ap.add_argument('--out',type=Path,default=Path('data/projections/stat_projections_2026.csv'))
    a=ap.parse_args()
    stats=pd.read_csv(a.stats)
    if not a.college.exists():
        print('No rookie RB college file; skipping'); return
    c=pd.read_csv(a.college)
    if c.empty:
        print('Empty rookie RB college file; skipping'); return
    c['name_key']=c['name'].map(norm_name)
    stats['name_key']=stats['name'].map(norm_name)
    stats['rookie_rb_college_applied']=False
    stats['rookie_rb_college_weight']=np.nan
    stats['rookie_rb_college_ypc']=np.nan
    stats['rookie_rb_college_yac_per_att']=np.nan
    stats['rookie_rb_college_mtf_per_att']=np.nan
    stats['rookie_rb_college_explosive_rate']=np.nan
    stats['rookie_rb_translated_ypc']=np.nan
    stats['rookie_rb_translated_catch_rate']=np.nan
    stats['rookie_rb_translated_ypt']=np.nan
    stats['rookie_rb_translated_rush_td_rate']=np.nan
    stats['rookie_rb_translated_rec_td_rate']=np.nan
    applied=0
    for idx,r in stats[(stats.position.eq('RB')) & stats.projection_status.eq('rookie_model')].iterrows():
        g=c[c.name_key.eq(r['name_key'])]
        if g.empty: continue
        d=g.iloc[-1]
        att=max(num(d.get('rush_attempts'),0),1); ry=num(d.get('rush_yards'),0); rtd=num(d.get('rush_tds'),0)
        rec=max(num(d.get('receptions'),0),0); tgt=max(num(d.get('targets'),rec),1); reyd=num(d.get('receiving_yards'),0); retd=num(d.get('receiving_tds'),0)
        ypc=ry/att; catch=rec/tgt; ypt=reyd/tgt; rush_td=rtd/att; rec_td=retd/tgt
        mtf=num(d.get('missed_tackles_forced'),np.nan); yac=num(d.get('yards_after_contact_per_attempt'),np.nan); expl=num(d.get('explosive_runs_10plus'),np.nan)
        mtf_rate=mtf/att if np.isfinite(mtf) else np.nan; expl_rate=expl/att if np.isfinite(expl) else np.nan
        pick=num(d.get('draft_pick'),257); age=num(d.get('age'),22)
        # College quality score: production + contact/explosive skill + receiving + draft/age.
        score=0.0
        score += clip((ypc-5.0)/2.0,-1,1)*.27
        if np.isfinite(yac): score += clip((yac-3.0)/2.0,-1,1)*.18
        if np.isfinite(mtf_rate): score += clip((mtf_rate-.18)/.15,-1,1)*.15
        if np.isfinite(expl_rate): score += clip((expl_rate-.12)/.12,-1,1)*.12
        score += clip((ypt-5.5)/4.0,-1,1)*.10
        score += clip((catch-.70)/.20,-1,1)*.05
        score += clip((80-pick)/80,-1,1)*.09
        score += clip((22-age)/2,-1,1)*.04
        # Translation is deliberately narrow; college signal cannot manufacture NFL-level extremes.
        translated_ypc=clip(NFL_PRIOR['ypc'] + .55*score,3.75,4.85)
        translated_catch=clip(NFL_PRIOR['catch'] + .055*score,.64,.82)
        translated_ypt=clip(NFL_PRIOR['ypt'] + .85*score,4.8,7.0)
        translated_rtd=clip(NFL_PRIOR['rush_td_rate'] + .010*clip((rush_td-.05)/.05,-1,1)+.005*score,.015,.045)
        translated_rectd=clip(NFL_PRIOR['rec_td_rate'] + .008*clip((rec_td-.04)/.05,-1,1)+.003*score,.012,.040)
        # Strongest for first-year no-NFL-history players, but still blended with existing rookie calibration.
        weight=clip(.48 + .12*(pick<=32) + .05*(pick<=10),.45,.65)
        carries=num(r.get('projected_rush_attempts'),0); targets=num(r.get('projected_targets'),0)
        old_ypc=num(r.get('projected_rushing_yards'),0)/carries if carries>0 else NFL_PRIOR['ypc']
        old_catch=num(r.get('projected_receptions'),0)/targets if targets>0 else NFL_PRIOR['catch']
        old_ypt=num(r.get('projected_receiving_yards'),0)/targets if targets>0 else NFL_PRIOR['ypt']
        old_rtd=num(r.get('projected_rushing_tds'),0)/carries if carries>0 else NFL_PRIOR['rush_td_rate']
        old_rectd=num(r.get('projected_receiving_tds'),0)/targets if targets>0 else NFL_PRIOR['rec_td_rate']
        new_ypc=(1-weight)*old_ypc+weight*translated_ypc
        new_catch=(1-weight)*old_catch+weight*translated_catch
        new_ypt=(1-weight)*old_ypt+weight*translated_ypt
        new_rtd=(1-weight)*old_rtd+weight*translated_rtd
        new_rectd=(1-weight)*old_rectd+weight*translated_rectd
        stats.at[idx,'projected_rushing_yards']=carries*new_ypc
        stats.at[idx,'projected_rushing_tds']=carries*new_rtd
        stats.at[idx,'projected_receptions']=targets*new_catch
        stats.at[idx,'projected_receiving_yards']=targets*new_ypt
        stats.at[idx,'projected_receiving_tds']=targets*new_rectd
        stats.at[idx,'rookie_rb_college_applied']=True
        stats.at[idx,'rookie_rb_college_weight']=weight
        stats.at[idx,'rookie_rb_college_ypc']=ypc
        stats.at[idx,'rookie_rb_college_yac_per_att']=yac
        stats.at[idx,'rookie_rb_college_mtf_per_att']=mtf_rate
        stats.at[idx,'rookie_rb_college_explosive_rate']=expl_rate
        stats.at[idx,'rookie_rb_translated_ypc']=translated_ypc
        stats.at[idx,'rookie_rb_translated_catch_rate']=translated_catch
        stats.at[idx,'rookie_rb_translated_ypt']=translated_ypt
        stats.at[idx,'rookie_rb_translated_rush_td_rate']=translated_rtd
        stats.at[idx,'rookie_rb_translated_rec_td_rate']=translated_rectd
        applied+=1
    eligible=stats.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for idx in stats[eligible].index:
        d=stats.loc[idx].to_dict(); stats.at[idx,'ppr_points']=points(d,1); stats.at[idx,'half_ppr_points']=points(d,.5); stats.at[idx,'standard_points']=points(d,0)
        stats.at[idx,'ppr_per_game']=stats.at[idx,'ppr_points']/GAMES; stats.at[idx,'half_ppr_per_game']=stats.at[idx,'half_ppr_points']/GAMES; stats.at[idx,'standard_per_game']=stats.at[idx,'standard_points']/GAMES
    for f in ['ppr_points','half_ppr_points','standard_points']:
        stats[f.replace('_points','_overall_rank')]=stats[f].rank(method='min',ascending=False); pc=f.replace('_points','_pos_rank'); stats[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=stats.position.eq(p)&stats[f].notna(); stats.loc[mask,pc]=stats.loc[mask,f].rank(method='min',ascending=False)
    stats=stats.drop(columns=['name_key'],errors='ignore'); nums=stats.select_dtypes(include=[np.number]).columns; stats[nums]=stats[nums].round(3); stats.to_csv(a.out,index=False)
    watch=stats[stats.rookie_rb_college_applied][['name','team','projected_rush_attempts','projected_rushing_yards','projected_rushing_tds','projected_targets','projected_receptions','projected_receiving_yards','ppr_points','ppr_pos_rank','rookie_rb_college_weight','rookie_rb_translated_ypc']]
    print(watch.to_dict('records')); print(f'Rookie RB college translations applied: {applied}'); print(f'Wrote {a.out}')
if __name__=='__main__': main()
