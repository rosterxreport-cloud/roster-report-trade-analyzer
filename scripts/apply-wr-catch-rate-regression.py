#!/usr/bin/env python3
"""Regress WR catch rate toward route/archetype expectations after QB adjustment.

Targets and receiving yards are preserved. Receptions are recalculated from a
blend of recent player catch skill, air-yards-per-target archetype expectation,
and the already-computed QB environment. This prevents high historical catch
rates from being treated as perfectly sticky while preserving legitimate slot/
underneath vs downfield differences.
"""
from pathlib import Path
import argparse,re,unicodedata
import numpy as np
import pandas as pd
GAMES=17.0
SEASON_W={2023:.20,2024:.30,2025:.50}

def norm(v):
 t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower();t=re.sub(r'\b(jr|sr|ii|iii|iv)\.?\b','',t);return re.sub(r'[^a-z0-9]','',t)
def num(v,d=np.nan):
 try:
  x=float(v);return x if np.isfinite(x) else d
 except:return d
def points(r,rec):
 x=lambda k:num(r.get(k),0);return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--stats',type=Path,default=Path('data/projections/stat_projections_2026.csv'));ap.add_argument('--features',type=Path,default=Path('data/projections/player_features_2023_2025.csv'));ap.add_argument('--out',type=Path,default=Path('data/projections/stat_projections_2026.csv'));a=ap.parse_args()
 s=pd.read_csv(a.stats);f=pd.read_csv(a.features);wr=f[f.position.eq('WR')].copy();wr['name_key']=wr.player_display_name.fillna(wr.get('player_name','')).map(norm)
 for c in ['catch_rate','air_yards_per_target','targets']:wr[c]=pd.to_numeric(wr.get(c),errors='coerce')
 # Empirical archetype curve from 2023-25 WR seasons with useful volume.
 sample=wr[wr.targets.ge(30)&wr.catch_rate.notna()&wr.air_yards_per_target.notna()].copy();x=sample.air_yards_per_target.clip(3,20);coef=np.polyfit(x,sample.catch_rate,2)
 def archetype(adot): return float(np.clip(np.polyval(coef,np.clip(adot,3,20)),.48,.78))
 s['catch_rate_history']=np.nan;s['catch_rate_archetype']=np.nan;s['catch_rate_qb_component']=np.nan;s['catch_rate_regressed']=np.nan;s['catch_rate_regression_applied']=False
 eligible=s.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])&s.position.eq('WR')
 for idx,r in s[eligible].iterrows():
  h=wr[wr.name_key.eq(norm(r['name']))].copy()
  if h.empty:continue
  h['sw']=h.season.map(SEASON_W).fillna(0)*np.sqrt(h.targets.clip(lower=1)/80).clip(upper=1)
  good=h.catch_rate.notna()&h.air_yards_per_target.notna()&h.sw.gt(0)
  if not good.any():continue
  hist=float(np.average(h.loc[good,'catch_rate'],weights=h.loc[good,'sw']));adot=float(np.average(h.loc[good,'air_yards_per_target'],weights=h.loc[good,'sw']));arch=archetype(adot)
  qb_delta=num(r.get('qb_environment_delta'),0);qb_component=float(np.clip(arch+.018*qb_delta,.45,.82))
  # 50% player skill, 30% archetype, 20% QB-context expectation.
  cr=float(np.clip(.50*hist+.30*arch+.20*qb_component,.45,.82));targets=num(r.get('projected_targets'),0)
  s.at[idx,'catch_rate_history']=hist;s.at[idx,'catch_rate_archetype']=arch;s.at[idx,'catch_rate_qb_component']=qb_component;s.at[idx,'catch_rate_regressed']=cr;s.at[idx,'catch_rate_regression_applied']=True;s.at[idx,'projected_receptions']=targets*cr
 for idx,r in s[s.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])].iterrows():
  d=s.loc[idx].to_dict();s.at[idx,'ppr_points']=points(d,1);s.at[idx,'half_ppr_points']=points(d,.5);s.at[idx,'standard_points']=points(d,0);s.at[idx,'ppr_per_game']=s.at[idx,'ppr_points']/GAMES;s.at[idx,'half_ppr_per_game']=s.at[idx,'half_ppr_points']/GAMES;s.at[idx,'standard_per_game']=s.at[idx,'standard_points']/GAMES
 for fmt in ['ppr_points','half_ppr_points','standard_points']:
  s[fmt.replace('_points','_overall_rank')]=s[fmt].rank(method='min',ascending=False);pc=fmt.replace('_points','_pos_rank');s[pc]=np.nan
  for pos in ['QB','RB','WR','TE']:
   mask=s.position.eq(pos)&s[fmt].notna();s.loc[mask,pc]=s.loc[mask,fmt].rank(method='min',ascending=False)
 nums=s.select_dtypes(include=[np.number]).columns;s[nums]=s[nums].round(3);s.to_csv(a.out,index=False)
 watch=s[s.name.isin(['Khalil Shakir','Jakobi Meyers','Jameson Williams','Jaylen Waddle'])];print(watch[['name','projected_targets','catch_rate_history','catch_rate_archetype','catch_rate_regressed','projected_receptions','ppr_points','ppr_pos_rank']].to_dict('records'));print('catch-rate adjusted',int(s.catch_rate_regression_applied.sum()))
if __name__=='__main__':main()
