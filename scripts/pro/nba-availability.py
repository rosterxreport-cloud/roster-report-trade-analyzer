"""Capture the latest current official NBA injury report; never invent an injury status."""
import datetime,hashlib,json,pathlib,re,subprocess,urllib.request
from zoneinfo import ZoneInfo
TEAMS={'Atlanta Hawks':'ATL','Boston Celtics':'BOS','Brooklyn Nets':'BKN','Charlotte Hornets':'CHA','Chicago Bulls':'CHI','Cleveland Cavaliers':'CLE','Dallas Mavericks':'DAL','Denver Nuggets':'DEN','Detroit Pistons':'DET','Golden State Warriors':'GSW','Houston Rockets':'HOU','Indiana Pacers':'IND','LA Clippers':'LAC','Los Angeles Clippers':'LAC','Los Angeles Lakers':'LAL','Memphis Grizzlies':'MEM','Miami Heat':'MIA','Milwaukee Bucks':'MIL','Minnesota Timberwolves':'MIN','New Orleans Pelicans':'NOP','New York Knicks':'NYK','Oklahoma City Thunder':'OKC','Orlando Magic':'ORL','Philadelphia 76ers':'PHI','Phoenix Suns':'PHX','Portland Trail Blazers':'POR','Sacramento Kings':'SAC','San Antonio Spurs':'SAS','Toronto Raptors':'TOR','Utah Jazz':'UTA','Washington Wizards':'WAS'}
def parse(text,day):
 teams={};current_team=None;current_date=day
 for line in text.splitlines():
  match=re.match(r'^\s*(\d{2}/\d{2}/\d{4})',line)
  if match:current_date=datetime.datetime.strptime(match[1],'%m/%d/%Y').date().isoformat()
  if current_date!=day:continue
  found=next((name for name in TEAMS if re.search(r'(?:^|\s{2,})'+re.escape(name)+r'(?:\s{2,}|$)',line)),None)
  if found:
   current_team=TEAMS[found];teams.setdefault(current_team,{'submitted':True,'players':[]})
   if 'NOT YET SUBMITTED' in line:teams[current_team]['submitted']=False
  if not current_team:continue
  status=re.search(r'\s+(Out|Doubtful|Questionable|Probable|Available)(?:\s{2,}|$)',line)
  if not status:continue
  prefix=line[:status.start()].strip();cells=re.split(r'\s{2,}',prefix);name=cells[-1] if cells else ''
  if ',' not in name:
   teams[current_team]['submitted']=False;continue
  last,first=name.split(',',1)
  teams[current_team]['players'].append({'name':(first.strip()+' '+last.strip()).strip(),'status':status[1]})
 return teams
def capture(directory,now=None):
 now=now or datetime.datetime.now(ZoneInfo('America/New_York'));directory=pathlib.Path(directory);directory.mkdir(parents=True,exist_ok=True)
 rounded=now.replace(minute=now.minute//15*15,second=0,microsecond=0)
 for offset in range(4):
  stamp=rounded-datetime.timedelta(minutes=15*offset)
  url='https://ak-static.cms.nba.com/referee/injury/Injury-Report_'+stamp.strftime('%Y-%m-%d_%I_%M%p')+'.pdf'
  try:
   with urllib.request.urlopen(url,timeout=20) as response:pdf=response.read()
   if not pdf.startswith(b'%PDF'):continue
   source=directory/'injuries.pdf';source.write_bytes(pdf);target=directory/'injuries.txt'
   subprocess.run(['pdftotext','-layout',str(source),str(target)],check=True,capture_output=True)
   text=target.read_text();header=re.search(r'Injury Report:\s*(\d{2}/\d{2}/\d{2})\s+(\d{2}:\d{2} [AP]M)',text)
   if not header:continue
   asof=datetime.datetime.strptime(' '.join(header.groups()),'%m/%d/%y %I:%M %p').replace(tzinfo=ZoneInfo('America/New_York'))
   if asof.date()!=now.date() or asof>now or (now-asof).total_seconds()>5400:continue
   result={'source':url,'reportAsOf':asof.isoformat(),'capturedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':hashlib.sha256(pdf).hexdigest(),'teams':parse(text,asof.date().isoformat())}
   if not result['teams']:continue
   (directory/'availability.json').write_text(json.dumps(result))
   return result
  except Exception:continue
 raise ValueError('No complete current official NBA availability report could be parsed')
