// Exercise the shared React bindings with the project's actual React package.
// Only the fixture owns the page controls; production modules remain unchanged.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import {installation_id,epoch,policy,availability,receipt} from './booking-browser-fixture.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
const available=Boolean(process.env.BOOKING_CHROME_EXECUTABLE&&process.env.BOOKING_BROWSER_NODE_MODULES);

test('project React mounts the contained booking and receipt hooks, updates inputs and stops them when disabled',{skip:!available},async()=>{
 const dependencies=process.env.BOOKING_BROWSER_NODE_MODULES,require=createRequire(resolve(dependencies,'fixture.cjs'));
 const {build}=await import(pathToFileURL(require.resolve('vite')).href);
 const entry=resolve(dirname(dependencies),'__abs_fixture_vendor__.mjs');
 const built=await build({root:dirname(dependencies),configFile:false,logLevel:'error',define:{'process.env.NODE_ENV':'"production"'},
  resolve:{alias:[{find:'react-dom/client',replacement:require.resolve('react-dom/client')},{find:'react',replacement:require.resolve('react')}]},
  plugins:[{name:'local-react-fixture',resolveId:id=>id===entry?'\0react-fixture':undefined,
   load:id=>id==='\0react-fixture'?"export * as React from 'react'; export {createRoot} from 'react-dom/client';":undefined}],
  build:{write:false,minify:false,lib:{entry,formats:['es'],fileName:'vendor'}}});
 const vendor=(Array.isArray(built)?built[0]:built).output.find(item=>item.type==='chunk'&&item.isEntry).code;
 const profile={version:1,installation_id,environment:'test',legacy_callbacks:[],legacy_receipts:[],payment:{name:'Synthetic Practice',description:'Synthetic appointment',color:'#123456'}};
 const calls=[],errors=[];let recovered=null;
 const document=`<!doctype html><div id="root"></div><script type="module">
  import {React,createRoot} from '/vendor.mjs';
  import {createBookingBrowser,createUseBooking} from '/browser/booking/index.mjs';
  import {createUseReceiptRecovery} from '/browser/booking/receipt-recovery.mjs';
  import {createEnquiryBrowser,createUseEnquiry} from '/browser/enquiry/index.mjs';
  let state={enabled:true,activation_epoch:${JSON.stringify(epoch)}};const subscribers=new Set();
  const product={getSnapshot:()=>state,subscribe:fn=>{subscribers.add(fn);return()=>subscribers.delete(fn);}};
  const browser=createBookingBrowser(${JSON.stringify(profile)},{product});
  const useBooking=createUseBooking(React,browser),useRecovery=createUseReceiptRecovery(React,browser);
  const useEnquiry=createUseEnquiry(React,createEnquiryBrowser({version:1,installation_id:${JSON.stringify(installation_id)},environment:'test',channels:{contact:{legacy_receipts:[]}}}));
  const root=createRoot(document.getElementById('root'));
  function Booking({service}){const value=useBooking(service);window.fixture.current=value;return React.createElement('pre',{id:'state'},JSON.stringify(value.state));}
  function Enquiry(){const value=useEnquiry();window.fixture.current=value;return React.createElement('pre',{id:'state'},JSON.stringify(value));}
  function Recovery(){const value=useRecovery();window.fixture.current=value;return React.createElement('pre',{id:'state'},JSON.stringify(value));}
  window.fixture={current:null,setService:value=>root.render(React.createElement(Booking,{service:value})),
   mode:value=>{state={...state,enabled:value};for(const fn of subscribers)fn();},
   enquiry:()=>root.render(React.createElement(Enquiry)),recovery:()=>root.render(React.createElement(Recovery)),unmount:()=>root.unmount(),subscribers:()=>subscribers.size,
   invalidConfiguration:()=>{try{createBookingBrowser({}, {product});return false;}catch{return true;}}};
  root.render(React.createElement(Booking,{service:''}));
 </script>`;
 const server=createServer(async(req,res)=>{
  try{
   const url=new URL(req.url,'http://fixture.invalid'),path=url.pathname;res.setHeader('cache-control','no-store');
   if(path==='/'){res.setHeader('content-type','text/html');return res.end(document);}
   if(path==='/vendor.mjs'){res.setHeader('content-type','text/javascript');return res.end(vendor);}
   if(/^\/browser\/(?:(?:booking|enquiry)\/)?[a-z-]+\.mjs$/.test(path)){res.setHeader('content-type','text/javascript');return res.end(await readFile(resolve(root,path.slice(1)),'utf8'));}
   let raw='';for await(const part of req)raw+=part;const body=raw?JSON.parse(raw):null;calls.push({path,body});res.setHeader('content-type','application/json');
   if(path==='/api/contact/policy')return res.end('{"version":1,"receipt_key_id":"current"}');
   if(['/api/contact/start','/api/contact/status','/api/contact/verify'].includes(path))return res.end(JSON.stringify({code:'ok',request_id:body.request_id,state:path.endsWith('verify')?'received':'awaiting_verification',generation:1,sends_remaining:2,verification_delivery:'queued',server_now:'2026-10-03T05:00:00Z',code_expires_at:'2026-10-03T05:05:00Z',resend_after:'2026-10-03T05:01:00Z'}));
   if(path==='/api/booking-policy')return res.end(JSON.stringify(policy()));
   if(path==='/api/availability')return res.end(JSON.stringify(availability()));
   if(path==='/api/checkout-context')return res.end('{"ready":true}');
   if(path==='/api/checkout/recover-receipt'){recovered=body.secret;return res.end('{"code":"receipt_restored"}');}
   if(path==='/api/checkout/status'&&req.headers['x-booking-receipt']===recovered)return res.end(JSON.stringify({...receipt(body.request_id),appointment_state:'confirmed',payment_state:'captured',captured_paise:210000}));
   res.writeHead(404);res.end('{"code":"fixture_route_missing"}');
  }catch(error){errors.push(error.message);res.destroy();}
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin='http://127.0.0.1:'+server.address().port;
 const {chromium}=await import(pathToFileURL(resolve(dependencies,'playwright-core/index.mjs')).href);
 const chrome=await chromium.launch({headless:true,executablePath:process.env.BOOKING_CHROME_EXECUTABLE,args:['--no-sandbox']});
 try{
  const context=await chrome.newContext(),page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  await context.route('**/*',route=>route.request().url().startsWith(origin+'/')?route.continue():route.abort());await page.goto(origin);
  await page.waitForFunction(()=>window.fixture?.current?.state?.slotsStatus==='ready').catch(error=>{throw new Error(error.message+'; fixture errors: '+errors.join('; '));});
  assert.equal(await page.evaluate(()=>fixture.invalidConfiguration()),true);
  await page.evaluate(()=>{fixture.setService('consultation');fixture.current.dispatch({type:'details',name:'full_name',value:'Synthetic Customer'});});
  await page.waitForFunction(()=>fixture.current.state.details.full_name==='Synthetic Customer');
  await page.evaluate(()=>fixture.current.dispatch({type:'edit',name:'day',value:'2026-10-03'}));await page.waitForFunction(()=>fixture.current.state.slotsStatus==='ready');
  await page.evaluate(()=>fixture.current.dispatch({type:'ack',value:true}));await page.waitForFunction(()=>fixture.current.state.ack===true);
  await page.evaluate(()=>fixture.current.dispatch({type:'error',message:'Synthetic report'}));await page.waitForFunction(()=>fixture.current.state.error==='Synthetic report');
  const before=calls.length;await page.evaluate(()=>fixture.mode(false));await page.evaluate(()=>fixture.current.loadPolicy());assert.equal(calls.length,before);
  await page.evaluate(()=>fixture.mode(true));await page.waitForFunction(()=>fixture.current.state.slotsStatus==='ready');
  await page.evaluate(()=>fixture.recovery());await page.waitForFunction(()=>fixture.current.restore!==undefined);
  const reference='ea79bf9a-6aac-415c-becf-d6d49af3946a';await page.evaluate(reference=>fixture.current.restore(reference,'12345678'),reference);
  await page.waitForFunction(()=>fixture.current.restored===true);assert.equal(await page.evaluate(()=>fixture.current.reference),reference);
  assert.equal(calls.filter(c=>c.path==='/api/checkout/recover-receipt').length,1);
  await page.evaluate(()=>fixture.current.check());assert.equal(calls.filter(c=>c.path==='/api/checkout/recover-receipt').length,1);
  await page.evaluate(()=>fixture.enquiry());await page.waitForFunction(()=>typeof fixture.current.start==='function');
  await page.evaluate(()=>fixture.current.start({name:'Synthetic Customer',email:'fixture@example.test',phone:'',subject:'Synthetic enquiry',message:'Synthetic request',source:'contact'}));
  await page.waitForFunction(()=>fixture.current.receipt?.state==='awaiting_verification');
  await page.evaluate(()=>fixture.current.verify('123456'));await page.waitForFunction(()=>fixture.current.receipt?.state==='received');
  assert.equal(calls.filter(c=>c.path==='/api/contact/start').length,1);assert.equal(calls.filter(c=>c.path==='/api/contact/verify').length,1);
  await page.evaluate(()=>fixture.unmount());assert.equal(await page.evaluate(()=>fixture.subscribers()),0);assert.deepEqual(errors,[]);await context.close();
 }finally{await chrome.close();await new Promise(resolve=>server.close(resolve));}
});
