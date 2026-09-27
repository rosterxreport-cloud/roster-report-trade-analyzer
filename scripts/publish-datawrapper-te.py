#!/usr/bin/env python3
import csv,json,os,urllib.request,urllib.error
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
   body=x.read().decode();return json.loads(body) if body else {}
 except urllib.error.HTTPError as e:
  raise SystemExit(f"Datawrapper {method} {path} failed: {e.code} {e.read().decode()}")
rows=json.loads(Path("data/new-te-projection-preview.json").read_text())
rows=sorted(rows,key=lambda x:float(x.get("fullPPR",0)),reverse=True)[:25]
out=["Rank,Player,Team,Opp,Proj PPR,Targets,Rec,Yds,TD"]
for i,x in enumerate(rows,1):
 def q(v): return '"'+str(v).replace('"','""')+'"'
 out.append(",".join([str(i),q(x["player"]),q(x["team"]),q(x["opponent"]),str(x["fullPPR"]),str(x["targets"]),str(x["receptions"]),str(x["recYds"]),str(x["TD"])]))
csvdata=("\n".join(out)+"\n").encode()
cfg=Path("data/datawrapper-charts.json")
conf=json.loads(cfg.read_text()) if cfg.exists() else {}
cid=conf.get("te_full_ppr")
if not cid:
 chart=req("POST","/charts",json.dumps({"title":"Week 3 Fantasy Football TE Rankings — Full PPR","type":"tables"}).encode())
 cid=chart["id"];conf["te_full_ppr"]=cid;cfg.write_text(json.dumps(conf,indent=2)+"\n")
req("PUT",f"/charts/{cid}/data",csvdata,"text/csv")
req("PATCH",f"/charts/{cid}",json.dumps({"title":"Week 3 Fantasy Football TE Rankings — Full PPR","metadata":{"describe":{"intro":"The Roster Report model projections. Updated automatically as the projection model refreshes.","byline":"The Roster Report","source-name":"The Roster Report Projection Model"}}}).encode())
pub=req("POST",f"/charts/{cid}/publish",b"{}")
chart=req("GET",f"/charts/{cid}")
print(json.dumps({"chartId":cid,"publicUrl":chart.get("publicUrl"),"publicVersion":chart.get("publicVersion")},indent=2))
