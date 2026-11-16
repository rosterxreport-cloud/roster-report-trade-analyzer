"""Release authorization for the unchanged incumbent; never changes source forecasts."""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path

def authorize(model_dir,snapshot,policy_path,now=None):
    policy=json.loads(Path(policy_path).read_text())
    if policy.get('approved') is not True or policy.get('sport')!='NBA':
        raise ValueError('NBA incumbent release is not authorized')
    for field in ('model','modelFingerprint','featureWeightsSha256'):
        if not policy.get(field) or snapshot.get(field)!=policy[field]:
            raise ValueError('NBA source is not the approved incumbent: '+field)
    files=policy.get('sourceFiles',{})
    if not {'simulate_slate.py','draftkings_audit.py','model.py'}.issubset(files):
        raise ValueError('Incomplete incumbent source pins')
    for name,digest in files.items():
        if Path(name).name!=name or hashlib.sha256((model_dir/'src'/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Incumbent source changed: '+name)
    now=now or datetime.now(timezone.utc)
    captured=datetime.fromisoformat(snapshot['createdAt'].replace('Z','+00:00'))
    starts=[datetime.fromisoformat(f['start'].replace('Z','+00:00')) for f in snapshot['fixtures']]
    if captured.tzinfo is None or not starts or any(s.tzinfo is None for s in starts) or captured>now or min(starts)<=now:
        raise ValueError('Source must be a current pre-lock forecast')
    return {'policyHash':hashlib.sha256(Path(policy_path).read_bytes()).hexdigest(),
            'authorization':policy['authorization'],'sourcePublishApproved':snapshot.get('publishApproved') is True}
