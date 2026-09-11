const SCORING_DEFAULTS=Object.freeze({passTd:4,passYard:.04,rushTd:6,receiveTd:6,longTdBonus:0,longTdThreshold:40,rushFirstDown:0,receiveFirstDown:0,tePremium:0});
const SCORING_LIMITS={passTd:[0,10],passYard:[0,.1],rushTd:[0,12],receiveTd:[0,12],longTdBonus:[0,20],rushFirstDown:[0,3],receiveFirstDown:[0,3],tePremium:[0,3]};
function normalizeScoringSettings(value){
  const result={...SCORING_DEFAULTS};
  for(const [key,[min,max]] of Object.entries(SCORING_LIMITS)){
    const n=Number(value?.[key]);if(Number.isFinite(n))result[key]=Math.min(max,Math.max(min,n));
  }
  result.longTdThreshold=Number(value?.longTdThreshold)===50?50:40;
  return result;
}
function customScoringActive(settings){
  const s=normalizeScoringSettings(settings);
  return Object.keys(SCORING_DEFAULTS).some(k=>s[k]!==SCORING_DEFAULTS[k]);
}
function applyCustomScoring(list,profiles,settings){
  const s=normalizeScoringSettings(settings);
  if(!customScoringActive(s))return list;
  const finite=(p,k)=>Number.isFinite(Number(p?.[k]))?Number(p[k]):null;
  return list.map(player=>{
    const profile=profiles?.[player.name];let delta=0,used=false;
    const add=(field,change)=>{const stat=finite(profile,field);if(stat!==null&&change!==0){delta+=stat*change;used=true;}};
    add('passingYards',s.passYard-SCORING_DEFAULTS.passYard);add('passingTds',s.passTd-SCORING_DEFAULTS.passTd);
    add('rushingTds',s.rushTd-SCORING_DEFAULTS.rushTd);add('receivingTds',s.receiveTd-SCORING_DEFAULTS.receiveTd);
    add('rushingFirstDowns',s.rushFirstDown);add('receivingFirstDowns',s.receiveFirstDown);
    if(player.pos==='TE')add('receptions',s.tePremium);
    if(s.longTdBonus) add(s.longTdThreshold===50?'longTds50':'longTds40',s.longTdBonus);
    const baseline=finite(profile,'baselinePoints');
    const impact=used&&baseline>0?Math.max(-.10,Math.min(.10,(delta/baseline)*.45)):0;
    return {...player,scoringBaseRank:player.rank,scoringBaseValue:player.value,customScoringImpact:impact,value:Math.round(player.value*(1+impact)*100)/100};
  }).sort((a,b)=>b.value-a.value||(a.scoringBaseRank??a.rank)-(b.scoringBaseRank??b.rank)).map((p,i)=>({...p,rank:i+1}));
}
