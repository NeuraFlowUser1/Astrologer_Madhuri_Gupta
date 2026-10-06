import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,readFileSync,existsSync,rmSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {startWhenBookingOn} from '../browser/conditional-work.mjs';
import {generateModes} from '../tools/build/page-modes.mjs';
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test('optional browser work loads only ON and a delayed import cannot start after OFF',async()=>{
 let enabled=false,listener,loads=0,starts=0,stops=0,release;
 const state={getSnapshot:()=>({enabled}),subscribe:callback=>{listener=callback;return()=>listener=null;}};
 const cleanup=startWhenBookingOn(()=>{++loads;return new Promise(resolve=>release=resolve);},{state});
 assert.equal(loads,0);enabled=true;listener();await tick();assert.equal(loads,1);
 enabled=false;listener();release(()=>{++starts;return()=>++stops;});await tick();assert.equal(starts,0);
 enabled=true;listener();await tick();release(()=>{++starts;return()=>++stops;});await tick();assert.equal(starts,1);
 listener();assert.equal(starts,1);enabled=false;listener();assert.equal(stops,1);cleanup();assert.equal(listener,null);
});

test('failed optional imports do not disrupt the general site and can retry on a later check',async()=>{
 let listener,attempts=0,starts=0;
 const state={getSnapshot:()=>({enabled:true}),subscribe:callback=>{listener=callback;return()=>listener=null;}};
 const cleanup=startWhenBookingOn(async()=>{if(++attempts===1)throw Error('chunk unavailable');return()=>{++starts;return()=>{};};},{state});
 await tick();assert.equal(starts,0);listener();await tick();assert.equal(starts,1);cleanup();
});

test('generated OFF pages and sitemap have no saved-receipt script or private booking listing',()=>{
 const dist=mkdtempSync(join(tmpdir(),'abs-display-build-'));
 const project={installation_id:'891d05ec-8ab2-4a87-b537-1c30f2b694b6',project_id:'practice',environment:'test',
  origin:'https://practice.example.test',aliases:[],worker:{origin:'https://worker.example.test'},surfaces:[{path:'/',class:'general'}]};
 const manifest={version:1,installation_id:project.installation_id,public_paths:['/','/contact'],
  booking_paths:['/booking','/booking/receipt'],backend_paths:['/studio'],assets:{}};
 const shell='<!doctype html><html><head><title>Original</title><meta name="description" content="Original"><meta property="og:title" content="Original"><meta name="robots" content="index"><link rel="canonical" href="https://original.example"></head><body><div id="root"></div><script type="module" src="/assets/site.js"></script></body></html>';
 try{
  generateModes({dist,shell,project,manifest,pages:{'/':['Practice','Book online.'],'/contact':['Contact','Get in touch.']},brand:'Practice & Care',offDescriptions:{'/':'Call the practice.'}});
  const off=readFileSync(join(dist,'index.html'),'utf8');assert.ok(off.includes('Call the practice.'));assert.ok(!off.includes('Book online.'));
  assert.ok(off.includes('Practice &amp; Care'));assert.ok(off.includes('booking-display-mode" content="off'));
  const on=readFileSync(join(dist,'__booking_display/on/index.html'),'utf8');assert.ok(on.includes('Book online.'));
  const absent=readFileSync(join(dist,'booking/receipt.html'),'utf8');assert.ok(!absent.includes('<script'));assert.ok(!absent.includes('sessionStorage'));
  assert.ok(readFileSync(join(dist,'__booking_display/on/booking/receipt.html'),'utf8').includes('noindex, nofollow'));
  for(const mode of ['on','off'])assert.ok(!readFileSync(join(dist,'__booking_display',mode,'sitemap.xml'),'utf8').includes('/booking/receipt'));
  assert.ok(!readFileSync(join(dist,'sitemap.xml'),'utf8').includes('/booking'));
  assert.equal(existsSync(join(dist,'__booking_display/off/booking.html')),false);
  assert.throws(()=>generateModes({dist,shell,project,manifest,pages:{},brand:'Practice'}));
 }finally{rmSync(dist,{recursive:true,force:true});}
});
