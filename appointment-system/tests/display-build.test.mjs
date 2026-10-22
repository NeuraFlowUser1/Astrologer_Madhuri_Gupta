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
 const state={getSnapshot:()=>({enabled,verified:true,checking:false}),subscribe:callback=>{listener=callback;return()=>listener=null;}};
 const cleanup=startWhenBookingOn(()=>{++loads;return new Promise(resolve=>release=resolve);},{state});
 assert.equal(loads,0);enabled=true;listener();await tick();assert.equal(loads,1);
 enabled=false;listener();release(()=>{++starts;return()=>++stops;});await tick();assert.equal(starts,0);
 enabled=true;listener();await tick();release(()=>{++starts;return()=>++stops;});await tick();assert.equal(starts,1);
 listener();assert.equal(starts,1);enabled=false;listener();assert.equal(stops,1);cleanup();assert.equal(listener,null);
});

test('failed optional imports do not disrupt the general site and can retry on a later check',async()=>{
 let listener,attempts=0,starts=0;
 const state={getSnapshot:()=>({enabled:true,verified:true,checking:false}),subscribe:callback=>{listener=callback;return()=>listener=null;}};
 const cleanup=startWhenBookingOn(async()=>{if(++attempts===1)throw Error('chunk unavailable');return()=>{++starts;return()=>{};};},{state});
 await tick();assert.equal(starts,0);listener();await tick();assert.equal(starts,1);cleanup();
});

test('generated OFF pages and sitemap have no saved-receipt script or private booking listing',()=>{
 const dist=mkdtempSync(join(tmpdir(),'abs-display-build-'));
 const project={installation_id:'891d05ec-8ab2-4a87-b537-1c30f2b694b6',project_id:'practice',environment:'test',
  origin:'https://practice.example.test',aliases:[],worker:{origin:'https://worker.example.test'},surfaces:[{path:'/',class:'general'},{path:'/booking-policy',class:'booking'}]};
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
  for(const mode of ['on','off'])assert.ok(!readFileSync(join(dist,'__booking_display',mode,'sitemap.xml'),'utf8').includes('/booking'));
  assert.ok(!readFileSync(join(dist,'sitemap.xml'),'utf8').includes('/booking'));
  assert.equal(existsSync(join(dist,'__booking_display/off/booking.html')),false);
  assert.throws(()=>generateModes({dist,shell,project,manifest,pages:{},brand:'Practice'}));
 }finally{rmSync(dist,{recursive:true,force:true});}
});

test('complete public rendering and exact titles retain one indexing/canonical intent in both modes',()=>{
 const dist=mkdtempSync(join(tmpdir(),'abs-display-render-'));
 const project={installation_id:'891d05ec-8ab2-4a87-b537-1c30f2b694b6',project_id:'practice',environment:'test',origin:'https://practice.example.test',aliases:[],worker:{origin:'https://worker.example.test'},surfaces:[{path:'/',class:'general'},{path:'/booking-policy',class:'booking'}]};
 const manifest={version:1,installation_id:project.installation_id,public_paths:['/'],booking_paths:['/booking','/booking-policy'],backend_paths:[],assets:{}};
 const shell='<!doctype html><html><head><title>Old</title></head><body><div id="root"></div><script type="module" src="/assets/site.js"></script></body></html>';
 try{
  const calls=[];
  generateModes({dist,shell,project,manifest,pages:{'/':{title:'Exact & complete | Practice',description:'A clear description.'}},brand:'Do not append',renderPage:input=>{
   calls.push([input.path,input.mode,input.booking]);return input.html.replace('<div id="root"></div>',input.booking?'<main><h1>Private</h1></main>':`<div id="root"><main><h1>Real page</h1><p>${input.mode}</p></main></div>`);
  }});
  assert.equal(calls.length,4);
  for(const mode of ['on','off']){
   const page=readFileSync(join(dist,'__booking_display',mode,'index.html'),'utf8');
   assert.ok(page.includes('<h1>Real page</h1>'));assert.ok(page.includes('<title>Exact &amp; complete | Practice</title>'));
   assert.ok(!page.includes('Do not append'));assert.equal((page.match(/name="robots"/g)||[]).length,1);
   assert.ok(page.includes('name="robots" content="index, follow"'));assert.ok(page.includes('rel="canonical" href="https://practice.example.test/"'));
   assert.ok(page.includes('src="/assets/site.js"'));assert.equal((page.match(/booking-display-mode/g)||[]).length,1);
   assert.ok(!readFileSync(join(dist,'__booking_display',mode,'sitemap.xml'),'utf8').includes('/booking'));
  }
  assert.throws(()=>generateModes({dist,shell,project,manifest,pages:{'/':{title:'T',description:'D'}},renderPage:()=>Promise.resolve(shell)}),/complete page/);
 }finally{rmSync(dist,{recursive:true,force:true});}
});

test('display-only ON markup cannot start protected recovery; previously verified checking can retain it',async()=>{
 let current={enabled:true,verified:false,checking:true,retained_on_epoch:null},listener,loads=0,starts=0,stops=0;
 const state={getSnapshot:()=>current,subscribe:fn=>{listener=fn;return()=>listener=null;}};
 const cleanup=startWhenBookingOn(async()=>{loads++;return()=>{starts++;return()=>stops++;};},{state});
 await tick();assert.equal(loads,0);
 current={enabled:true,verified:true,checking:false,retained_on_epoch:'verified-epoch'};listener();await tick();assert.equal(starts,1);
 current={...current,verified:false,checking:true};listener();await tick();assert.equal(stops,0);assert.equal(starts,1);
 current={enabled:false,verified:false,checking:false,retained_on_epoch:null};listener();assert.equal(stops,1);cleanup();
});


test('metadata remains single with apostrophes, quotes and repeated enforcement',()=>{
 const dist=mkdtempSync(join(tmpdir(),'abs-display-quotes-'));
 const project={installation_id:'891d05ec-8ab2-4a87-b537-1c30f2b694b6',project_id:'practice',environment:'test',origin:'https://practice.example.test',aliases:[],worker:{origin:'https://worker.example.test'},surfaces:[{path:'/',class:'general'},{path:'/booking-policy',class:'booking'}]};
 const manifest={version:1,installation_id:project.installation_id,public_paths:['/'],booking_paths:['/booking'],backend_paths:[],assets:{}};
 const shell=`<!doctype html><html><head><title>Old</title><meta name='description' content="A doctor's older text"><meta name="robots" content="index"></head><body><main></main></body></html>`;
 const title='Women’s care & questions | Practice',description=`Ask about women's health and "your next visit".`;
 try{
  generateModes({dist,shell,project,manifest,pages:{'/':{title,description}},renderPage:({html})=>html.replace('</head>',`<meta name="description" content="A second doctor's stale text"></head>`)});
  for(const mode of ['on','off']){
   const html=readFileSync(join(dist,'__booking_display',mode,'index.html'),'utf8');
   assert.equal((html.match(/name="description"/g)||[]).length,1);
   assert.ok(html.includes(`content="Ask about women's health and &quot;your next visit&quot;."`));
   assert.ok(html.includes('<title>Women’s care &amp; questions | Practice</title>'));
   assert.equal((html.match(/name="robots"/g)||[]).length,1);
   assert.equal((html.match(/rel="canonical"/g)||[]).length,1);
   assert.equal((html.match(/name="booking-display-mode"/g)||[]).length,1);
   assert.ok(!html.includes('stale text'));
  }
  const utility=readFileSync(join(dist,'__booking_display/on/booking.html'),'utf8');
  assert.equal((utility.match(/name="robots"/g)||[]).length,1);
  assert.ok(utility.includes('content="noindex, nofollow"'));
 }finally{rmSync(dist,{recursive:true,force:true});}
});
