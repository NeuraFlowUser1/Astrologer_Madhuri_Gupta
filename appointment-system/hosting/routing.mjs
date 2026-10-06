/** Project-contained host guard. No customer data or database access. */
import {createHash,createHmac,randomBytes,timingSafeEqual} from 'node:crypto';
import {facts} from '../worker/installation.mjs';
import {canonical,checkedSnapshot} from '../worker/service-state.mjs';
import {classify,normalizedPath,within} from './surface-policy.mjs';

const headers={'cache-control':'private, no-store','x-content-type-options':'nosniff',
 'referrer-policy':'no-referrer','x-vercel-enable-rewrite-caching':'0'};
const absent=()=>new Response('Page not found',{status:404,headers:{...headers,'x-robots-tag':'noindex, nofollow'}});
const object=value=>value && typeof value==='object' && !Array.isArray(value);
const names=(value,expected)=>object(value) && Object.keys(value).sort().join(',')===expected.split(',').sort().join(',');
const envFor=project=>({BOOKING_INSTALLATION_ID:project.installation_id,BOOKING_PROJECT_ID:project.project_id,
 BOOKING_ENVIRONMENT:project.environment,BOOKING_PUBLIC_ORIGIN:project.origin});

export function checkedProjection(value,nonce,secret,now,project){
 const env=envFor(project),declared=facts(env);
 if(!names(value,'version,installation_id,project,environment,purpose,operation_id,issued_at_ms,published_at_ms,snapshot,snapshot_hash,reconcile_pending,nonce,signature')
   || value.version!==1 || value.installation_id!==declared.installation_id || value.project!==declared.project
   || value.environment!==declared.environment || value.purpose!=='read' || value.operation_id!==null
   || value.nonce!==nonce || value.reconcile_pending!==false || !Number.isSafeInteger(value.issued_at_ms)
   || Math.abs(now-value.issued_at_ms)>60000 || !Number.isSafeInteger(value.published_at_ms)
   || value.published_at_ms<=0 || value.published_at_ms>value.issued_at_ms
   || typeof value.signature!=='string' || !/^[a-f0-9]{64}$/.test(value.signature))throw Error('state_invalid');
 const state=checkedSnapshot(value.snapshot,env);
 if(value.snapshot_hash!==createHash('sha256').update(canonical(state)).digest('hex'))throw Error('state_invalid');
 const {signature,...unsigned}=value;
 const expected=createHmac('sha256',secret).update(`booking-product:${declared.installation_id}:${declared.environment}:v1:read:`+canonical(unsigned)).digest();
 if(!timingSafeEqual(expected,Buffer.from(signature,'hex')))throw Error('state_invalid');
 return state;
}

export async function readProjection(project,{fetcher=fetch,environment=process.env,now=Date.now,nonce=randomBytes(32).toString('hex')}={}){
 const encoded=environment.BOOKING_CONTROL_READ_KEY;
 if(typeof encoded!=='string' || !/^[A-Za-z0-9_-]{43}=$/.test(encoded) || !/^[a-f0-9]{64}$/.test(nonce))throw Error('state_configuration');
 const secret=Buffer.from(encoded,'base64url');
 if(secret.length!==32 || secret.toString('base64url')+'='!==encoded)throw Error('state_configuration');
 const controller=new AbortController();let timer,reader;
 try{
  return await Promise.race([(async()=>{
   const reply=await fetcher(project.worker.origin+'/service-state',{method:'GET',redirect:'error',cache:'no-store',
    signal:controller.signal,headers:{'X-Booking-State-Nonce':nonce}});
   if(reply.status!==200 || reply.headers.get('content-type')?.split(';')[0].trim()!=='application/json' || !reply.body)throw Error('state_invalid');
   reader=reply.body.getReader();const chunks=[];let length=0;
   while(true){const {done,value}=await reader.read();if(done)break;
    length+=value.byteLength;if(length>4096)throw Error('state_invalid');chunks.push(value);}
   const value=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(Buffer.concat(chunks)));
   checkedProjection(value,nonce,secret,now(),project);return value;
  })(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('state_unavailable')),2000);})]);
 }finally{clearTimeout(timer);controller.abort();if(reader)void reader.cancel().catch(()=>{});}
}

export function checkedManifest(manifest,project){
 facts(envFor(project));
 if(!names(manifest,'version,installation_id,public_paths,booking_paths,backend_paths,assets') || manifest.version!==1
   || manifest.installation_id!==project.installation_id || !object(manifest.assets))throw Error('surface_manifest_invalid');
 const seen=new Set();
 for(const group of ['public_paths','booking_paths','backend_paths']){
  if(!Array.isArray(manifest[group]) || manifest[group].length>1000)throw Error('surface_manifest_invalid');
  for(const path of manifest[group]){
   if(normalizedPath(path)!==path || seen.has(path))throw Error('surface_manifest_invalid');seen.add(path);
   if(group==='booking_paths' && classify(path,project.surfaces)!=='booking')throw Error('surface_manifest_invalid');
   if(group==='public_paths' && !['general','enquiry'].includes(classify(path,project.surfaces)))throw Error('surface_manifest_invalid');
  }
 }
 const assetNames=new Set();
 for(const [path,kind] of Object.entries(manifest.assets)){
  const normalized=normalizedPath(path),classification=classify(path,project.surfaces);
  const standalonePage=(/^\/google[a-f0-9]+\.html$/.test(path) || path==='/404.html') && kind==='general';
  if(path.replaceAll('//','/')!==path || path.endsWith('/') || !['booking','general'].includes(kind)
    || assetNames.has(normalized) || within(normalized,'/__booking_display') || (!standalonePage && normalized!==path.toLowerCase())
    || seen.has(normalized) || !['booking','general','enquiry'].includes(classification)
    || normalized==='/api' || within(normalized,'/api'))throw Error('surface_manifest_invalid');
  if(classification==='booking' && kind!=='booking')throw Error('surface_manifest_invalid');
  assetNames.add(normalized);
 }
 if(!Array.isArray(project.aliases) || new Set(project.aliases).size!==project.aliases.length)throw Error('surface_manifest_invalid');
 for(const origin of [project.origin,project.worker.origin,...project.aliases]){
  const parsed=new URL(origin);
  if(parsed.origin!==origin || parsed.username || parsed.password || parsed.protocol!=='https:')throw Error('surface_manifest_invalid');
 }
 return structuredClone(manifest);
}

// next/rewrite are supplied by the tiny host wrapper, keeping this module
// usable outside Vercel without a second implementation of booking logic.
export function createRouting({project,manifest,next,rewrite,...options}){
 project=structuredClone(project);manifest=checkedManifest(manifest,project);
 const hosts=new Set([project.origin,...project.aliases].map(origin=>new URL(origin).host));
 const assets=Object.fromEntries(Object.entries(manifest.assets).map(([path,kind])=>[normalizedPath(path),kind]));
 return async request=>{
  const url=new URL(request.url);let path,kind;
  if(!hosts.has(url.host))return new Response('This website address is unavailable',{status:421,headers});
  try{path=normalizedPath(decodeURIComponent(url.pathname));kind=classify(path,project.surfaces);}catch{return absent();}
  if(within(path,'/__booking_display') || path==='/booking-display-manifest.json')return absent();
  if(path==='/api/service-state' || path==='/api/service-state/probe'){
   const probe=path.endsWith('/probe'),nonce=request.headers.get('x-booking-state-nonce');
   if(!['GET','HEAD'].includes(request.method) || url.search || (probe && !/^[a-f0-9]{64}$/.test(nonce || '')))
    return Response.json({code:'invalid_state_request'},{status:400,headers});
   try{
    const value=await readProjection(project,{...options,...(probe?{nonce}:{})});
    return new Response(request.method==='HEAD'?null:JSON.stringify(probe?value:{enabled:value.snapshot.enabled,activation_epoch:value.snapshot.activation_epoch}),
     {headers:{...headers,'content-type':'application/json'}});
   }catch{return Response.json({code:'state_unavailable',enabled:false},{status:503,headers});}
  }
  const asset=Object.hasOwn(assets,path)?assets[path]:undefined;
  if(asset==='booking')kind='booking';
  if(kind==='booking'){
   try{if((await readProjection(project,options)).snapshot.enabled!==true)return absent();}catch{return absent();}
  }
  if(kind==='private' || ['company','provider','worker'].includes(kind) || path==='/api' || within(path,'/api')
    || manifest.backend_paths.includes(path))return next({headers});
  if(!['GET','HEAD'].includes(request.method))return absent();
  if(asset)return next(asset==='booking'?{headers}:{});
  if(manifest.booking_paths.includes(path)){
   return rewrite(new URL('/__booking_display/on'+path+'.html',url),{headers:{...headers,'x-robots-tag':'noindex, nofollow'}});
  }
  if(path!=='/sitemap.xml' && !manifest.public_paths.includes(path))return absent();
  let enabled=false;try{enabled=(await readProjection(project,options)).snapshot.enabled===true;}catch{}
  const target=new URL('/__booking_display/'+(enabled?'on':'off')+(path==='/'?'/index.html':path==='/sitemap.xml'?path:path+'.html'),url);
  return rewrite(target,{headers});
 };
}
