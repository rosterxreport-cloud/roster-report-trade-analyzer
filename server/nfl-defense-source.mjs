import crypto from 'node:crypto';
const plain=s=>s.replace(/<[^>]+>/g,'').replace(/&amp;/g,'&').replace(/&#39;/g,"'").replace(/&nbsp;/g,' ').trim();
export function parseDefenses(html,capturedAt=new Date().toISOString()){
 const title=plain(html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i)?.[1]||'');
 const metadata=title.match(/(20\d{2})\s+Week\s+(\d+)/i);
 const section=html.match(/<h2\s+id=["']dst["'][^>]*>[\s\S]*?<tbody>([\s\S]*?)<\/tbody>/i);
 if(!metadata||!section)throw Error('Current defense source schema is unavailable.');
 const players=[];
 for(const row of section[1].matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/gi)){
  const cells=[...row[1].matchAll(/<td[^>]*>([\s\S]*?)<\/td>/gi)].map(x=>plain(x[1]));
  if(cells.length!==9||!Number.isFinite(Number(cells[5]))||Number(cells[5])<0)throw Error('Invalid defense source row.');
  const team=({NO:'NO',WSH:'WAS',LA:'LAR'})[cells[1]]||cells[1],opponent=({WSH:'WAS',LA:'LAR'})[cells[2]]||cells[2];
  players.push({name:cells[0]+' DST',team,opponent,projection:Number(cells[5])});
 }
 if(players.length<4||new Set(players.map(p=>p.team)).size!==players.length)throw Error('Incomplete defense source.');
 return {season:Number(metadata[1]),week:Number(metadata[2]),capturedAt,source:'https://dfsroto.win/projections',sourceHash:crypto.createHash('sha256').update(html).digest('hex'),players};
}
