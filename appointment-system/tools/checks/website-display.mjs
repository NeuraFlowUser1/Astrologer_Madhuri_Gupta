/** Loopback-only display proof. No application, provider credential or database is opened. */
import {createServer} from 'node:http';
import {readFileSync,lstatSync} from 'node:fs';
import {resolve,relative,extname} from 'node:path';
import {pathToFileURL} from 'node:url';
import {createHash,createHmac,randomBytes,randomUUID} from 'node:crypto';
import {createInterface} from 'node:readline';

export async function displayProof(projectRoot,siteRoot,{enabled=false,port=0}={}){
 const root=resolve(projectRoot),site=resolve(siteRoot),dist=resolve(site,'dist');
 if(site!==root && !site.startsWith(root+'/'))throw Error('Website must be inside its own project.');
 for(const path of [root,site,dist])if(lstatSync(path).isSymbolicLink())throw Error('Proof target links are forbidden.');
 const project=JSON.parse(readFileSync(resolve(root,'appointment-settings/project.json')));
 const manifest=JSON.parse(readFileSync(resolve(dist,'appointment-surface-manifest.json')));
 const {createRouting}=await import(pathToFileURL(resolve(root,'appointment-system/hosting/routing.mjs')).href);
 const {canonical}=await import(pathToFileURL(resolve(root,'appointment-system/worker/service-state.mjs')).href);
 const secret=randomBytes(32);let current=enabled,epoch=randomUUID(),reads=0;
 const fetcher=async(url,options)=>{
  if(url!==project.worker.origin+'/service-state')throw Error('Unexpected proof outbound address.');
  ++reads;const now=Date.now();
  const snapshot={version:1,installation_id:project.installation_id,project:project.project_id,environment:project.environment,
   origin:project.origin,enabled:current,restore_generation:'f6068613-815b-4f47-a280-3d341eabefb3',generation_sequence:'1',revision:'1',activation_epoch:epoch};
  const value={version:1,installation_id:project.installation_id,project:project.project_id,environment:project.environment,purpose:'read',
   operation_id:null,issued_at_ms:now,published_at_ms:now,snapshot,snapshot_hash:createHash('sha256').update(canonical(snapshot)).digest('hex'),
   reconcile_pending:false,nonce:options.headers['X-Booking-State-Nonce']};
  return Response.json({...value,signature:createHmac('sha256',secret).update(`booking-product:${project.installation_id}:${project.environment}:v1:read:`+canonical(value)).digest('hex')});
 };
 const route=createRouting({project,manifest,environment:{BOOKING_CONTROL_READ_KEY:secret.toString('base64url')+'='},fetcher,
  next:options=>new Response(null,{headers:{...options.headers,'x-proof-next':'1'}}),
  rewrite:(url,options)=>new Response(null,{headers:{...options.headers,'x-proof-rewrite':url.pathname}})});
 const types={'.html':'text/html; charset=utf-8','.js':'text/javascript','.mjs':'text/javascript','.css':'text/css',
  '.json':'application/json','.svg':'image/svg+xml','.png':'image/png','.webp':'image/webp','.jpg':'image/jpeg','.jpeg':'image/jpeg',
  '.woff2':'font/woff2','.xml':'application/xml','.txt':'text/plain','.mp4':'video/mp4'};
 const server=createServer(async(request,response)=>{
  try{
   // Only display reads are offered. The fixture cannot make a booking, send an
   // enquiry, issue a company command, or proxy an API request to either client.
   if(!['GET','HEAD'].includes(request.method)){response.writeHead(405);return response.end();}
   const incoming=new URL(request.url,project.origin);
   const guarded=await route(new Request(incoming,{method:request.method,headers:request.headers}));
   const target=guarded.headers.get('x-proof-rewrite'),passed=guarded.headers.get('x-proof-next');
   const headers=Object.fromEntries(guarded.headers);delete headers['x-proof-rewrite'];delete headers['x-proof-next'];
   if(target || passed){
    if(passed && (incoming.pathname==='/api' || incoming.pathname.startsWith('/api/') || incoming.pathname.startsWith('/company') || incoming.pathname.includes('studio'))){
     response.writeHead(503,{'content-type':'application/json','cache-control':'no-store'});
     return response.end(JSON.stringify({code:'isolated_display_proof_no_application'}));
    }
    const path=resolve(dist,'.'+decodeURIComponent(target || incoming.pathname));
    if(relative(dist,path).startsWith('..') || lstatSync(path).isSymbolicLink() || !lstatSync(path).isFile())throw Error('Invalid proof asset.');
    response.writeHead(guarded.status,{...headers,'content-type':types[extname(path)] || 'application/octet-stream'});
    return response.end(request.method==='HEAD'?undefined:readFileSync(path));
   }
   response.writeHead(guarded.status,headers);response.end(request.method==='HEAD'?undefined:Buffer.from(await guarded.arrayBuffer()));
  }catch{response.writeHead(404,{'cache-control':'no-store'});response.end('Page not found');}
 });
 await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(port,'127.0.0.1',resolve);});
 return {origin:'http://127.0.0.1:'+server.address().port,manifest,project,state:()=>({enabled:current,reads}),
  setEnabled(value){if(typeof value!=='boolean')throw Error('Boolean mode required.');current=value;epoch=randomUUID();},
  close:()=>new Promise(resolve=>server.close(resolve))};
}

if(process.argv[1] && import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
 if(process.argv[2]!=='--isolated-display-proof' || !process.argv[3] || !process.argv[4])
  throw Error('Use --isolated-display-proof PROJECT_ROOT SITE_ROOT [LOOPBACK_PORT].');
 const proof=await displayProof(process.argv[3],process.argv[4],{port:Number(process.argv[5] || 0)});
 console.log(JSON.stringify({status:'loopback-display-only',origin:proof.origin,enabled:false}));
 const input=createInterface({input:process.stdin});
 input.on('line',line=>{if(line==='on'||line==='off'){proof.setEnabled(line==='on');console.log(JSON.stringify(proof.state()));}});
 const stop=()=>{input.close();proof.close().then(()=>process.exit(0));};
 process.on('SIGINT',stop);process.on('SIGTERM',stop);
}
