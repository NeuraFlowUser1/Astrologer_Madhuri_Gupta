/** TEST ONLY. Serves the actual compiled app on loopback with synthetic contracts.
 * No provider proxies, credentials, payment SDK, live writes or second UI. */
import {createServer} from 'node:http';
import {readFile,stat} from 'node:fs/promises';
import {resolve,extname,sep} from 'node:path';
import {syntheticResponses} from './synthetic-responses.mjs';
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json','.svg':'image/svg+xml','.avif':'image/avif','.webp':'image/webp','.jpeg':'image/jpeg','.png':'image/png','.woff2':'font/woff2','.ttf':'font/ttf'};
export async function startReview({port=0,otp=false,mode='on',distRoot=resolve(import.meta.dirname,'../../dist')}={}){
 const dist=resolve(distRoot);
 const {respond}=syntheticResponses({otp,mode}),calls=[];
 const server=createServer(async(req,res)=>{
  res.setHeader('cache-control','no-store');res.setHeader('x-robots-tag','noindex, nofollow');
  try{
   const url=new URL(req.url,'http://127.0.0.1');
   if(url.pathname.startsWith('/api/')){
    let input='';for await(const chunk of req){input+=chunk;if(input.length>16384){res.writeHead(413);res.end();return;}}
    const body=input?JSON.parse(input):{},reply=respond(url,req.method,body);calls.push({path:url.pathname,method:req.method});
    res.writeHead(reply.status,{'content-type':'application/json'});res.end(JSON.stringify(reply.value));return;
   }
   if(!['GET','HEAD'].includes(req.method)){res.writeHead(405);res.end();return;}
   if(/^\/(company|studio|enquiries-studio|appointment-system)(\/|$)/.test(url.pathname)){res.writeHead(404);res.end('Not part of this isolated public review.');return;}
   let file=resolve(dist,'.'+decodeURIComponent(url.pathname));if(file!==dist&&!file.startsWith(dist+sep)){res.writeHead(403);res.end();return;}
   try{if(!(await stat(file)).isFile())file=resolve(dist,'index.html');}catch{if(extname(file)){res.writeHead(404);res.end();return;}file=resolve(dist,'index.html');}
   let bytes=await readFile(file);if(extname(file)==='.html')bytes=Buffer.from(bytes.toString().replace(/<body([^>]*)>/,'<body$1><div data-synthetic-review style="position:relative;z-index:100;background:#183d31;color:#fff;padding:10px 16px;text-align:center;font:14px/1.5 system-ui">LOCAL DESIGN REVIEW · Synthetic appointments only · No payment or email is sent · Test email code: 123456</div>'));
   // Self-only business connections. The confirmed public map may load in its own frame.
   res.setHeader('content-security-policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data:; font-src 'self' https://fonts.gstatic.com; connect-src 'self'; frame-src https://www.google.com https://maps.google.com; object-src 'none'; base-uri 'self'; form-action 'self'");
   res.writeHead(200,{'content-type':mime[extname(file)]||'application/octet-stream'});res.end(req.method==='HEAD'?undefined:bytes);
  }catch{res.writeHead(400,{'content-type':'application/json'});res.end(JSON.stringify({code:'synthetic_invalid_request'}));}
 });
 await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(port,'127.0.0.1',resolve);});
 return {origin:'http://127.0.0.1:'+server.address().port,calls,close:()=>new Promise(resolve=>server.close(resolve))};
}
if(process.argv[1]===import.meta.filename){const proof=await startReview({port:Number(process.env.SARSA_REVIEW_PORT||8868),otp:process.argv.includes('--otp'),mode:process.argv.includes('--off')?'off':'on'});console.log('Actual-app isolated review: '+proof.origin);}
