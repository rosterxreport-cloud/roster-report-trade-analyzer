export const columns=[['Pass_Att','Pass att'],['Pass_Yds','Pass yds'],['Pass_TD','Pass TD'],['INT','INT'],['Rush_Att','Carries'],['Rush_Yds','Rush yds'],['Rush_TD','Rush TD'],['Targets','Targets'],['Receptions','Catches'],['Rec_Yds','Rec yds'],['Rec_TD','Rec TD']];
export function points(p,format='ppr',passTD=4){return p[{ppr:'PPR',half:'Half_PPR',standard:'Standard'}[format]||'PPR']+(p.Position==='QB'?(Number(passTD)-4)*p.Pass_TD:0);}
export function selectPlayers(players,{search='',position='',team='',format='ppr',passTD=4,sort='points',direction='desc'}={}){
 const q=search.trim().toLowerCase();return players.filter(p=>(!position||p.Position===position)&&(!team||p.Team===team)&&(!q||`${p.Player} ${p.Team} ${p.Opponent}`.toLowerCase().includes(q))).slice().sort((a,b)=>{
 const av=sort==='points'?points(a,format,passTD):a[sort],bv=sort==='points'?points(b,format,passTD):b[sort];
 const cmp=typeof av==='number'?av-bv:String(av).localeCompare(String(bv));return (direction==='asc'?cmp:-cmp)||a.Player.localeCompare(b.Player);
 });
}
export function pageRows(rows,page,size){return rows.slice((page-1)*size,page*size);}
export function statline(p){const n=k=>Number(p[k]).toFixed(2);const rush=`${n('Rush_Att')} carries · ${n('Rush_Yds')} rush yds · ${n('Rush_TD')} rush TD`;return p.Position==='QB'?`${n('Pass_Att')} att · ${n('Pass_Yds')} pass yds · ${n('Pass_TD')} pass TD · ${n('INT')} INT\n${rush}`:`${rush}\n${n('Targets')} targets · ${n('Receptions')} catches · ${n('Rec_Yds')} rec yds · ${n('Rec_TD')} rec TD`;}
