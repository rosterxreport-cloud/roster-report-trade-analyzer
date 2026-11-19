"""Research-only whole-game replay conditioned on frozen RR opportunity forecasts.
Not a possession simulator, not an approved replacement for RR point projections.
"""
import argparse,collections,hashlib,importlib.util,json,re
from datetime import datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

FIELDS=['Pass_Att','Pass_Yds','Pass_TD','INT','Sacks_Taken','Rush_Att','Rush_Yds','Rush_TD','Targets','Receptions','Rec_Yds','Rec_TD','Fumbles_Lost','Two_Point_Conversions','Return_TD','Offensive_Fumble_Recovery_TD']
SIMULATOR_HASH=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
FEATURES=['Pass_Att','Rush_Att','Pass_Yds','Pass_TD','Rush_TD','INT']
def helper(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def dk(box):
    f=lambda k:box[:,:,FIELDS.index(k)]
    return .04*f('Pass_Yds')+4*f('Pass_TD')-f('INT')+.1*(f('Rush_Yds')+f('Rec_Yds'))+6*(f('Rush_TD')+f('Rec_TD')+f('Return_TD')+f('Offensive_Fumble_Recovery_TD'))+f('Receptions')-f('Fumbles_Lost')+2*f('Two_Point_Conversions')+3*((f('Pass_Yds')>=300).astype(int)+(f('Rush_Yds')>=100).astype(int)+(f('Rec_Yds')>=100).astype(int))

def templates(frame,season,week):
    prior=frame[frame.season.eq(season)&frame.season_type.eq('REG')&frame.week.lt(week)]
    if prior.duplicated(['game_id','play_id']).any():raise ValueError('Duplicate source play')
    dst=helper('nfl-dst-model');rows,audit=dst.ledger(prior,week-1);defenses={(r['gameId'],r['Team']):r for r in rows}
    result=[]
    for gid,g in prior.groupby('game_id'):
        g=g.sort_values('play_id');first=g.iloc[0];teams=[first.home_team,first.away_team];plays=g.to_dict('records');features={t:np.zeros(len(FEATURES)) for t in teams}
        for r in plays:
            t=r['posteam']
            if t not in features or r.get('two_point_attempt')==1 or r.get('extra_point_attempt')==1:continue
            if r.get('pass_attempt')==1 and r.get('sack')!=1:
                features[t][0]+=1;features[t][5]+=int(r.get('interception')==1)
                if r.get('complete_pass')==1:features[t][2]+=float(r['yards_gained']);features[t][3]+=int(r.get('pass_touchdown')==1)
            if r.get('rush_attempt')==1:features[t][1]+=1;features[t][4]+=int(r.get('rush_touchdown')==1)
        for orientation in [teams,list(reversed(teams))]:
            result.append(dict(game=gid,week=int(first.week),teams=orientation,features=np.concatenate([features[t] for t in orientation]),plays=plays,dst=[defenses[gid,t] for t in orientation]))
    if len(result)<40:raise ValueError('Insufficient strictly prior game templates')
    return result

def simulate(pool,players,teams,draws=10000,seed=20261115):
    if len(teams)!=2 or teams[0]==teams[1] or len({r['id'] for r in players})!=len(players):raise ValueError('Unique players and opposing teams required')
    for r in players:
        if r['Team'] not in teams or any(not np.isfinite(r.get(k,np.nan)) or r[k]<0 for k in FEATURES+['Targets','Receptions','Rec_Yds','Rec_TD']) or r['Receptions']>r['Targets']+.01:raise ValueError('Invalid RR source opportunities')
    if any(t['week']>=players[0]['week'] for t in pool):raise ValueError('Target/future game entered template pool')
    by_team={t:[i for i,r in enumerate(players) if r['Team']==t] for t in teams}
    context=np.concatenate([np.array([sum(players[i][k] for i in by_team[t]) for k in FEATURES]) for t in teams]);matrix=np.array([t['features'] for t in pool]);scale=np.maximum(matrix.std(axis=0),1)
    distances=np.mean(((matrix-context)/scale)**2,axis=1);weights=np.exp(-.5*(distances-distances.min()));weights/=weights.sum()
    rng=np.random.default_rng(seed);chosen=rng.choice(len(pool),draws,p=weights);box=np.zeros((draws,len(players),len(FIELDS)))
    dst_scores=np.zeros((draws,2));dst_events={k:np.zeros((draws,2)) for k in helper('nfl-dst-model').WEIGHTS};dst_events['Points_Allowed']=np.zeros((draws,2))
    scoring={k:np.zeros((draws,2)) for k in ['FieldGoalsMade','ExtraPointsMade','TwoPointScores']}
    unmodeled={k:np.zeros((draws,2)) for k in ['Fumbles_Lost','Return_TD','Offensive_Fumble_Recovery_TD']}
    def role(team,kind,size):
        ids=by_team[team]
        if kind=='QB':w=np.array([players[i]['Pass_Att'] if players[i]['Position']=='QB' else 0 for i in ids])
        elif kind=='catchTD':w=np.array([players[i]['Rec_TD'] if players[i]['Receptions']>0 else 0 for i in ids])
        elif kind=='catch':w=np.array([max(0,players[i]['Receptions']-players[i]['Rec_TD']) for i in ids])
        elif kind=='target':w=np.array([max(0,players[i]['Targets']-players[i]['Receptions']) for i in ids])
        elif kind=='rushTD':w=np.array([players[i]['Rush_TD'] if players[i]['Rush_Att']>0 else 0 for i in ids])
        elif kind=='return':w=np.array([players[i].get('priorReturnAttempts',0) for i in ids])
        else:w=np.array([max(0,players[i]['Rush_Att']-players[i]['Rush_TD']) for i in ids])
        if w.sum()<=0:
            if kind=='return':return None
            # A source-projected zero-TD team can still score in a historical game.
            # Allocate by supported receptions/carries; never assign to zero-opportunity players.
            fallback={'catchTD':'Receptions','catch':'Receptions','target':'Targets','rushTD':'Rush_Att','rush':'Rush_Att'}.get(kind)
            if not fallback:raise ValueError('No projected QB for '+team)
            w=np.array([players[i][fallback] for i in ids])
        if w.sum()<=0:raise ValueError('No supported role '+kind+' for '+team)
        return rng.choice(ids,size=size,p=w/w.sum())
    for template_id in np.unique(chosen):
        t=pool[template_id];indexes=np.flatnonzero(chosen==template_id);n=len(indexes);mapping=dict(zip(t['teams'],teams));qbs={team:role(team,'QB',n) for team in teams}
        for side in [0,1]:
            dst_scores[indexes,side]=t['dst'][side]['DraftKings']
            for field in dst_events:dst_events[field][indexes,side]=t['dst'][side][field]
        def add(field,who,value):
            if who is not None:np.add.at(box[:,:,FIELDS.index(field)],(indexes,who),value)
        for play in t['plays']:
            source_team=play['posteam'];team=mapping.get(source_team)
            if team is None:continue
            side=teams.index(team);qb=qbs[team];receiver=rusher=None;flag=lambda key:play.get(key)==1
            if play.get('field_goal_result')=='made':scoring['FieldGoalsMade'][indexes,side]+=1
            if play.get('extra_point_result')=='good':scoring['ExtraPointsMade'][indexes,side]+=1
            if play.get('two_point_conv_result')=='success':scoring['TwoPointScores'][indexes,side]+=1
            conversion=flag('two_point_attempt') or flag('extra_point_attempt')
            if flag('two_point_attempt'):
                if play.get('two_point_conv_result')=='success':
                    if flag('pass_attempt'):add('Two_Point_Conversions',qb,1);add('Two_Point_Conversions',role(team,'catch',n),1)
                    elif flag('rush_attempt'):add('Two_Point_Conversions',role(team,'rush',n),1)
                    else:raise ValueError('Unclassified offensive conversion')
                continue
            if conversion:continue
            if flag('sack'):add('Sacks_Taken',qb,1)
            if flag('pass_attempt') and not flag('sack'):
                add('Pass_Att',qb,1)
                if flag('complete_pass'):
                    receiver=role(team,'catchTD' if flag('pass_touchdown') else 'catch',n)
                    add('Targets',receiver,1);add('Receptions',receiver,1);add('Rec_Yds',receiver,float(play['yards_gained']));add('Pass_Yds',qb,float(play['yards_gained']))
                    if flag('pass_touchdown'):add('Pass_TD',qb,1);add('Rec_TD',receiver,1)
                elif not flag('interception'):
                    receiver=role(team,'target',n);add('Targets',receiver,1)
                if flag('interception'):add('INT',qb,1)
            if flag('rush_attempt'):
                rusher=role(team,'rushTD' if flag('rush_touchdown') else 'rush',n);add('Rush_Att',rusher,1);add('Rush_Yds',rusher,float(play['yards_gained']))
                if flag('rush_touchdown'):add('Rush_TD',rusher,1)
            for j in [1,2]:
                fumbled=play.get(f'fumbled_{j}_team');recovered=play.get(f'fumble_recovery_{j}_team')
                if not isinstance(fumbled,str) or not isinstance(recovered,str) or fumbled==recovered:continue
                who=None;fid=play.get(f'fumbled_{j}_player_id');fteam=mapping.get(fumbled)
                if fteam==team:
                    if fid and fid==play.get('passer_player_id'):who=qb
                    elif fid and fid==play.get('receiver_player_id'):who=receiver
                    elif fid and fid==play.get('rusher_player_id'):who=rusher
                if who is None:unmodeled['Fumbles_Lost'][indexes,teams.index(fteam)]+=1
                else:add('Fumbles_Lost',who,1)
            if flag('touchdown') and not flag('pass_touchdown') and not flag('rush_touchdown'):
                scoring_team=mapping.get(play.get('td_team'))
                if play['play_type'] in ['kickoff','punt','field_goal']:
                    target=role(scoring_team,'return',n)
                    if target is None:unmodeled['Return_TD'][indexes,teams.index(scoring_team)]+=1
                    else:add('Return_TD',target,1)
                elif scoring_team==team:unmodeled['Offensive_Fumble_Recovery_TD'][indexes,side]+=1
    validation=validate(box,players,teams,dst_events,unmodeled,scoring)
    return dict(box=box,scores=dk(box),dstScores=dst_scores,dstEvents=dst_events,unmodeled=unmodeled,scoringEvents=scoring,checks=validation,effectiveTemplates=float(1/np.square(weights).sum()),templates=len(pool),templateGames=len({t['game'] for t in pool}))


def align_moments(sim,players,teams,seed):
    """Soft entropy balancing of whole outcomes against RR inputs, not actuals."""
    box=sim['box'];targets=[];columns=[];labels=[];unsupported=[];td_changes=[]
    for team in teams:
        ids=[i for i,p in enumerate(players) if p['Team']==team]
        pass_td=sum(players[i]['Pass_TD'] for i in ids);rec_td=sum(players[i]['Rec_TD'] for i in ids)
        for i in ids:
            p=players[i];fields=['Rush_Att','Rush_Yds','Rush_TD','Targets','Receptions','Rec_Yds','Rec_TD']
            if p['Position']=='QB':fields+=['Pass_Att','Pass_Yds','Pass_TD','INT']
            for field in fields:
                target=p[field]
                if field=='Rec_TD' and rec_td>0:
                    target*=pass_td/rec_td
                    if abs(target-p[field])>.001:td_changes.append(dict(id=p['id'],source=p[field],jointTarget=target))
                values=box[:,i,FIELDS.index(field)];scale=values.std()
                if scale<1e-8:
                    if abs(target-values.mean())>.01:unsupported.append(dict(id=p['id'],field=field,target=target,constant=float(values.mean())))
                    continue
                columns.append((values-values.mean())/scale);targets.append((target-values.mean())/scale);labels.append((i,field,target,scale))
    if not columns:raise ValueError('No moment constraints supported')
    X=np.column_stack(columns);mu=np.array(targets);ridge=.02
    def objective(theta):
        z=X@theta;maximum=z.max();exp=np.exp(z-maximum);w=exp/exp.sum()
        loss=maximum+np.log(exp.mean())-mu@theta+.5*ridge*(theta@theta)
        gradient=X.T@w-mu+ridge*theta
        return float(loss),gradient,w
    theta=np.zeros(len(mu));loss,gradient,weights=objective(theta);history=[]
    for iteration in range(80):
        if np.max(np.abs(gradient))<.005:break
        q=gradient.copy();alphas=[]
        for step,delta,rho in reversed(history):
            alpha=rho*(step@q);alphas.append(alpha);q-=alpha*delta
        gamma=(history[-1][0]@history[-1][1])/(history[-1][1]@history[-1][1]) if history else 1.
        direction=gamma*q
        for (step,delta,rho),alpha in zip(history,reversed(alphas)):
            direction+=step*(alpha-rho*(delta@direction))
        direction=-direction
        if gradient@direction>=0:direction=-gradient
        size=1.;accepted=False
        for _ in range(24):
            candidate=theta+size*direction;new_loss,new_gradient,new_weights=objective(candidate)
            if new_loss<=loss+1e-4*size*(gradient@direction):accepted=True;break
            size*=.5
        if not accepted:break
        step=candidate-theta;delta=new_gradient-gradient;curvature=step@delta
        if curvature>1e-10:history=(history+[(step,delta,1/curvature)])[-8:]
        theta,loss,gradient,weights=candidate,new_loss,new_gradient,new_weights
    # Moment matching may concentrate on a few rare whole games. Back off the
    # density toward uniform using only ESS, never target-game actual results.
    minimum_effective=max(200,.1*len(box));temperature=1.
    if 1/(weights@weights)<minimum_effective:
        logs=np.log(np.maximum(weights,1e-300));logs-=logs.max();low,high=0.,1.
        for _ in range(40):
            middle=(low+high)/2;candidate=np.exp(middle*logs);candidate/=candidate.sum()
            if 1/(candidate@candidate)>=minimum_effective:low=middle
            else:high=middle
        temperature=low;weights=np.exp(temperature*logs);weights/=weights.sum()
    effective=float(1/(weights@weights));diagnostic=dict(temperature=temperature,minimumEffectiveDraws=minimum_effective,policy='soft-whole-game-entropy-moment-alignment-v1',ridge=ridge,iterations=iteration+1,effectiveDraws=effective,constraints=len(mu),unsupportedMoments=unsupported,receiverTDTargetChanges=td_changes,weightedMaxStandardizedError=float(np.max(np.abs(X.T@weights-mu))),accepted=effective>=200)
    if effective<200:
        diagnostic['reason']='Insufficient effective draws; original candidate retained';return sim,diagnostic
    rng=np.random.default_rng(seed);index=rng.choice(len(box),len(box),p=weights)
    aligned={**sim,'box':box[index],'scores':sim['scores'][index],'dstScores':sim['dstScores'][index],'dstEvents':{k:v[index] for k,v in sim['dstEvents'].items()},'unmodeled':{k:v[index] for k,v in sim['unmodeled'].items()},'scoringEvents':{k:v[index] for k,v in sim['scoringEvents'].items()}}
    aligned['checks']=validate(aligned['box'],players,teams,aligned['dstEvents'],aligned['unmodeled'],aligned['scoringEvents'])
    diagnostic['resampledMaxStandardizedError']=float(max(abs(aligned['box'][:,i,FIELDS.index(f)].mean()-target)/scale for i,f,target,scale in labels))
    return aligned,diagnostic

def validate(box,players,teams,dst,unmodeled,scoring=None):
    if not np.isfinite(box).all():raise ValueError('Nonfinite outcomes')
    for f in FIELDS:
        values=box[:,:,FIELDS.index(f)]
        if f not in ['Pass_Yds','Rush_Yds','Rec_Yds'] and ((values<0).any() or not np.equal(values,np.floor(values)).all()):raise ValueError('Invalid event counts')
    f=lambda name:box[:,:,FIELDS.index(name)]
    if (f('Receptions')>f('Targets')).any() or (f('Rec_TD')>f('Receptions')).any() or (f('Rush_TD')>f('Rush_Att')).any() or (f('Pass_TD')+f('INT')>f('Pass_Att')).any():raise ValueError('Individual scoring events exceed opportunities')
    get=lambda name,ids:box[:,ids,FIELDS.index(name)].sum(axis=1)
    for side,team in enumerate(teams):
        ids=[i for i,p in enumerate(players) if p['Team']==team]
        if (get('Targets',ids)>get('Pass_Att',ids)).any():raise ValueError('Team targets exceed attempts')
        for a,b in [('Pass_Yds','Rec_Yds'),('Pass_TD','Rec_TD')]:
            if not np.allclose(get(a,ids),get(b,ids)):raise ValueError('QB/receiver scoring identity failed')
        if not np.array_equal(get('INT',ids),dst['Interceptions'][:,1-side]):raise ValueError('Interception/DST identity failed')
        if not np.array_equal(get('Sacks_Taken',ids),dst['Sacks'][:,1-side]):raise ValueError('Sack/DST identity failed')
        if not np.array_equal(get('Fumbles_Lost',ids)+unmodeled['Fumbles_Lost'][:,side],dst['Fumble_Recoveries'][:,1-side]):raise ValueError('Fumble/DST identity failed')
        if scoring is not None:
            points=6*(get('Pass_TD',ids)+get('Rush_TD',ids)+get('Offensive_Fumble_Recovery_TD',ids)+unmodeled['Offensive_Fumble_Recovery_TD'][:,side]+dst['Return_TD'][:,side]+dst['Blocked_Kick_Return_TD'][:,side])+2*(scoring['TwoPointScores'][:,side]+dst['Conversion_Returns'][:,side])+scoring['ExtraPointsMade'][:,side]+3*scoring['FieldGoalsMade'][:,side]
            if not np.array_equal(points,dst['Points_Allowed'][:,1-side]):raise ValueError('Offensive/special-team points allowed identity failed')
        if (get('Receptions',ids)>get('Targets',ids)).any() or (get('Rec_TD',ids)>get('Receptions',ids)).any() or (get('Rush_TD',ids)>get('Rush_Att',ids)).any():raise ValueError('TD/opportunity constraints failed')
    return dict(passingReceivingYards=True,passingReceivingTD=True,interceptions=True,sacks=True,fumbleRecoveries=True,pointsAllowed=scoring is not None,opportunities=True,draws=len(box))


def run(forecast,pbp,stats,schedule,season,week,captured,output,draws=10000,align=False):
    cutoff=datetime.fromisoformat(captured.replace('Z','+00:00'))
    if cutoff.utcoffset() is None:raise ValueError('Timezone required')
    output.mkdir(parents=True,exist_ok=False)
    frame=pd.read_parquet(pbp);pool=templates(frame,season,week);forecasts=pd.read_csv(forecast).to_dict('records');games=pd.read_csv(schedule);games=games[games.season.eq(season)&games.week.eq(week)&games.game_type.eq('REG')]
    observed=pd.read_parquet(stats);observed=observed[observed.season.eq(season)&observed.season_type.eq('REG')]
    history=observed[observed.week.lt(week)];observed=observed[observed.week.eq(week)]
    event=helper('nfl-event-candidate');prior_ids=collections.defaultdict(set)
    for r in history.to_dict('records'):prior_ids[event.name_key(r['player_display_name']),r['position']].add(r['player_id'])
    results=[];excluded=[];summaries=[];score_vectors={};all_players=[];game_checks=[];correlations=[]
    for g in games.to_dict('records'):
        start=datetime.fromisoformat(g['gameday']+'T'+g['gametime']).replace(tzinfo=ZoneInfo('America/New_York'))
        if start<=cutoff:excluded.append(dict(game=g['game_id'],reason='Game started before saved forecast capture'));continue
        teams=[g['home_team'],g['away_team']];players=[dict(r,week=week,id='rr:'+r['Team']+':'+event.name_key(r['Player'])) for r in forecasts if r['Team'] in teams]
        if any(r['Opponent']!=teams[1-teams.index(r['Team'])] for r in players):raise ValueError('Forecast opponent mismatch')
        if not players:excluded.append(dict(game=g['game_id'],reason='No saved RR player forecasts'));continue
        for r in players:
            ids=prior_ids[event.name_key(r['Player']),r['Position']];r['sourcePlayerId']=next(iter(ids)) if len(ids)==1 else None
            prior=history[history.player_id.eq(r['sourcePlayerId'])];r['priorReturnAttempts']=float((prior.punt_returns+prior.kickoff_returns).mean()) if len(prior) else 0
        identity_seed=int.from_bytes(hashlib.sha256((str(season)+':'+str(week)+':'+g['game_id']).encode()).digest()[:8],'big')
        sim=simulate(pool,players,teams,draws,identity_seed);alignment=None
        if align:sim,alignment=align_moments(sim,players,teams,identity_seed+1)
        box=sim['box'];values=sim['scores'];all_players+=players
        artifact=hashlib.sha256(g['game_id'].encode()).hexdigest()[:16]+'.npz'
        np.savez_compressed(output/artifact,box=box,scores=values,player_ids=np.array([p['id'] for p in players]),player_teams=np.array([p['Team'] for p in players]),teams=np.array(teams),dst_scores=sim['dstScores'],**{'dst_'+k:v for k,v in sim['dstEvents'].items()},**{'unmodeled_'+k:v for k,v in sim['unmodeled'].items()},**{'scoring_'+k:v for k,v in sim['scoringEvents'].items()})
        game_checks.append(dict(drawArtifact=artifact,drawArtifactHash=hashlib.sha256((output/artifact).read_bytes()).hexdigest(),game=g['game_id'],teams=teams,momentAlignment=alignment,**sim['checks'],effectiveTemplates=sim['effectiveTemplates'],unmodeledMean={k:v.mean(axis=0).tolist() for k,v in sim['unmodeled'].items()}))
        for side,team in enumerate(teams):score_vectors['DST:'+team]=sim['dstScores'][:,side].tolist()
        for i,r in enumerate(players):
            scores=values[:,i];score_vectors[r['id']]=scores.tolist();means=box[:,i,:].mean(axis=0);anchor=r['PPR']+r['INT']
            summaries.append(dict(id=r['id'],name=r['Player'],team=r['Team'],position=r['Position'],sourceCoreDK=anchor,mean=float(scores.mean()),median=float(np.median(scores)),p10=float(np.quantile(scores,.1)),p90=float(np.quantile(scores,.9)),meanStats=dict(zip(FIELDS,means.tolist()))))
            actual=observed[observed.player_id.eq(r['sourcePlayerId'])&observed.team.eq(r['Team'])&observed.opponent_team.eq(r['Opponent'])]
            if len(actual)==1:
                try:
                    points=event.actual_score(actual.iloc[0].to_dict());results.append(dict(id=r['id'],game=g['game_id'],actual=points,mean=float(scores.mean()),error=float(scores.mean()-points),inside80=bool(np.quantile(scores,.1)<=points<=np.quantile(scores,.9))))
                except ValueError as error:excluded.append(dict(player=r['id'],reason=str(error)))
            else:excluded.append(dict(player=r['id'],reason='No unique final recorded actual; not assumed zero/DNP'))
            if r['Position']=='QB' and r['Pass_Att']>0:
                a=scores;b=sim['dstScores'][:,1-teams.index(r['Team'])];correlations.append(dict(player=r['id'],opposingDST=teams[1-teams.index(r['Team'])],correlation=float(np.corrcoef(a,b)[0,1]) if a.std()>0 and b.std()>0 else None))
    report=dict(schemaVersion=1,kind='joint-research',sport='NFL',scoring='DraftKings',joint=True,draws=draws,publishApproved=False,generatedAt=datetime.now(timezone.utc).isoformat(),sourceForecastCapturedAt=captured,season=season,week=week,simulatorHash=SIMULATOR_HASH,hashes={label:hashlib.sha256(p.read_bytes()).hexdigest() for label,p in [('forecast',forecast),('pbp',pbp),('stats',stats),('schedule',schedule)]},policy='rr-context-weighted-whole-game-replay-v1'+('-moment-aligned' if align else ''),sourceInputsUnchanged=True,gameChecks=game_checks,players=summaries,scores=score_vectors,metrics=dict(n=len(results),games=len({r['game'] for r in results}),meanDKMAE=float(np.mean([abs(r['error']) for r in results])) if results else None,meanDKBias=float(np.mean([r['error'] for r in results])) if results else None,middle80Coverage=float(np.mean([r['inside80'] for r in results])) if results else None),actualRows=results,correlations=correlations,excluded=excluded,limitations=['Experimental historical-game replay, not a possession/field-position simulator or a release-approved model.','Optional moment alignment resamples whole game outcomes toward source stat expectations with a fixed regularizer; receiving TD targets are normalized to passing TD totals and all changes are disclosed. This is not probability calibration.',
        'Historical game templates are reweighted by RR team opportunity/yardage/TD context; players receive roles using unchanged RR opportunity shares. Individual source means are not guaranteed to match; source forecasts are never overwritten.','All players and both DSTs in each game share the same replayed events; different games are independent. This is not the former independent DST bootstrap policy.','Some return/fumble/recovery events have no supported modeled player and are retained explicitly as unmodeled team events, never silently imputed to a named player.','No verified active roster, DNP probabilities, current salary replay, contest settlement or profitability is established. Played-observation backtest only; missing records are not zeroes.','Retrospective exploratory reconstruction using corrected historical provider data. An untouched prospective test is still required.'])
    (output/'joint-research.json').write_text(json.dumps(report,allow_nan=False,separators=(',',':'))+'\n');print(json.dumps(dict(games=len(game_checks),players=len(summaries),scoreVectors=len(score_vectors),metrics=report['metrics'],correlations=correlations),indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['forecast','pbp','stats','schedule','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--align-moments',action='store_true')
    p.add_argument('--season',type=int,required=True);p.add_argument('--week',type=int,required=True);p.add_argument('--captured-at',required=True)
    a=p.parse_args();run(a.forecast,a.pbp,a.stats,a.schedule,a.season,a.week,a.captured_at,a.output,align=a.align_moments)
