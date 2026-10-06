import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));

test('the actual staff page remains hidden until fresh ON, disappears while open OFF, and recovers without stale content',
 {skip:!process.env.BOOKING_CHROME_EXECUTABLE || !process.env.BOOKING_BROWSER_NODE_MODULES},async()=>{
 const {chromium}=await import(pathToFileURL(resolve(process.env.BOOKING_BROWSER_NODE_MODULES,'playwright-core/index.mjs')).href);
 const files=new Map(),assets=resolve(root,'engine/appointment_system/studio_assets');
 for(const name of ['interface.js','calendar.js','inbox.js','appointments.js','interface.css','booking-guard.mjs'])files.set('/api/studio/'+name,resolve(assets,name));
 files.set('/api/studio/staff-actions.js',resolve(assets,'staff-actions.js'));
 files.set('/api/studio/product-state.mjs',resolve(root,'browser/product-state.mjs'));
 let enabled=false,available=true,statusReads=0;const epoch='bd01549f-d36a-4aef-ae9d-11257192d1af';
 const server=createServer(async(req,res)=>{
  const path=new URL(req.url,'http://fixture.invalid').pathname;res.setHeader('cache-control','no-store');
  if(path==='/studio'){res.setHeader('content-type','text/html');return res.end((await readFile(resolve(assets,'index.html'),'utf8')).replaceAll('{{PRACTICE_NAME}}','Synthetic Practice'));}
  if(path==='/api/service-state'){res.writeHead(available?200:503,{'content-type':'application/json'});return res.end(JSON.stringify(available?{enabled,activation_epoch:epoch}:{code:'state_unavailable'}));}
  if(path==='/api/studio/status'){statusReads++;res.writeHead(401,{'content-type':'application/json'});return res.end('{"signed_in":false}');}
  if(files.has(path)){res.setHeader('content-type',path.endsWith('.css')?'text/css':'text/javascript');const source=await readFile(files.get(path),'utf8');return res.end(source.replace('/*STAFF_BROWSER_CONFIGURATION*/null',JSON.stringify({version:1,installation_id:epoch,environment:'test',legacy:{client:[],company:[],calendar:[],inbox:[],enquiry:[]}})));}
  res.writeHead(404);res.end();
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:true,executablePath:process.env.BOOKING_CHROME_EXECUTABLE,args:['--no-sandbox']});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',route=>route.request().url().startsWith(origin+'/')?route.continue():route.abort());
  await page.goto(origin+'/studio');await page.waitForFunction(()=>window.bookingVisibility?.getSnapshot().verified);
  assert.equal(await page.locator('[data-booking-shell]').isVisible(),false);assert.equal(statusReads,0);
  enabled=true;await page.evaluate(()=>window.bookingVisibility.refresh({force:true}));await page.getByRole('button',{name:'Sign in with Google',exact:true}).waitFor();
  assert.equal(await page.locator('[data-booking-shell]').isVisible(),true);assert.equal(statusReads,1);
  enabled=false;const start=Date.now();await page.locator('[data-booking-shell]').waitFor({state:'hidden',timeout:7500});assert.ok(Date.now()-start<7500);
  assert.equal(await page.getByRole('button',{name:'Sign in with Google',exact:true}).isVisible(),false);
  enabled=true;await page.evaluate(()=>window.bookingVisibility.refresh({force:true}));await page.locator('[data-booking-shell]').waitFor({state:'visible'});
  available=false;await page.evaluate(()=>window.bookingVisibility.refresh({force:true}));assert.equal(await page.locator('[data-booking-shell]').isVisible(),false);
  available=true;await page.evaluate(()=>window.bookingVisibility.refresh({force:true}));await page.getByRole('button',{name:'Sign in with Google',exact:true}).waitFor();
  assert.deepEqual(errors,[]);await page.close();
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
});

test('the actual staff calendar recovers a dropped mutation response after reload without issuing another change',
 {skip:!process.env.BOOKING_CHROME_EXECUTABLE || !process.env.BOOKING_BROWSER_NODE_MODULES},async()=>{
 const {chromium}=await import(pathToFileURL(resolve(process.env.BOOKING_BROWSER_NODE_MODULES,'playwright-core/index.mjs')).href);
 const assets=resolve(root,'engine/appointment_system/studio_assets'),files=new Map();
 for(const name of ['interface.js','calendar.js','inbox.js','appointments.js','interface.css','booking-guard.mjs','staff-actions.js'])files.set('/api/studio/'+name,resolve(assets,name));
 files.set('/api/studio/product-state.mjs',resolve(root,'browser/product-state.mjs'));
 const epoch='bd01549f-d36a-4aef-ae9d-11257192d1af';let saved=null,writes=0,checked=0;const operationIds=new Set();
 const server=createServer(async(req,res)=>{
  const path=new URL(req.url,'http://fixture.invalid').pathname;res.setHeader('cache-control','no-store');
  if(path==='/studio'){res.setHeader('content-type','text/html');return res.end((await readFile(resolve(assets,'index.html'),'utf8')).replaceAll('{{PRACTICE_NAME}}','Synthetic Practice'));}
  if(files.has(path)){res.setHeader('content-type',path.endsWith('.css')?'text/css':'text/javascript');return res.end((await readFile(files.get(path),'utf8')).replace('/*STAFF_BROWSER_CONFIGURATION*/null',JSON.stringify({version:1,installation_id:epoch,environment:'test',legacy:{client:[],company:[],calendar:[],inbox:[],enquiry:[]}})));}
  const json=value=>{res.setHeader('content-type','application/json');res.end(JSON.stringify(value));};
  if(path==='/api/service-state')return json({enabled:true,activation_epoch:epoch});
  if(path==='/api/studio/status')return json({signed_in:true,role:'client',email:'practice@example.test',resources:[],authorization_saved:false});
  let text='';for await(const part of req)text+=part;const body=text?JSON.parse(text):{};
  if(path==='/api/studio/calendar/time-context')return json({code:'ok',timezone:'Asia/Kolkata',today:'2026-10-03'});
  if(path==='/api/studio/calendar/resolve-time')return json({code:'ok',timezone:body.timezone,local:body.local,instant:new Date(body.local+':00+05:30').toISOString()});
  if(path==='/api/studio/calendar/month'){
   const date=new Date(body.month+'T12:00:00Z'),count=new Date(Date.UTC(date.getUTCFullYear(),date.getUTCMonth()+1,0)).getUTCDate();
   return json({code:'ok',timezone:'Asia/Kolkata',month:body.month,days:Array.from({length:count},(_,i)=>({date:body.month.slice(0,8)+String(i+1).padStart(2,'0'),appointments:i===6?2:0,closures:0}))});
  }
  if(path==='/api/studio/calendar/list')return json({code:'ok',day:body.day,timezone:'Asia/Kolkata',items:[],next_cursor:null});
  if(path==='/api/studio/inbox/list')return json({code:'ok',view:body.view,items:[],next_cursor:null});
  if(path==='/api/studio/calendar/close'){writes++;operationIds.add(body.operation_id);saved=body.operation_id;return res.destroy();}
  if(path==='/api/studio/calendar/action-result'){checked++;return json({code:body.operation_id===saved?'closed':'operation_not_found',operation_id:body.operation_id});}
  res.writeHead(404);res.end();
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:true,executablePath:process.env.BOOKING_CHROME_EXECUTABLE,args:['--no-sandbox']});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',route=>route.request().url().startsWith(origin+'/')?route.continue():route.abort());
  await page.goto(origin+'/studio');await page.locator('#calendar-panel').waitFor();
  await page.waitForFunction(()=>!document.querySelector('#closure-start').disabled && !!document.querySelector('#calendar-month button'));
  await page.getByRole('button',{name:'2026-10-07: 2 appointments, 0 blocked periods',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#calendar-day').value==='2026-10-07'&&!document.querySelector('#closure-start').disabled);
  await page.locator('#closure-start').fill('2026-12-10T13:00');await page.locator('#closure-end').fill('2026-12-10T13:20');await page.locator('#closure-reason').fill('Synthetic unavailability');
  await page.locator('#calendar-close button[type=submit]').click();
  await page.waitForFunction(()=>document.querySelector('#calendar-action-status').textContent.includes('could not confirm'));
  // Chrome may retransmit an identical request after a connection reset. It
  // must retain one action identity; recovery must not submit another request.
  assert.equal(operationIds.size,1);const beforeRecovery=writes;assert.equal(await page.evaluate(()=>window.PracticeStaffActions('calendar').get().length),1);
  await page.reload();await page.locator('#calendar-repeat').waitFor();await page.locator('#calendar-repeat').click();
  await page.waitForFunction(()=>document.querySelector('#calendar-action-status').textContent.includes('Earlier changes checked'));
  assert.equal(writes,beforeRecovery);assert.equal(operationIds.size,1);assert.equal(checked,1);assert.equal(await page.evaluate(()=>window.PracticeStaffActions('calendar').get().length),0);
  assert.deepEqual(errors,[]);await page.close();
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
});
