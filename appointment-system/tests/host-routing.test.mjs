import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash,createHmac,randomUUID} from 'node:crypto';
import {canonical} from '../worker/service-state.mjs';
import {checkedManifest,checkedProjection,createRouting,readProjection} from '../hosting/routing.mjs';
import {classify,normalizedPath} from '../hosting/surface-policy.mjs';

const secret=Buffer.alloc(32,19),now=1790956800000;
const project={installation_id:'891d05ec-8ab2-4a87-b537-1c30f2b694b6',project_id:'example-practice',environment:'test',
 origin:'https://practice.example.test',aliases:['https://www.practice.example.test'],worker:{origin:'https://worker.example.test'},
 surfaces:[{path:'/',class:'general'},{path:'/booking-policy',class:'booking'},{path:'/manual-calendar',class:'booking'}]};
const manifest={version:1,installation_id:project.installation_id,public_paths:['/','/contact','/services','/privacy'],
 booking_paths:['/booking','/booking/receipt','/booking-policy'],backend_paths:['/studio','/enquiries-studio','/company'],
 assets:{'/assets/Booking-AbC123.js':'booking','/media/meeting-guide.pdf':'booking','/assets/framework-C2.js':'general',
 '/media/portrait.webp':'general','/robots.txt':'general'}};
const environment={BOOKING_CONTROL_READ_KEY:secret.toString('base64url')+'='};
const snapshot=enabled=>({version:1,installation_id:project.installation_id,project:project.project_id,environment:project.environment,
 origin:project.origin,enabled,restore_generation:randomUUID(),generation_sequence:'1',revision:'9007199254740993',activation_epoch:randomUUID()});
function signed(state,nonce,changes={}){
 const unsigned={version:1,installation_id:project.installation_id,project:project.project_id,environment:project.environment,
  purpose:'read',operation_id:null,issued_at_ms:now,published_at_ms:now-86400000,snapshot:state,
  snapshot_hash:createHash('sha256').update(canonical(state)).digest('hex'),reconcile_pending:false,nonce,...changes};
 return {...unsigned,signature:createHmac('sha256',secret).update(`booking-product:${project.installation_id}:${project.environment}:v1:read:`+canonical(unsigned)).digest('hex')};
}
function setup(enabled=true,changes={}){
 const calls=[],state=snapshot(enabled);
 const fetcher=async(url,options)=>{calls.push({url,options});return Response.json(signed(state,options.headers['X-Booking-State-Nonce']));};
 const route=createRouting({project,manifest,environment,now:()=>now,fetcher,
  next:options=>new Response('next',{headers:options.headers}),
  rewrite:(url,options)=>new Response(url.pathname,{headers:options.headers}),...changes});
 return {route,calls,state};
}
const request=(path,options={})=>new Request(project.origin+path,options);

test('host and application surface aliases are classified without receipt exceptions',()=>{
 for(const path of ['/BOOKING//receipt/','/booking.html','/booking/index.html','/STUDIO/','/api/checkout/status','/assets/appointment-system/a.js','/manual-calendar/one'])
  assert.equal(classify(path,project.surfaces),'booking',path);
 for(const path of ['/company','/api/webhooks/razorpay','/api/internal/recovery','/enquiries-studio','/api/enquiry-studio/list','/api/studio/sign-in/callback'])
  assert.equal(classify(path,project.surfaces),'private',path);
 for(const path of ['/contact','/api/contact/start','/services'])assert.equal(classify(path,project.surfaces),'general',path);
 for(const path of ['x','/a/../b','/a/./b','/a\\b','/%2f','/a?b','/a#b','/a\u0000','/a\u007f'])assert.throws(()=>normalizedPath(path));
 assert.equal(normalizedPath('/index.html'),'/');
});

test('off denies old pages, APIs, direct chunks and media regardless of receipt cookie or query',async()=>{
 const {route,calls}=setup(false);
 for(const path of ['/booking','/booking/receipt?receipt=saved','/BOOKING//receipt/','/booking.html','/booking/index.html',
  '/%62ooking','/api/checkout/status','/api/booking','/studio','/admin','/dashboard','/booking-help',
  '/booking-policy','/manual-calendar','/assets/Booking-AbC123.js?preload=1','/media/meeting-guide.pdf']){
  const reply=await route(request(path,{headers:{Cookie:'saved-receipt=old'}}));assert.equal(reply.status,404,path);
  assert.equal(reply.headers.get('cache-control'),'private, no-store');assert.equal(reply.headers.get('location'),null);
 }
 assert.equal((await route(request('/api/checkout',{method:'POST',body:'customer details'}))).status,404);
 for(const call of calls){assert.equal(call.url,'https://worker.example.test/service-state');assert.equal(call.options.method,'GET');
  assert.deepEqual(Object.keys(call.options.headers),['X-Booking-State-Nonce']);assert.equal(call.options.body,undefined);}
});

test('general assets and independently authenticated work continue without a state read',async()=>{
 const {route,calls}=setup(false);
 for(const path of ['/api/contact/start','/company','/api/company/command','/api/webhooks/razorpay','/api/internal/recovery',
  '/enquiries-studio','/api/enquiry-studio/list','/api/studio/sign-in/callback','/assets/framework-C2.js','/media/portrait.webp','/robots.txt']){
  const reply=await route(request(path));assert.equal(reply.status,200);assert.equal(await reply.text(),'next',path);
 }
 assert.equal(calls.length,0);
});

test('fresh ON permits exact booking pages and assets and does not keep a positive cache',async()=>{
 const {route,state,calls}=setup();
 assert.equal(await (await route(request('/booking'))).text(),'/__booking_display/on/booking.html');
 assert.equal(await (await route(request('/booking/receipt'))).text(),'/__booking_display/on/booking/receipt.html');
 assert.equal(await (await route(request('/assets/Booking-AbC123.js'))).text(),'next');
 assert.equal(await (await route(request('/studio'))).text(),'next');
 state.enabled=false;
 assert.equal((await route(request('/booking'))).status,404);assert.equal(calls.length,5);
 assert.equal(new Set(calls.map(call=>call.options.headers['X-Booking-State-Nonce'])).size,5);
});

test('general pages and sitemap select truthful OFF variants on projection failure',async()=>{
 const {route}=setup(true,{fetcher:async()=>{throw Error('offline');}});
 for(const [path,target] of [['/','/index.html'],['/contact','/contact.html'],['/privacy','/privacy.html'],['/sitemap.xml','/sitemap.xml']]){
  const reply=await route(request(path+'?customer=do-not-forward'));assert.equal(reply.status,200);
  assert.equal(await reply.text(),'/__booking_display/off'+target);assert.equal(reply.headers.get('cache-control'),'private, no-store');
 }
 assert.equal((await route(request('/booking'))).status,404);
 assert.equal((await route(request('/assets/framework-C2.js'))).status,200);
 assert.equal((await route(request('/contact',{method:'POST'}))).status,404);
 const on=setup();assert.equal(await (await on.route(request('/contact'))).text(),'/__booking_display/on/contact.html');
});

test('unknown hosts, internal variants, unknown legacy hashes and double encodings cannot bypass the guard',async()=>{
 const {route,calls}=setup();
 assert.equal((await route(new Request('https://foreign.example.test/booking'))).status,421);
 assert.equal((await route(new Request('https://practice.example.test:444/booking'))).status,421);
 for(const path of ['/__booking_display/on/booking.html','/__BOOKING_DISPLAY/off/index.html','/booking-display-manifest.json',
  '/assets/old-booking-hash.js','/%2562ooking','/a%5cb','/a%00b','/a%ZZ','/missing'])assert.equal((await route(request(path))).status,404,path);
 assert.equal(calls.length,0);
 assert.equal((await route(new Request('https://www.practice.example.test/contact'))).status,200);
});

test('service state exposes only display facts and probe proves the supplied nonce',async()=>{
 const {route,state}=setup();
 assert.deepEqual(await (await route(request('/api/service-state'))).json(),{enabled:true,activation_epoch:state.activation_epoch});
 const probe=await route(request('/api/service-state/probe',{headers:{'X-Booking-State-Nonce':'a'.repeat(64)}}));
 assert.equal((await probe.json()).nonce,'a'.repeat(64));
 assert.equal(await (await route(request('/api/service-state',{method:'HEAD'}))).text(),'');
 for(const [path,options] of [['/api/service-state?x=1',{}],['/api/service-state',{method:'POST'}],['/api/service-state/probe',{}]])
  assert.equal((await route(request(path,options))).status,400);
 const broken=setup(true,{environment:{}});assert.equal((await broken.route(request('/api/service-state'))).status,503);
});

test('projection rejects every altered identity, timestamp, shape and boolean substitution',()=>{
 const state=snapshot(true),nonce='a'.repeat(64),good=signed(state,nonce);
 assert.deepEqual(checkedProjection(good,nonce,secret,now,project),state);
 for(const [key,value] of Object.entries({version:true,installation_id:randomUUID(),project:'foreign',environment:'production',
  purpose:'publish-ack',operation_id:randomUUID(),nonce:'b'.repeat(64),reconcile_pending:true,issued_at_ms:now-60001,
  published_at_ms:0,signature:'0'.repeat(64),snapshot_hash:'0'.repeat(64),extra:1}))
  assert.throws(()=>checkedProjection({...good,[key]:value},nonce,secret,now,project),key);
 for(const [key,value] of Object.entries({enabled:1,revision:9007199254740993,origin:'https://foreign.example.test',activation_epoch:'00000000-0000-0000-0000-000000000000'}))
  assert.throws(()=>checkedProjection(signed({...state,[key]:value},nonce),nonce,secret,now,project),key);
});

test('projection validates key, type, byte size, UTF-8 and bounded response time',async()=>{
 for(const value of [undefined,'bad','!'.repeat(44),secret.toString('base64url')])
  await assert.rejects(readProjection(project,{environment:{BOOKING_CONTROL_READ_KEY:value}}));
 for(const reply of [new Response('redirect',{status:302}),new Response('{}'),Response.json({}),
  new Response(' '.repeat(4097),{headers:{'Content-Type':'application/json'}}),
  new Response(Uint8Array.of(0xff),{headers:{'Content-Type':'application/json'}})])
  await assert.rejects(readProjection(project,{environment,fetcher:async()=>reply}));
 await assert.rejects(readProjection(project,{environment,nonce:'invalid'}));
 const start=Date.now();await assert.rejects(readProjection(project,{environment,fetcher:()=>new Promise(()=>{})}));
 assert.ok(Date.now()-start<4000);
});

test('manifest refuses foreign installation, route conflicts, shadow assets and false general classification',()=>{
 assert.deepEqual(checkedManifest(manifest,project),manifest);
 for(const mutate of [m=>m.installation_id=randomUUID(),m=>m.extra=true,m=>m.public_paths.push('/booking'),
  m=>m.public_paths.push('/contact'),m=>m.booking_paths.push('/not-booking'),
  m=>m.assets['/assets/appointment-system/one.js']='general',m=>m.assets['/company/a.js']='general',
  m=>m.assets['/api/x.js']='general',m=>m.assets['/__booking_display/on/a.js']='general',
  m=>m.assets['/contact']='general',m=>m.assets['/assets/BOOKING-AbC123.js']='booking',
  m=>m.assets['/hidden.html']='general',m=>m.assets['/a//b']='general']){
  const copy=structuredClone(manifest);mutate(copy);assert.throws(()=>checkedManifest(copy,project));
 }
 assert.throws(()=>checkedManifest(manifest,{...project,aliases:['https://foreign.example.test/path']}));
 assert.throws(()=>checkedManifest(manifest,{...project,worker:{origin:'http://worker.example.test'}}));
});
