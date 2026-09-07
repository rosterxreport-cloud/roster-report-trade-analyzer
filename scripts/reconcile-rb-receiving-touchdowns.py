#!/usr/bin/env python3
"""Reconcile RB receiving TDs using receiving role, high-value opportunity and team pass-TD budget.

Runs after the generic receiving-TD allocator. Preserves each team's modeled RB receiving-TD
budget while reallocating it according to RB target share, receiving hierarchy, efficiency,
QB environment and explicit red-zone fields when available.
"""
from pathlib import Path
import re,unicodedata
import numpy as np
import pandas as pd

STATS=Path('data/projections/stat_projections_2026.csv')
ROLES=Path('data/projections/player_role_context_2026.csv')
FEAT=Path('data/projections/player_features_2023_2025.csv')
GAMES=17.0; SW={2023:.20,2024:.30,2025:.50}

def norm(v):
    t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower(); t=re.sub(r'\b(jr|sr|ii|iii|iv)\.?\b','',t); return re.sub(r'[^a-z0-9]','',t)
def num(v,d=0.0):
    try:
        x=float(v); return x if np.isfinite(x) else d
    except (TypeError,ValueError): return d

def points(r,rec=1.0):
    x=lambda k:num(r.get(k),0); return .04*x('projected_passing_yards')+4*x('projected_passing_tds')-2*x('projected_interceptions')+.1*x('projected_rushing_yards')+6*x('projected_rushing_tds')+rec*x('projected_receptions')+.1*x('projected_receiving_yards')+6*x('projected_receiving_tds')

def main():
    s=pd.read_csv(STATS); r=pd.read_csv(ROLES); f=pd.read_csv(FEAT)
    keep=[c for c in ['name','position','team_2026','depth_rank','depth_starter','role_target_share_2026','role_confidence'] if c in r]
    rr=r[keep].rename(columns={'team_2026':'team'})
    m=s.merge(rr,on=['name','position','team'],how='left',suffixes=('','_role'))
    f['name_key']=f.player_display_name.fillna(f.get('player_name','')).map(norm)
    hist={}
    for name,g in f[f.position.eq('RB')].groupby('name_key'):
        g=g.copy(); tg=pd.to_numeric(g.get('targets'),errors='coerce').fillna(0); g['w']=g.season.map(SW).fillna(0)*np.sqrt(tg.clip(lower=1)/50).clip(upper=1)
        def avg(c,d):
            if c not in g: return d
            x=pd.to_numeric(g[c],errors='coerce'); ok=g.w.gt(0)&x.notna(); return float(np.average(x[ok],weights=g.loc[ok,'w'])) if ok.any() else d
        hist[name]={'tdr':avg('rec_td_per_target',.022),'ypt':avg('yards_per_target',5.8),'epa':avg('receiving_epa_per_target',0.0),'catch':avg('catch_rate',.73)}
    elig=m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model']) & m.position.eq('RB')
    for c in ['rb_rec_td_reconciled','rb_rec_td_share','rb_rec_td_team_budget','rb_rec_td_high_value_score','rb_rec_td_proxy_used']:
        m[c]=False if c in ['rb_rec_td_reconciled','rb_rec_td_proxy_used'] else np.nan
    for team,g in m[elig].groupby('team'):
        idx=list(g.index); tar=pd.to_numeric(m.loc[idx,'projected_targets'],errors='coerce').fillna(0.0); old=pd.to_numeric(m.loc[idx,'projected_receiving_tds'],errors='coerce').fillna(0.0)
        if tar.sum()<=0: continue
        budget=float(max(.25,old.sum()))
        tsh=(tar/tar.sum()).to_numpy(); weights=[]; hvlist=[]; proxies=[]
        for j,i in enumerate(idx):
            row=m.loc[i]; h=hist.get(norm(row.get('name')),{'tdr':.022,'ypt':5.8,'epa':0.0,'catch':.73}); rank=max(1,int(num(row.get('depth_rank'),4))); starter=bool(row.get('depth_starter',False)); depth={1:1.0,2:.70,3:.40,4:.22}.get(rank,.15); depth*=1.06 if starter else 1.0
            rz=num(row.get('red_zone_targets'),np.nan); iz10=num(row.get('inside_10_targets'),np.nan); iz5=num(row.get('inside_5_targets'),np.nan)
            explicit=[x for x in [rz,iz10,iz5] if np.isfinite(x) and x>=0]
            if explicit:
                hv=max(.01,.25*(rz if np.isfinite(rz) else 0)+.55*(iz10 if np.isfinite(iz10) else 0)+1.0*(iz5 if np.isfinite(iz5) else 0)); proxy=False
            else:
                role_t=np.clip(num(row.get('role_target_share_2026'),.04),.005,.35); hv=max(.01,.70*tsh[j]+.20*(role_t/.10)+.10*(depth/1.06)); proxy=True
            eff=np.clip(.40*(h['ypt']/5.8)+.25*((h['epa']+.15)/.15)+.20*(h['catch']/.73)+.15*(h['tdr']/.022),.60,1.45)
            qb=1+np.clip(num(row.get('qb_environment_delta'),0),-.12,.12)*.35
            w=.50*hv+.25*tsh[j]+.15*(depth/1.06)+.10*eff; w*=qb
            weights.append(max(.001,w)); hvlist.append(hv); proxies.append(proxy)
        w=np.asarray(weights,float); w/=w.sum()
        if len(w)>1 and w.max()>.70:
            k=int(w.argmax()); excess=w[k]-.70; w[k]=.70; oth=np.arange(len(w))!=k; w[oth]+=excess*w[oth]/w[oth].sum()
        new=budget*w
        # Require meaningful receiving volume for extreme TD totals.
        caps=np.maximum(1.0,tar.to_numpy()*.055); clipped=new>caps; excess=float(np.maximum(new-caps,0).sum()); new=np.minimum(new,caps)
        for _ in range(3):
            room=np.maximum(caps-new,0); mask=room>1e-9
            if excess<=1e-9 or not mask.any(): break
            rw=w*mask; rw/=rw.sum(); add=np.minimum(room,excess*rw); new+=add; excess-=add.sum()
        if new.sum()>0 and abs(new.sum()-budget)>.01: new*=budget/new.sum()
        for j,i in enumerate(idx):
            m.at[i,'projected_receiving_tds']=new[j]; m.at[i,'rb_rec_td_reconciled']=True; m.at[i,'rb_rec_td_share']=new[j]/max(budget,1e-9); m.at[i,'rb_rec_td_team_budget']=budget; m.at[i,'rb_rec_td_high_value_score']=hvlist[j]; m.at[i,'rb_rec_td_proxy_used']=proxies[j]
    for i in m[m.projection_status.isin(['modeled_veteran','returning_fallback','rookie_model'])].index:
        d=m.loc[i].to_dict(); m.at[i,'ppr_points']=points(d,1); m.at[i,'half_ppr_points']=points(d,.5); m.at[i,'standard_points']=points(d,0); m.at[i,'ppr_per_game']=m.at[i,'ppr_points']/GAMES; m.at[i,'half_ppr_per_game']=m.at[i,'half_ppr_points']/GAMES; m.at[i,'standard_per_game']=m.at[i,'standard_points']/GAMES
    for fcol in ['ppr_points','half_ppr_points','standard_points']:
        m[fcol.replace('_points','_overall_rank')]=m[fcol].rank(method='min',ascending=False); pc=fcol.replace('_points','_pos_rank'); m[pc]=np.nan
        for pos in ['QB','RB','WR','TE']:
            mask=m.position.eq(pos)&m[fcol].notna(); m.loc[mask,pc]=m.loc[mask,fcol].rank(method='min',ascending=False)
    drop=[c for c in m.columns if c.endswith('_role') or c in {'depth_rank','depth_starter','role_target_share_2026','role_confidence'}]
    m=m.drop(columns=drop,errors='ignore'); nums=m.select_dtypes(include=[np.number]).columns; m[nums]=m[nums].round(3); m.to_csv(STATS,index=False)
    watch=['Christian McCaffrey','Bijan Robinson','Jahmyr Gibbs',"De'Von Achane",'Jeremiyah Love','Jadarian Price']
    print(m[m.name.isin(watch)][['name','team','projected_targets','projected_receiving_tds','rb_rec_td_share','rb_rec_td_proxy_used','ppr_points','ppr_pos_rank']].to_dict('records'))
if __name__=='__main__': main()
