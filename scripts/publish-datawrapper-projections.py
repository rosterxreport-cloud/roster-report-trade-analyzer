#!/usr/bin/env python3
import json,os,urllib.request,urllib.error
from pathlib import Path
TOKEN=os.environ.get("DATAWRAPPER_API_TOKEN")
if not TOKEN: raise SystemExit("DATAWRAPPER_API_TOKEN is not configured")
API="https://api.datawrapper.de/v3"
def req(method,path,data=None,ctype="application/json"):
 h={"Authorization":f"Bearer {TOKEN}"}
 if data is not None:h["Content-Type"]=ctype
 r=urllib.request.Request(API+path,data=data,headers=h,method=method)
 try:
  with urllib.request.urlopen(r,timeout=60) as x:
   b=x.read().decode();return json.loads(b) if b else {}
 except urllib.error.HTTPError as e: raise SystemExit(f"Datawrapper {method} {path} failed: {e.code} {e.read().decode()}")
def q(v):
 return '"'+str(v if v is not None else "").replace('"','""')+'"'
cfg=Path("data/datawrapper-charts.json")
# Permanent chart identities used by Roster Report embeds. Never create replacements.
conf={"qb":"FIj6e","rb":"brX2K","wr":"191in","te":"e7NFZ"}
if cfg.exists():
 saved=json.loads(cfg.read_text())
 conf.update(saved)
 conf.update({"qb":"FIj6e","rb":"brX2K","wr":"191in","te":"e7NFZ"})
specs={
 "qb":{"file":"data/new-qb-projection-preview.json","key":"weeklyPoints","limit":32,"title":"Week 3 Fantasy Football QB Rankings","cols":[("Player","player"),("Team","team"),("Opp","opponent"),("Standard","weeklyPoints"),("Half-PPR","weeklyPoints"),("PPR","weeklyPoints"),("Pass Yds","passYards"),("Pass TD","passTD"),("Rush Yds","rushYards")]},
 "rb":{"file":"data/new-rb-projection-preview.json","key":"weeklyHalfPPR","limit":50,"title":"Week 3 Fantasy Football RB Rankings","cols":[("Player","player"),("Team","team"),("Opp","opponent"),("Standard","weeklyStandard"),("Half-PPR","weeklyHalfPPR"),("PPR","weeklyPPR"),("Carries","carries"),("Targets","targets"),("Rush Yds","rushYds"),("Rec Yds","recYds"),("TD","TD")]},
 "wr":{"file":"data/new-wr-projection-preview.json","key":"weeklyHalfPPR","limit":50,"title":"Week 3 Fantasy Football WR Rankings","cols":[("Player","player"),("Team","team"),("Opp","opponent"),("Standard","weeklyStandard"),("Half-PPR","weeklyHalfPPR"),("PPR","weeklyPPR"),("Targets","targets"),("Rec","receptions"),("Yds","recYds"),("TD","TD")]},
 "te":{"file":"data/new-te-projection-preview.json","key":"halfPPR","limit":25,"title":"Week 3 Fantasy Football TE Rankings","cols":[("Player","player"),("Team","team"),("Opp","opponent"),("Standard","standard"),("Half-PPR","halfPPR"),("PPR","fullPPR"),("Targets","targets"),("Rec","receptions"),("Yds","recYds"),("TD","TD")]}
}
for pos,s in specs.items():
 rows=json.loads(Path(s["file"]).read_text());rows=sorted(rows,key=lambda x:float(x.get(s["key"]) or -999),reverse=True)[:s["limit"]]
 header=["Rank"]+[x[0] for x in s["cols"]];lines=[",".join(header)]
 for i,x in enumerate(rows,1):
  vals=[]
  for label,k in s["cols"]:
   v=x.get(k)
   if label in ("Standard","Half-PPR","PPR","Proj Pts","Proj PPR") and v is not None:
    try: v=f"{float(v):.1f} pts"
    except (TypeError,ValueError): pass
   vals.append(q(v))
  lines.append(",".join([str(i)]+vals))
 cid=conf.get(pos)
 if not cid:
  ch=req("POST","/charts",json.dumps({"title":s["title"],"type":"tables"}).encode());cid=ch["id"];conf[pos]=cid
 req("PUT",f"/charts/{cid}/data",("\n".join(lines)+"\n").encode(),"text/csv")
 meta={"describe":{"intro":"The Roster Report model projections. Updated automatically as injuries, roles and matchups change.","byline":"The Roster Report","source-name":"The Roster Report Projection Model","notes":"Weekly fantasy football projections. Scoring format is shown in the table title."},"visualize":{"dark-mode-invert":True,"header":{"style":{"bold":True}},"table":{"striped":True,"row-height":"compact","mobile-first":True},"perPage":10,"pagination":True,"columns":{"Rank":{"align":"center","width":"small"},"Player":{"align":"left","bold":True},"Team":{"align":"center","width":"small"},"Opp":{"align":"center","width":"small"},"Proj Pts":{"align":"right","bold":True,"heatmap":True,"number-format":"0.0","type":"text"},"Proj PPR":{"align":"right","bold":True,"heatmap":True,"number-format":"0.0","type":"text"}},"custom-colors":{"football-blue":"#1261A0","football-yellow":"#F2C94C"}}}
 req("PATCH",f"/charts/{cid}",json.dumps({"title":s["title"],"metadata":meta}).encode())
 req("POST",f"/charts/{cid}/publish",b"{}")
 ch=req("GET",f"/charts/{cid}");print(json.dumps({"position":pos.upper(),"chartId":cid,"publicUrl":ch.get("publicUrl")}))
cfg.write_text(json.dumps(conf,indent=2)+"\n")
