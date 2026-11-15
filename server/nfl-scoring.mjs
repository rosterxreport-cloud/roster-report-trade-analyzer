import {fail} from './domain.mjs';
const statFields=['Pass_Att','Pass_Yds','Pass_TD','INT','Rush_Att','Rush_Yds','Rush_TD','Targets','Receptions','Rec_Yds','Rec_TD'];
const eventFields=['Fumbles_Lost','Two_Point_Conversions','Return_TD','Offensive_Fumble_Recovery_TD'];
const bonusFields=['Pass_300_Probability','Rush_100_Probability','Rec_100_Probability'];
// Inputs must come from the RR model's own opportunity/event distributions.
// This adapter never estimates probabilities from a point yardage projection.
export function scoreNFLProjection(row){
 if(!['QB','RB','WR','TE'].includes(row.Position))fail(400,'This scoring adapter requires an offensive player; DST needs its own modeled events.');
 const missing=[...statFields,...eventFields,...bonusFields].filter(k=>!Number.isFinite(row[k]));
 if(missing.length)fail(400,'Missing modeled DraftKings inputs: '+missing.join(', '));
 if([...statFields.filter(k=>!k.endsWith('_Yds')),...eventFields].some(k=>row[k]<0)||bonusFields.some(k=>row[k]<0||row[k]>1)||row.Receptions>row.Targets+.01)fail(400,'Invalid modeled event counts, bonus probabilities or target budget.');
 if((row.Pass_Att===0&&(row.Pass_300_Probability!==0||row.Pass_TD!==0||row.INT!==0||row.Pass_Yds!==0))||(row.Rush_Att===0&&(row.Rush_100_Probability!==0||row.Rush_Yds!==0||row.Rush_TD!==0))||(row.Targets===0&&(row.Rec_100_Probability!==0||row.Receptions!==0||row.Rec_Yds!==0||row.Rec_TD!==0)))fail(400,'Modeled production conflicts with zero opportunity.');
 const components={passing:.04*row.Pass_Yds+4*row.Pass_TD-row.INT,rushing:.1*row.Rush_Yds+6*row.Rush_TD,receiving:row.Receptions+.1*row.Rec_Yds+6*row.Rec_TD,turnovers:-row.Fumbles_Lost,conversions:2*row.Two_Point_Conversions,otherTouchdowns:6*(row.Return_TD+row.Offensive_Fumble_Recovery_TD),yardageBonuses:3*(row.Pass_300_Probability+row.Rush_100_Probability+row.Rec_100_Probability)};
 return {scoring:'DraftKings',projection:Object.values(components).reduce((a,b)=>a+b,0),components,publishApproved:false};
}
