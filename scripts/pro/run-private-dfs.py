"""Run the established private NBA producer and publish authorized outputs.
No training, research variants or timestamp-only refreshes are invoked.
"""
import contextlib,datetime,hashlib,importlib.util,io,json,os,pathlib,shutil,subprocess,sys,tempfile,urllib.request
from zoneinfo import ZoneInfo
ROOT=pathlib.Path(os.environ.get('DFS_MODEL_ROOT','/vercel/private-recovery/Roster_Report_Basketball_Private_Research_v0_5/roster-basketball-model'))
REPO=pathlib.Path(__file__).resolve().parents[2]
PUBLISH=os.environ['DFS_PUBLISH_URL']
TOKEN=os.environ['DFS_PUBLISH_TOKEN']
def publish(path,data):
 raw=json.dumps({'path':path,'data':data},separators=(',',':'),allow_nan=False).encode()
 request=urllib.request.Request(PUBLISH,data=raw,headers={'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'})
 with urllib.request.urlopen(request,timeout=45) as response:return json.load(response)
def nba_slate_date(pool,now=None):
 """Choose the real upcoming operator slate's game date; never relabel an old forecast."""
 now=now or datetime.datetime.now(datetime.timezone.utc)
 starts=[]
 for row in pool.get('players',[]):
  value=row.get('startsAt')
  if value:
   start=datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
   if start>now:starts.append(start)
 if not starts:
  value=pool.get('locksAt')
  if value:
   start=datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
   if start>now:starts.append(start)
 if not starts:raise ValueError('No upcoming verified NBA salary games')
 return min(starts).astimezone(ZoneInfo('America/New_York')).date()
def execute():
 today=datetime.datetime.now(ZoneInfo('America/New_York')).date()
 report={'state':'partial','nba':{'state':'pending'},'salaries':{},'slates':{'NBA':'Requires complete verified identity and current availability evidence','NFL':'Requires matching established weekly forecasts; original core scoring and attributed DST source are configured'}}
 with tempfile.TemporaryDirectory(prefix='rr-dfs-') as directory:
  work=pathlib.Path(directory);output=work/'artifacts';nba_ready=False
  for sport in ['NBA','NFL']:
   capture=work/sport.lower()
   try:
    result=subprocess.run(['node',str(REPO/'scripts/pro/capture-current-salaries.mjs'),sport,str(capture)],capture_output=True,text=True,timeout=100)
    if result.returncode:report['salaries'][sport]={'state':'failed','reason':'Current official salary capture did not pass'}
    else:
     pool=json.loads((capture/'salary-pool.json').read_text())
     report['salaries'][sport]={'state':'validated','players':len(pool['players']),'draftGroupId':pool['draftGroupId'],'locksAt':pool['locksAt']}
     archive=ROOT/'forward/salary-captures'/str(today);archive.mkdir(parents=True,exist_ok=True)
     shutil.copyfile(capture/'salary-pool.json',archive/(sport+'-'+pool['draftGroupId']+'-'+str(int(datetime.datetime.now().timestamp()))+'.json'))
   except Exception:report['salaries'][sport]={'state':'failed','reason':'Official salary retrieval unavailable'}
  try:
   pool_file=work/'nba/salary-pool.json'
   forecast_date=nba_slate_date(json.loads(pool_file.read_text())) if pool_file.exists() else today
   model=work/'model';shutil.copytree(ROOT,model,ignore=shutil.ignore_patterns('__pycache__','tmp','run-artifacts'))
   for relative in ['tmp/pdfs','forward/predictions','data/injury_reports','data/starters','data/features_weekly']:(model/relative).mkdir(parents=True,exist_ok=True)
   # Preserve every original forecast. Recompute in an isolated working copy using fresh observed inputs.
   snapshot=model/'forward/predictions'/f'{forecast_date}.json'
   if snapshot.exists():snapshot.unlink()
   sys.path.insert(0,str(model/'src'))
   import run_forward
   with (work/'producer.log').open('w') as log,contextlib.redirect_stdout(log):
    manifest=run_forward.verify_frozen()
    data,refresh_receipt=run_forward.refresh(forecast_date,forecast_date.year+(forecast_date.month>=7))
    generated=run_forward.forecast(forecast_date,data,manifest)
   if not snapshot.exists():raise RuntimeError('Established producer did not create a forecast')
   source=json.loads(snapshot.read_text())
   if not source.get('predictions') or not source.get('fixtures'):
    report['nba']={'state':'idle','reason':'No upcoming NBA games have established forecasts'}
    raise StopIteration()
   destination=model/'forward/predictions/runs';destination.mkdir(exist_ok=True)
   # Immutable source receipts survive the sandbox snapshot for audit/recovery.
   archive=ROOT/'forward/predictions/runs';archive.mkdir(exist_ok=True)
   source_hash=hashlib.sha256(snapshot.read_bytes()).hexdigest()
   saved=archive/(str(forecast_date)+'-'+source_hash+'.json')
   if not saved.exists():shutil.copyfile(snapshot,saved)
   output=work/'artifacts'
   command=[sys.executable,str(REPO/'scripts/pro/export-nba.py'),'--model-dir',str(model),'--snapshot',str(snapshot),'--output',str(output),'--release-policy',str(REPO/'config/nba-incumbent-release.json')]
   with (work/'export.log').open('w') as log:
    subprocess.run(command,check=True,stdout=log,stderr=log,timeout=90)
   receipts=[]
   for name in ['basic','distributions']:
    artifact=json.loads((output/(name+'.json')).read_text());receipt=publish('nba/'+name+'.json',artifact);receipts.append(receipt)
   report['nba']={'state':'published','players':len(source['predictions']),'draws':10000,'capturedAt':source['createdAt'],'sourceHash':source_hash,'model':source['model'],'receipts':receipts}
   nba_ready=True
  except StopIteration:pass
  except Exception as error:report['nba']={'state':'failed','errorType':type(error).__name__,'reason':'Established NBA refresh did not pass; prior artifacts retained'}
  try:
   if not nba_ready:raise ValueError('NBA model stage is not ready')
   spec=importlib.util.spec_from_file_location('nba_availability',REPO/'scripts/pro/nba-availability.py');availability_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(availability_module)
   availability_module.capture(work/'availability',game_date=forecast_date.isoformat())
   pool_path=work/'nba/salary-pool.json'
   if not pool_path.exists():raise ValueError('Verified salary pool unavailable')
   pool=json.loads(pool_path.read_text())
   args=['node',str(REPO/'scripts/pro/assemble-nba-slate.mjs'),str(pool_path),str(work/'nba'/('nba-'+pool['draftGroupId']+'-csv.response')),str(output/'basic.json'),str(output/'joint.json'),str(work/'availability/availability.json'),str(output/'distributions.json')]
   result=subprocess.run(args,capture_output=True,text=True,timeout=100)
   lines=(result.stdout if result.returncode==0 else result.stderr).strip().splitlines()
   report['slates']['NBA']=json.loads(lines[-1]) if lines else {'state':'blocked','reason':'NBA slate assembly unavailable'}
  except Exception as error:report['slates']['NBA']={'state':'blocked','reason':'Current NBA eligibility and source verification did not pass','errorType':type(error).__name__}
  try:
   pool_path=work/'nfl/salary-pool.json'
   if not pool_path.exists():raise ValueError('Verified NFL salary pool unavailable')
   pool=json.loads(pool_path.read_text())
   args=['node',str(REPO/'scripts/pro/assemble-nfl-slate.mjs'),str(pool_path),str(work/'nfl'/('nfl-'+pool['draftGroupId']+'-csv.response'))]
   result=subprocess.run(args,capture_output=True,text=True,timeout=100)
   lines=(result.stdout if result.returncode==0 else result.stderr).strip().splitlines()
   report['slates']['NFL']=json.loads(lines[-1]) if lines else {'state':'blocked','reason':'NFL weekly source verification unavailable'}
  except Exception as error:report['slates']['NFL']={'state':'blocked','reason':'Matching established weekly NFL source is unavailable','errorType':type(error).__name__}
  if all(isinstance(report['slates'].get(s),dict) and report['slates'][s].get('state')=='published' for s in ['NBA','NFL']):report['state']='published'
  (ROOT/'forward/latest-runtime-receipt.json').write_text(json.dumps(report,indent=2))
 return report
if __name__=='__main__':
 try:print(json.dumps(execute(),separators=(',',':'),allow_nan=False))
 except Exception as error:
  print(json.dumps({'state':'failed','stage':'established-model-refresh','errorType':type(error).__name__}))
  sys.exit(1)