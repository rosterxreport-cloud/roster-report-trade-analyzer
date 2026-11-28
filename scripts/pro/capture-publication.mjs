// Read-only public publication evidence. No subscriber data, credentials or login.
import fs from 'node:fs/promises';import crypto from 'node:crypto';
const directory=process.argv[2];if(!directory)throw Error('Supply an output directory.');await fs.mkdir(directory,{recursive:true});
const captures=[];
for(const [name,url] of [['home','https://rosterxreport.substack.com/'],['subscribe','https://rosterxreport.substack.com/subscribe'],['publication','https://rosterxreport.substack.com/api/v1/publication']]){
 const requestedAt=new Date().toISOString();
 try{const response=await fetch(url,{redirect:'error',signal:AbortSignal.timeout(20000)});const bytes=Buffer.from(await response.arrayBuffer());await fs.writeFile(`${directory}/${name}.response`,bytes);captures.push({name,url,requestedAt,receivedAt:new Date().toISOString(),status:response.status,contentType:response.headers.get('content-type'),bytes:bytes.length,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),unavailable:/Site Unavailable|Unable to access this site|Access denied|Just a moment/i.test(bytes.toString('utf8'))});}
 catch(error){captures.push({name,url,requestedAt,error:error.name});}
}
await fs.writeFile(`${directory}/receipts.json`,JSON.stringify({publishApproved:false,captures},null,2)+'\n');console.log(JSON.stringify(captures));
