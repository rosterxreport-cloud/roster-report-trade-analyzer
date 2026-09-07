#!/usr/bin/env python3
"""Joint veteran RB role-achievability sanity layer.

Prevents a veteran in a worsening/committee role from accidentally recreating an old career
peak because carries, targets and TD submodels are each independently optimistic. Recent
healthy usage is weighted 2025 > 2024 > 2023; current depth/competition determines how much
upside above that recent distribution is allowed. No player-specific overrides.
"""
from pathlib import Path
import re, unicodedata
import numpy as np
import pandas as pd
STATS=Path('data/projections/stat_projections_2026.csv'); ROLES=Path('data/projections/player_role_context_2026.csv'); FEATS=Path('data/projections/player_features_2023_2025.csv'); GAMES=17.; SW={2023:.15,2024:.30,2025:.55}
def num(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except: return d
def norm(v):
    t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower(); t=re.sub(r'\b(jr|sr|ii|iii|iv)\.?\b','',t); return re.sub(r'[^a-z0-9]','',t)
def score(r,rec=1.):
    x=lambda k:num(r.get(k),0.); return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')
def main():
    s=pd.read_csv(STATS); r=pd.read_csv(ROLES); f=pd.read_csv(FEATS,low_memory=False)
    keep=[c for c in ['name','position','team_2026','depth_rank','depth_starter','role_confidence'] if c in r]; rr=r[keep].rename(columns={'team_2026':'team'}); m=s.merge(rr,on=['name','position','team'],how='left',suffixes=('','_role'))
    f=f[(f.position.eq('RB')) & f.season.isin(SW)].copy(); nc='player_display_name' if 'player_display_name' in f else 'player_name'; f['nk']=f[nc].map(norm)
    hist={}
    for nk,g in f.groupby('nk'):
        games=pd.to_numeric(g.get('games'),errors='coerce').fillna(0); w=g.season.map(SW).fillna(0)*np.sqrt(games.clip(lower=1)/12).clip(upper=1); ok=w.gt(0)&games.gt(0)
        if not ok.any(): continue
        def avg(cols, per_game=False):
            for col in cols:
                if col in g:
                    x=pd.to_numeric(g[col],errors='coerce'); x=x/games.where(games>0) if per_game else x
                    good=ok&x.notna()
                    if good.any(): return float(np.average(x[good],weights=w[good]))
            return np.nan
        hist[nk]={'cpg':avg(['carries','rushing_attempts'],True),'tpg':avg(['targets'],True),'rush_td_pg':avg(['rushing_tds'],True),'rec_td_pg':avg(['receiving_tds'],True)}
    for c in ['rb_achievability_applied','rb_achievability_role_factor','rb_achievability_carry_cap','rb_achievability_target_cap','rb_achievability_td_cap','rb_achievability_joint_multiplier']:
        m[c]=False if c=='rb_achievability_applied' else np.nan
    elig=m.projection_status.isin(['modeled_veteran','returning_fallback']) & m.position.eq('RB')
    for i in m.index[elig]:
        row=m.loc[i]; h=hist.get(norm(row['name']));
        if not h: continue
        rank=max(1,int(num(row.get('depth_rank'),4))); starter=bool(row.get('depth_starter',False)); conf=np.clip(num(row.get('role_confidence'),.6),0,1)
        ccomp=np.clip(num(row.get('rb_competition_carry_score'),.5),0,1); tcomp=np.clip(num(row.get('rb_competition_target_score'),.5),0,1)
        # Current role controls how much a veteran may exceed his recent healthy baseline.
        if rank==1 and starter:
            role_factor=np.clip(1.16-.28*ccomp,.84,1.14); target_factor=np.clip(1.14-.32*tcomp,.78,1.12)
        elif rank==2:
            role_factor=np.clip(.82-.20*ccomp,.58,.82); target_factor=np.clip(.80-.24*tcomp,.52,.80)
        else:
            role_factor=.55; target_factor=.50
        role_factor=.75*role_factor+.25*conf
        cpg=num(h.get('cpg'),np.nan); tpg=num(h.get('tpg'),np.nan); rtd=num(h.get('rush_td_pg'),np.nan); etd=num(h.get('rec_td_pg'),np.nan)
        carry_cap=(cpg*GAMES*max(.90,role_factor*1.18)) if np.isfinite(cpg) else np.inf
        target_cap=(tpg*GAMES*max(.82,target_factor*1.16)) if np.isfinite(tpg) else np.inf
        # TD ceiling is tied to recent scoring rate and current role; committee competition hits high-value touches too.
        recent_td=((rtd if np.isfinite(rtd) else 0)+(etd if np.isfinite(etd) else 0))*GAMES
        td_cap=max(3.0,recent_td*np.clip(.92+.28*role_factor-.22*ccomp,.72,1.18)) if recent_td>0 else np.inf
        oc=num(row.get('projected_rush_attempts'),0); ot=num(row.get('projected_targets'),0); ort=num(row.get('projected_rushing_tds'),0); oet=num(row.get('projected_receiving_tds'),0)
        cr=min(1.,carry_cap/max(oc,1e-9)); tr=min(1.,target_cap/max(ot,1e-9)); tdr=min(1.,td_cap/max(ort+oet,1e-9))
        # Smooth, not hard-cliff: only suppress the optimistic tail.
        cr=.35+.65*cr if cr<1 else 1.; tr=.30+.70*tr if tr<1 else 1.; tdr=.40+.60*tdr if tdr<1 else 1.
        m.at[i,'projected_rush_attempts']=oc*cr; m.at[i,'projected_rushing_yards']=num(row.get('projected_rushing_yards'),0)*cr
        m.at[i,'projected_targets']=ot*tr; m.at[i,'projected_receptions']=num(row.get('projected_receptions'),0)*tr; m.at[i,'projected_receiving_yards']=num(row.get('projected_receiving_yards'),0)*tr
        m.at[i,'projected_rushing_tds']=ort*tdr; m.at[i,'projected_receiving_tds']=oet*tdr
        m.at[i,'rb_achievability_applied']=True; m.at[i,'rb_achievability_role_factor']=role_factor; m.at[i,'rb_achievability_carry_cap']=carry_cap if np.isfinite(carry_cap) else np.nan; m.at[i,'rb_achievability_target_cap']=target_cap if np.isfinite(target_cap) else np.nan; m.at[i,'rb_achievability_td_cap']=td_cap if np.isfinite(td_cap) else np.nan; m.at[i,'rb_achievability_joint_multiplier']=min(cr,tr,tdr)
    all_elig=m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for i in m.index[all_elig]:
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=score(d,1); m.at[i,'half_ppr_points']=score(d,.5); m.at[i,'standard_points']=score(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/GAMES; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/GAMES; m.at[i,'standard_per_game']=m.at[i,'standard_points']/GAMES
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        m[fc.replace('_points','_overall_rank')]=m[fc].rank(method='min',ascending=False); pc=fc.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    drop=[c for c in m if c.endswith('_role') or c in {'depth_rank','depth_starter','role_confidence'}]; m=m.drop(columns=drop,errors='ignore'); nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(STATS,index=False)
    watch=['Rhamondre Stevenson','Jaylen Warren','Tony Pollard','Alvin Kamara','TreVeyon Henderson','Rico Dowdle']; print(m[m.name.isin(watch)][['name','team','projected_rush_attempts','projected_targets','projected_rushing_tds','projected_receiving_tds','ppr_points','ppr_pos_rank','rb_achievability_role_factor','rb_achievability_joint_multiplier']].to_dict('records'))
if __name__=='__main__': main()
