import csv
from collections import defaultdict
rows=list(csv.DictReader(open('data/projections/2026_week6_league_v4_full.csv')))
q={r['Team']:float(r['Pass_Att']) for r in rows if r['Position']=='QB'}
for r in rows:
 if r['Position'] not in ('WR','TE','RB') or r['Team'] not in q: continue
 share=float(r['Targets'])/q[r['Team']]
 if share>0.30: print(r['Player'],r['Team'],round(share,3))
