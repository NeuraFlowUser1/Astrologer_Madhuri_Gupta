/** Actual receiving-site React/Chrome and unbundled shared receipt. Synthetic only. */
import {test,before,after} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {receipt,epoch} from './booking-browser-fixture.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
const available=!!(process.env.BOOKING_CHROME_EXECUTABLE&&process.env.BOOKING_BROWSER_NODE_MODULES);
let browser,server,origin;
before(async()=>{
 if(!available)return;
 const dependencies=process.env.BOOKING_BROWSER_NODE_MODULES,require=createRequire(resolve(dependencies,'fixture.cjs'));
 const {build}=await import(pathToFileURL(require.resolve('vite')).href),entry=resolve(dirname(dependencies),'__abs_receipt_fixture__.mjs');
 const built=await build({root:dirname(dependencies),configFile:false,logLevel:'error',define:{'process.env.NODE_ENV':'"production"'},
  plugins:[{name:'synthetic-receipt-vendor',resolveId:id=>id===entry?'\0receipt-vendor':undefined,
   load:id=>id==='\0receipt-vendor'?"export * as React from 'react'; export {createRoot} from 'react-dom/client';":undefined}],
  build:{write:false,minify:false,lib:{entry,formats:['es'],fileName:'vendor'},rollupOptions:{output:{inlineDynamicImports:true}}}});
 const vendor=(Array.isArray(built)?built[0]:built).output.find(item=>item.type==='chunk'&&item.isEntry).code;
 const id='11111111-1111-4111-8111-111111111111';
 const base={...receipt(id),appointment_state:'confirmed',payment_state:'captured',captured_paise:210000,booking_revision:1,
  meeting_mode:'google_meet',meeting_state:'ready',meet_url:'https://meet.google.com/abc-defg-hij',
  acknowledgement_state:'delivered',meeting_email_state:'provider_accepted',email_copy:{operation_id:null,booking_revision:null,
   state:'not_requested',has_booking_email:true,target_hint:null,next_request_at:null,remaining_requests:3,can_request:true,blocked_reason:null}};
 const document=`<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Local receipt fixture</title>
 <link rel="stylesheet" href="/browser/booking/receipt-fields.css"></head><body><main id="root"></main><script type="module">
 import {React,createRoot} from '/vendor.mjs';
 import {createReceiptFields} from '/browser/booking/receipt-fields.mjs';
 const root=createRoot(document.getElementById('root')),base=${JSON.stringify(base)},listeners=new Set();
 let r=structuredClone(base),display={enabled:true,verified:true,checking:false,activation_epoch:${JSON.stringify(epoch)}};
 const calls=[];let failPost=false,failPDF=false,paused=false,release=null;
 const product={getSnapshot:()=>display,subscribe:fn=>{listeners.add(fn);return()=>listeners.delete(fn);}};
 const api=async(path,{body})=>{
  calls.push({path,body});if(paused)await new Promise(resolve=>release=resolve);
  if(path==='/api/checkout/status')return structuredClone(r);
  if(failPost){failPost=false;throw Error('Synthetic lost reply');}
  r={...r,email_copy:{...r.email_copy,operation_id:body.operation_id,booking_revision:body.expected_revision,state:'pending',
   target_hint:'c***@example.test',can_request:false,blocked_reason:'delivery_pending',remaining_requests:2}};
  return {code:'receipt_copy_accepted',request_id:body.request_id,operation_id:body.operation_id,booking_revision:body.expected_revision,email_copy:r.email_copy};
 };
 // This double proves UI action/freshness/Blob behavior; actual PDF bytes have separate real-library tests.
 const loadPDF=async()=>{
  if(failPDF)throw Error('Synthetic PDF failure');
  const font={getCharacterSet:()=>Array.from({length:10000},(_,i)=>i),widthOfTextAtSize:(s,n)=>s.length*n*.5};
  const PDFDocument={create:async()=>({registerFontkit(){},embedFont:async()=>font,addPage:()=>({drawText(){},node:{set(){}}}),
   context:{register:x=>x,obj:x=>x},save:async()=>new Uint8Array([37,80,68,70])})};
  return {PDFDocument,PDFName:{of:x=>x},PDFString:{of:x=>x},fontkit:{},fontBytes:new Uint8Array([1])};
 };
 const Fields=createReceiptFields(React,{browser:{api,product},brand:'Synthetic practice',loadPDF,theme:'fixture'});
 const credential={request_id:base.request_id,secret:'r1.current.'+'a'.repeat(43)};
 const flow={state:{credential,receipt:r},updateReceipt(value){r=value;render();return r;}};
 let showTitle=true;
 function render(){flow.state.receipt=r;root.render(React.createElement(Fields,{flow,showTitle}));}
 window.proof={base,change(value){r={...base,...value};render();},blank(){r=null;render();},title(value){showTitle=value;render();},
  calls:()=>calls,receipt:()=>r,mode(change){display={...display,...change};for(const fn of listeners)fn();},
  failPost(){failPost=true;},failPDF(value){failPDF=value;},pause(){paused=true;},release(){paused=false;release?.();},unmount(){root.unmount();}};render();
 </script></body></html>`;
 server=createServer(async(req,res)=>{
  try{
   const path=new URL(req.url,'http://fixture.invalid').pathname;
   if(path==='/'){res.setHeader('content-type','text/html');return res.end(document);}
   if(path==='/vendor.mjs'){res.setHeader('content-type','text/javascript');return res.end(vendor);}
   if(/^\/browser\/[a-z0-9/-]+\.(mjs|css)$/.test(path)){
    res.setHeader('content-type',path.endsWith('.css')?'text/css':'text/javascript');return res.end(await readFile(resolve(root,path.slice(1)),'utf8'));
   }
   res.writeHead(404);res.end();
  }catch{res.destroy();}
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));origin='http://127.0.0.1:'+server.address().port;
 const {chromium}=await import(pathToFileURL(resolve(dependencies,'playwright-core/index.mjs')).href);
 browser=await chromium.launch({headless:true,executablePath:process.env.BOOKING_CHROME_EXECUTABLE,args:['--no-sandbox']});
});
after(async()=>{if(browser)await browser.close();if(server)await new Promise(resolve=>server.close(resolve));});
async function pageFor(run){
 const context=await browser.newContext(),page=await context.newPage(),errors=[];
 page.on('pageerror',error=>errors.push(error.message));await context.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
 try{await page.goto(origin);await page.getByRole('heading',{name:'Your appointment is confirmed'}).waitFor();await run(page);assert.deepEqual(errors,[]);}
 finally{await context.close();}
}
test('all saved receipt states expose payment/refund facts and legacy projections never offer actions',{skip:!available},()=>pageFor(async page=>{
 for(const [appointment_state,title] of [['held','Your time is reserved'],['expired','This reservation has ended'],['cancelled','This appointment was cancelled'],['payment_review','Your payment is being checked'],['confirmed','Your appointment is confirmed']]){
  await page.evaluate(({appointment_state})=>proof.change({appointment_state,refunded_paise:100}),{appointment_state});
  await page.getByRole('heading',{name:title,exact:true}).waitFor();
  assert.equal(await page.locator('dt').filter({hasText:/^Refund recorded$/}).locator('xpath=following-sibling::dd').innerText(),'₹1');
  assert.equal(await page.getByRole('button',{name:'Download appointment PDF'}).count(),appointment_state==='confirmed'?1:0);
 }
 await page.evaluate(()=>proof.change({booking_revision:null,meeting_mode:null,email_copy:null}));
 await page.getByText('Check the latest booking status to see available document and email options.').waitFor();
 assert.equal(await page.getByRole('button').count(),0);
 await page.evaluate(()=>proof.title(false));await page.getByRole('region',{name:'Saved appointment details'}).waitFor();
 assert.equal(await page.getByRole('heading').count(),0);await page.evaluate(()=>proof.blank());await page.waitForFunction(()=>document.getElementById('root').childElementCount===0);
}));
test('meeting, confirmation, copy and refusal states use their actual saved facts',{skip:!available},()=>pageFor(async page=>{
 for(const [change,text] of [[{meeting_mode:'internal',meet_url:null},'Contact the practice for the meeting arrangements.'],
  [{meet_url:null,meeting_state:'needs_attention'},'Your meeting link needs attention. Please contact the practice.'],
  [{meet_url:null,meeting_state:'preparing'},'Your meeting link is being prepared.'],
  [{appointment_state:'held',meet_url:null},'Meeting details are available after confirmation.']]){
  await page.evaluate(change=>proof.change(change),change);await page.getByText(text,{exact:true}).waitFor();
 }
 for(const value of ['not_requested','not_queued','pending','processing','provider_accepted','accepted','delivered','failed','attention','needs_attention','bounced','complained','suppressed','retry_wait','delivery_unknown','unknown']){
  await page.evaluate(value=>proof.change({acknowledgement_state:value,meeting_email_state:value}),value);
  await page.waitForFunction(value=>proof.receipt().acknowledgement_state===value,value);
  const fact=await page.locator('dt').filter({hasText:/^Confirmation email$/}).locator('xpath=following-sibling::dd').innerText();assert.ok(fact.length>0);
 }
 for(const reason of ['delivery_pending','delivery_unknown','cooldown','quota','destination_unavailable','copy_unavailable','booking_unavailable']){
  await page.evaluate(reason=>proof.change({email_copy:{...proof.base.email_copy,can_request:false,blocked_reason:reason,target_hint:'c***@example.test'}}),reason);
  await page.waitForFunction(()=>document.querySelector('.abs-copy-hint')?.textContent.length>0);
  assert.equal(await page.getByRole('button',{name:'Email appointment details',exact:true}).isDisabled(),true);
 }
 for(const state of ['not_requested','pending','processing','provider_accepted','delivered','superseded','needs_attention','unknown']){
  await page.evaluate(state=>proof.change({meet_url:null,email_copy:{...proof.base.email_copy,state}}),state);
  await page.waitForFunction(state=>proof.receipt().email_copy.state===state,state);assert.ok((await page.locator('.abs-copy-status').innerText()).length>0);
  if(state==='pending')await page.getByText('We’ll email the details when your meeting link is ready.').waitFor();
 }
}));
test('canonical copy uses saved address and a nullable booking requires a deliberate address with immutable retry',{skip:!available},()=>pageFor(async page=>{
 await page.getByRole('button',{name:'Email appointment details',exact:true}).click();await page.getByRole('status').waitFor();
 assert.equal(await page.locator('input[type=email]').count(),0);
 let posts=await page.evaluate(()=>proof.calls().filter(c=>c.path.endsWith('/email-details')));assert.equal(posts.length,1);assert.equal('email' in posts[0].body,false);
 await page.evaluate(()=>proof.change({email_copy:{...proof.base.email_copy,has_booking_email:false}}));
 const action=page.getByRole('button',{name:'Email appointment details',exact:true});await action.waitFor();await action.click();
 const input=page.getByLabel('Email address for this copy',{exact:true});await input.waitFor();assert.equal(await input.evaluate(n=>n===document.activeElement),true);
 await input.fill('bad');await page.getByRole('button',{name:'Send email copy',exact:true}).click();
 assert.equal((await page.evaluate(()=>proof.calls().filter(c=>c.path.endsWith('/email-details')))).length,1);
 await input.fill('copy@example.test');await page.evaluate(()=>proof.failPost());await page.getByRole('button',{name:'Send email copy',exact:true}).click();
 await page.getByRole('alert').waitFor();assert.equal(await input.isDisabled(),true);
 await page.getByRole('button',{name:'Retry the same email request',exact:true}).click();
 await page.waitForFunction(()=>proof.calls().filter(c=>c.path.endsWith('/email-details')).length===3);
 posts=await page.evaluate(()=>proof.calls().filter(c=>c.path.endsWith('/email-details')));assert.deepEqual(posts[1].body,posts[2].body);assert.equal(posts[2].body.email,'copy@example.test');
 assert.equal((await page.evaluate(()=>proof.receipt())).email_copy.has_booking_email,false);
}));
test('PDF busy/error/ready states and product checking revoke the actual local Blob links',{skip:!available},()=>pageFor(async page=>{
 const button=page.getByRole('button',{name:'Download appointment PDF',exact:true});
 await page.evaluate(()=>{proof.failPDF(true);proof.pause();});await button.click();await page.getByRole('button',{name:'Preparing PDF…',exact:true}).waitFor();
 await page.evaluate(()=>proof.release());await page.getByRole('alert').waitFor();assert.equal(await page.locator('a[download]').count(),0);
 await page.evaluate(()=>proof.failPDF(false));await button.click();await page.getByRole('link',{name:'Download PDF',exact:true}).waitFor();
 const link=page.getByRole('link',{name:'Open PDF',exact:true});assert.match(await link.getAttribute('href'),/^blob:/);
 await page.evaluate(()=>proof.mode({checking:true,verified:false}));await page.waitForFunction(()=>!document.querySelector('a[download]'));
 assert.equal(await page.getByRole('button',{name:'Download appointment PDF',exact:true}).isDisabled(),true);
 await page.evaluate(()=>proof.mode({checking:false,verified:true}));await button.click();await link.waitFor();
 await page.evaluate(()=>proof.unmount());assert.equal(await page.getByRole('link').count(),0);
}));
