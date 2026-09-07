#!/usr/bin/env python3
"""Role-based receiving TD allocation anchored to team QB TD budgets."""
from pathlib import Path
import argparse,re,unicodedata
import numpy as np
import pandas as pd
GAMES=17.;LEAGUE=.045;SW={2023:.20,2024:.30,2025:.50}
def norm(v):
 t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower();t=re.sub(r'\b(jr|sr|ii|iii|iv)\.?\b','',t);return re.sub(r'[^a-z0-9]','',t)
def num(v,d=0.):
 try:x=float(v);return x if np.isfinite(x) else d
 except:return d
def pts(r,rec):
 x=lambda k:num(r.get(k),0);return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--stats',type=Path,default=Path('data/projections/stat_projections_2026.csv'));ap.add_argument('--roles',type=Path,default=Path('data/projections/player_role_context_2026.csv'));ap.add_argument('--features',type=Path,default=Path('data/projections/player_features_2023_2025.csv'));ap.add_argument('--out',type=Path,default=Path('data/projections/stat_projections_2026.csv'));a=ap.parse_args()
 s=pd.read_csv(a.stats);r=pd.read_csv(a.roles);f=pd.read_csv(a.features);f['name_key']=f.player_display_name.fillna(f.get('player_name','')).map(norm)
 rolecols=[c for c in ['name','position','team_2026','rec_td_per_target','target_share','depth_starter','depth_rank'] if c in r];m=s.merge(r[rolecols].rename(columns={'team_2026':'role_team'}),on=['name','position'],how='left',suffixes=('','_role'));eligible=m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
 for c in ['td_allocation_share','td_individual_prior','td_role_score','td_air_yards_per_target','td_first_down_rate']:m[c]=np.nan
 hist={}
 for name,g in f[f.position.isin(['WR','TE','RB'])].groupby('name_key'):
  g=g.copy();tg=pd.to_numeric(g.get('targets'),errors='coerce').fillna(0);g['w']=g.season.map(SW).fillna(0)*np.sqrt(tg.clip(lower=1)/80).clip(upper=1)
  def avg(c,d):
   if c not in g:return d
   x=pd.to_numeric(g[c],errors='coerce');ok=g.w.gt(0)&x.notna();return float(np.average(x[ok],weights=g.loc[ok,'w'])) if ok.any() else d
  hist[name]={'tdr':avg('rec_td_per_target',LEAGUE),'adot':avg('air_yards_per_target',8.),'fd':avg('receiving_first_down_rate',.35)}
 for team,g in m[eligible&m.position.isin(['RB','WR','TE'])].groupby('team'):
  q=m[eligible&m.position.eq('QB')&m.team.eq(team)]
  if q.empty:continue
  teamtd=pd.to_numeric(q.projected_passing_tds,errors='coerce').max()
  if not np.isfinite(teamtd) or teamtd<=0:continue
  idx=g.index;tar=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0);yds=pd.to_numeric(m.loc[idx,'projected_receiving_yards'],errors='coerce').fillna(0);starter=m.loc[idx,'depth_starter'].fillna(False).astype(bool);rank=pd.to_numeric(m.loc[idx,'depth_rank'],errors='coerce').fillna(9)
  hs=[hist.get(norm(m.at[i,'name']),{'tdr':LEAGUE,'adot':8.,'fd':.35}) for i in idx];tdr=pd.Series([h['tdr'] for h in hs],index=idx).clip(.012,.11);adot=pd.Series([h['adot'] for h in hs],index=idx).clip(3,20);fd=pd.Series([h['fd'] for h in hs],index=idx).clip(.15,.65);reg=.65*LEAGUE+.35*tdr
  tsh=tar/max(tar.sum(),1);ysh=yds/max(yds.sum(),1);air=((adot-8)/8).clip(-.5,1);first=((fd-.35)/.20).clip(-1,1);yprr=pd.to_numeric(m.loc[idx,'wr_yprr_2025'],errors='coerce').fillna(1.6) if 'wr_yprr_2025' in m else pd.Series(1.6,index=idx);expl=((yprr-1.6)/1).clip(-.6,1)
  raw=.40*tsh+.18*ysh+.14*(reg/reg.sum())+.10*((air+1)/(air+1).sum())+.10*((first+1.1)/(first+1.1).sum())+.08*((expl+1)/(expl+1).sum());role=np.where(starter,1.05,np.where(rank.le(2),.97,np.where(rank.le(3),.88,.74)));w=pd.Series(raw*role,index=idx).clip(lower=.001);share=w/w.sum();individual=(.58*(tar*reg)+.42*(yds/175))*role;alloc=teamtd*.98*share;new=.62*alloc+.38*individual;new*=np.clip(teamtd*.99/max(new.sum(),.01),.90,1.12);new=new.clip(0,14)
  m.loc[idx,'projected_receiving_tds']=new;m.loc[idx,'td_allocation_share']=share;m.loc[idx,'td_individual_prior']=individual;m.loc[idx,'td_role_score']=w;m.loc[idx,'td_air_yards_per_target']=adot;m.loc[idx,'td_first_down_rate']=fd
 for i in m[eligible].index:
  d=m.loc[i].to_dict();m.at[i,'ppr_points']=pts(d,1);m.at[i,'half_ppr_points']=pts(d,.5);m.at[i,'standard_points']=pts(d,0);m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/GAMES;m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/GAMES;m.at[i,'standard_per_game']=m.at[i,'standard_points']/GAMES
 for fmt in ['ppr_points','half_ppr_points','standard_points']:
  m[fmt.replace('_points','_overall_rank')]=m[fmt].rank(method='min',ascending=False);pc=fmt.replace('_points','_pos_rank');m[pc]=np.nan
  for pos in ['QB','RB','WR','TE']:
   mask=m.position.eq(pos)&m[fmt].notna();m.loc[mask,pc]=m.loc[mask,fmt].rank(method='min',ascending=False)
 m=m.drop(columns=[c for c in ['role_team','rec_td_per_target','target_share','depth_starter','depth_rank'] if c in m],errors='ignore');nums=m.select_dtypes(include=[np.number]).columns;m[nums]=m[nums].round(3);m.to_csv(a.out,index=False)
 watch=m[m.name.isin(['Khalil Shakir','Jakobi Meyers','Jameson Williams','Jaylen Waddle'])];print(watch[['name','projected_targets','projected_receiving_tds','td_allocation_share','td_air_yards_per_target','td_first_down_rate','ppr_points','ppr_pos_rank']].to_dict('records'))
if __name__=='__main__':main()
