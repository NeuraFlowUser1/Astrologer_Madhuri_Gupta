/** Local routing regression check. Synthetic signed state; no network or secrets. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash,createHmac,randomUUID} from 'node:crypto';
import {resolve} from 'node:path';
import {createRouting} from '../../../appointment-system/hosting/routing.mjs';
import {canonical} from '../../../appointment-system/worker/service-state.mjs';

const root=resolve(import.meta.dirname,'../../..');
const config=JSON.parse(readFileSync(resolve(root,'vercel.json'),'utf8'));
const installed=JSON.parse(readFileSync(resolve(root,'appointment-settings/project.json'),'utf8'));
const manifest=JSON.parse(readFileSync(resolve(root,'frontend/dist/appointment-surface-manifest.json'),'utf8'));
// This fixture cannot contact the real installation. Its signing key is test-only.
const project={...installed,origin:'https://routing.example.test',aliases:[],environment:'test',
 installation_id:randomUUID(),worker:{origin:'https://worker.example.test'}};
manifest.installation_id=project.installation_id;
const key=Buffer.alloc(32,19),now=1791808800000,results=[];
const snapshot=enabled=>({version:1,installation_id:project.installation_id,project:project.project_id,
 environment:project.environment,origin:project.origin,enabled,restore_generation:randomUUID(),
 generation_sequence:'1',revision:'1',activation_epoch:randomUUID()});
function routing(enabled){
 const state=snapshot(enabled===true);let forwarded=0,reads=0;
 const route=createRouting({project,manifest,now:()=>now,
  environment:{BOOKING_CONTROL_READ_KEY:key.toString('base64url')+'='},
  fetcher:async(url,options)=>{
   reads++;assert.equal(url,project.worker.origin+'/service-state');
   if(enabled==='unknown')throw Error('synthetic state outage');
   const value={version:1,installation_id:project.installation_id,project:project.project_id,
    environment:project.environment,purpose:'read',operation_id:null,issued_at_ms:now,
    published_at_ms:now-1000,snapshot:state,snapshot_hash:createHash('sha256').update(canonical(state)).digest('hex'),
    reconcile_pending:false,nonce:options.headers['X-Booking-State-Nonce']};
   return Response.json({...value,signature:createHmac('sha256',key)
    .update(`booking-product:${project.installation_id}:${project.environment}:v1:read:`+canonical(value)).digest('hex')});
  },next:()=>{forwarded++;return new Response('existing backend');},rewrite:()=>{throw Error('Unexpected page rewrite');}});
 return {route,counts:()=>({forwarded,reads})};
}
for(const enabled of [true,false,'unknown']){
 const {route,counts}=routing(enabled);
 for(const path of ['/studio','/studio/calendar','/studio/calendar/']){
  const reply=await route(new Request(project.origin+path));
  assert.equal(reply.status,enabled===true?200:404,`${path}, booking ${enabled}`);
  assert.equal(await reply.text(),enabled===true?'existing backend':'Page not found');
 }
 assert.deepEqual(counts(),{forwarded:enabled===true?3:0,reads:3});
 results.push({booking:enabled,aliases:3,result:'passed'});
}
for(const path of ['/studio/calendar','/studio/calendar/']){
 assert(config.rewrites.some(item=>item.source===path&&item.destination==='/api'),`Missing backend rewrite: ${path}`);
}
assert(!config.rewrites.some(item=>item.source==='/studio/:path*'),'Do not expose unknown staff addresses.');
assert(!config.redirects?.some(item=>item.source==='/testimonials'),'Legacy Testimonials redirect still hides the new page.');
results.push({hosting:'exact staff rewrites and Testimonials route',result:'passed'});
console.log(JSON.stringify({result:'passed',checks:results}));
