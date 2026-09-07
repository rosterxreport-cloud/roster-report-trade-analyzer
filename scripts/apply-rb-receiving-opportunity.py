#!/usr/bin/env python3
"""Reconcile RB receiving opportunity to current role, coaching, competition and rookie college receiving evidence.

Current role is the anchor. Positive role changes unlock receiving upside; negative role changes
accelerate decay of historical target volume. Team RB target budgets are preserved.
"""
from pathlib import Path
import re, unicodedata
import numpy as np
import pandas as pd
STATS=Path('data/projections/stat_projections_2026.csv'); ROLES=Path('data/projections/player_role_context_2026.csv'); COACH=Path('data/projections/coaching_scheme_context_2026.csv'); FEATURES=Path('data/projections/player_features_2023_2025.csv'); COLLEGE=Path('data/rookie_rb_college_2026.csv'); GAMES=17.; SW={2023:.20,2024:.30,2025:.50}
def num(v,d=np.nan):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except (TypeError,ValueError): return d
def norm(v):
    t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower(); t=re.sub(r'\b(jr|sr|ii|iii|iv)\.?\b','',t); return re.sub(r'[^a-z0-9]','',t)
def score(r,rec=1.):
    x=lambda k:num(r.get(k),0.); return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')
def main():
    s=pd.read_csv(STATS); r=pd.read_csv(ROLES); c=pd.read_csv(COACH) if COACH.exists() else pd.DataFrame(); f=pd.read_csv(FEATURES) if FEATURES.exists() else pd.DataFrame(); college=pd.read_csv(COLLEGE) if COLLEGE.exists() else pd.DataFrame()
    keep=[x for x in ['name','position','team_2026','depth_rank','depth_starter','role_target_share_2026','targets_per_game','role_confidence','rookie'] if x in r]; rr=r[keep].rename(columns={'team_2026':'team'}); m=s.merge(rr,on=['name','position','team'],how='left',suffixes=('','_role')); eligible=m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])&m.position.eq('RB')
    hist={}
    if len(f):
        f=f[f.position.eq('RB')].copy(); f['name_key']=f.player_display_name.fillna(f.get('player_name','')).map(norm)
        for nk,g in f.groupby('name_key'):
            games=pd.to_numeric(g.get('games'),errors='coerce').fillna(0); tg=pd.to_numeric(g.get('targets'),errors='coerce').fillna(0); tpg=tg/games.where(games>0); w=g.season.map(SW).fillna(0)*np.sqrt(games.clip(lower=1)/12).clip(upper=1); ok=w.gt(0)&tpg.notna()
            if ok.any(): hist[nk]=float(np.average(tpg[ok],weights=w[ok]))
    college_rec={}
    if len(college):
        college=college.copy(); college['name_key']=college.name.map(norm)
        for _,row in college.iterrows():
            rec=max(0,num(row.get('receptions'),0)); games=max(1,num(row.get('games'),1)); yds=max(0,num(row.get('receiving_yards'),0)); college_rec[row.name_key]=float(np.clip(1.65+.38*(rec/games)+.0022*yds,1.5,4.8))
    coach={row.team:row for _,row in c.iterrows()} if len(c) and 'team' in c else {}
    for col in ['rb_receiving_role_applied','rb_receiving_target_share','rb_receiving_role_score','rb_receiving_history_tpg','rb_receiving_college_tpg','rb_receiving_coach_multiplier','rb_receiving_role_change_multiplier']:
        m[col]=False if col=='rb_receiving_role_applied' else np.nan
    for team,g in m[eligible].groupby('team'):
        idx=list(g.index); old_t=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0.); budget=float(old_t.sum())
        if budget<=0: continue
        cr=coach.get(team); coach_mult=1.
        if cr is not None:
            pr=num(cr.get('coach_pass_rate_index'),1.); pv=num(cr.get('coach_pass_volume_index'),1.); conf=np.clip(num(cr.get('coaching_confidence'),0),0,1); coach_mult=float(np.clip(1+conf*(.18*(pr-1)+.12*(pv-1)),.94,1.06))
        weights=[]
        for i in idx:
            row=m.loc[i]; rank=max(1,int(num(row.get('depth_rank'),4))); starter=bool(row.get('depth_starter',False)); conf=np.clip(num(row.get('role_confidence'),.6),0,1); depth={1:1.,2:.58,3:.32,4:.16}.get(rank,.10); depth*=1.10 if starter else 1.
            role_share=np.clip(num(row.get('role_target_share_2026'),.045),.005,.30); ht=num(hist.get(norm(row['name']),row.get('targets_per_game')),1.8); rookie=(row.get('projection_status')=='rookie_model') or bool(row.get('rookie',False)); coll=college_rec.get(norm(row['name']),np.nan)
            current=.58*depth+.30*np.clip(role_share/.10,.05,2.5)
            # Historical usage decays sharply for demoted backs; proven receiving RB1s retain upside.
            hist_decay=1.0 if rank==1 else (.48 if rank==2 else .25); history=.12*np.clip(ht/3.,.20,1.9)*hist_decay
            w=current+history; role_mult=1.
            if rookie:
                cs=np.clip(num(coll,2.4)/3.,.50,1.65); w=.60*current+.40*cs
                if rank==1 and starter: role_mult*=1.18+0.08*conf
            elif rank==1 and starter and ht>=2.6:
                role_mult*=1.10+0.05*conf
            elif rank>=2:
                role_mult*=.88 if rank==2 else .78
            w*=coach_mult*role_mult; weights.append(max(.01,w)); m.at[i,'rb_receiving_history_tpg']=ht; m.at[i,'rb_receiving_college_tpg']=coll if np.isfinite(num(coll,np.nan)) else np.nan; m.at[i,'rb_receiving_coach_multiplier']=coach_mult; m.at[i,'rb_receiving_role_change_multiplier']=role_mult; m.at[i,'rb_receiving_role_score']=w
        w=np.asarray(weights,float); w/=w.sum()
        # Clear RB1 receiving floors: uncertainty is not evidence of a tiny role. Proven receiving RB1s get a higher floor.
        ranks=[max(1,int(num(m.loc[i].get('depth_rank'),4))) for i in idx]
        for j,i in enumerate(idx):
            row=m.loc[i]; rookie=(row.get('projection_status')=='rookie_model') or bool(row.get('rookie',False)); ht=num(hist.get(norm(row['name']),row.get('targets_per_game')),1.8)
            floor=0.
            if ranks[j]==1 and bool(row.get('depth_starter',False)):
                floor=.47 if rookie else (.55 if ht>=2.6 else .46)
            if floor and w[j]<floor and len(w)>1:
                need=floor-w[j]; oth=np.arange(len(w))!=j; take=w[oth].sum(); w[j]=floor; w[oth]*=(1-floor)/max(take,1e-9)
        if len(w)>1 and w.max()>.68:
            k=int(w.argmax()); excess=w[k]-.68; w[k]=.68; oth=np.arange(len(w))!=k; w[oth]+=excess*w[oth]/w[oth].sum()
        for j,i in enumerate(idx):
            row=m.loc[i]; ot=max(num(row.get('projected_targets'),0),1e-6); nt=budget*w[j]; ratio=nt/ot; m.at[i,'projected_targets']=nt
            for col in ['projected_receptions','projected_receiving_yards','projected_receiving_tds']: m.at[i,col]=num(row.get(col),0)*ratio
            m.at[i,'rb_receiving_role_applied']=True; m.at[i,'rb_receiving_target_share']=w[j]
    all_elig=m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])
    for i in m.index[all_elig]:
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=score(d,1); m.at[i,'half_ppr_points']=score(d,.5); m.at[i,'standard_points']=score(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/GAMES; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/GAMES; m.at[i,'standard_per_game']=m.at[i,'standard_points']/GAMES
    for fc in ['ppr_points','half_ppr_points','standard_points']:
        m[fc.replace('_points','_overall_rank')]=m[fc].rank(method='min',ascending=False); pc=fc.replace('_points','_pos_rank'); m[pc]=np.nan
        for p in ['QB','RB','WR','TE']:
            mask=m.position.eq(p)&m[fc].notna(); m.loc[mask,pc]=m.loc[mask,fc].rank(method='min',ascending=False)
    drop=[x for x in m.columns if x.endswith('_role') or x in {'depth_rank','depth_starter','role_target_share_2026','targets_per_game','role_confidence','rookie'}]; m=m.drop(columns=drop,errors='ignore'); nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(STATS,index=False)
if __name__=='__main__': main()
