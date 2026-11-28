"""Apply observed official availability to release lists without changing forecasts."""
import unicodedata,re
def key(value):
 return re.sub(r"[\W_]+","",unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().lower())
def apply(artifact,availability):
 teams=availability['teams'];result={**artifact};players=[]
 for p in artifact['players']:
  team=teams.get(p['team'],{});status='unverified'
  if team.get('submitted'):
   matches=[r['status'] for r in team['players'] if key(r['name'])==key(p['name'])]
   status=matches[0].lower() if len(matches)==1 else ('active' if not matches else 'unverified')
  if status in ('out','inactive','doubtful'):continue
  players.append({**p,'status':status,'availabilityAsOf':availability['reportAsOf']})
 result['players']=players
 result['availability']={k:availability[k] for k in ['source','reportAsOf','capturedAt','sha256','gameDate']}
 return result
