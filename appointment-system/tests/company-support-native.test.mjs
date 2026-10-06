import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=fileURLToPath(new URL('../engine/appointment_system/',import.meta.url));
const available=Boolean(process.env.BOOKING_CHROME_EXECUTABLE&&process.env.BOOKING_BROWSER_NODE_MODULES);
const reference='11111111-1111-4111-8111-111111111111';
const scope={installation_id:reference,environment:'test',legacy:{company:[]}};
const appointment={code:'ok',reference,claim_id:'22222222-2222-4222-8222-222222222222',revision:2,
 name:'Synthetic Person',service:'Synthetic Consultation',starts_at:'2031-04-04T10:30:00Z',state:'confirmed',email:'fixture@example.test',phone:'+919999999999'};
async function fixture(run){
 const {chromium}=await import(pathToFileURL(resolve(process.env.BOOKING_BROWSER_NODE_MODULES,'playwright-core/index.mjs')).href);
 const state={calls:[],reviews:[],results:new Map(),failure:null,wrongResult:false,handlers:new Map(),resultChange:{}};
 const server=createServer(async(req,res)=>{
  const path=new URL(req.url,'http://fixture.invalid').pathname;res.setHeader('cache-control','no-store');
  const files={'/company/booking-support':'company_assets/support.html','/api/company/support.js':'company_assets/support.js',
   '/api/company/staff-actions.js':'studio_assets/staff-actions.js','/api/company/assets/control.css':'company_assets/control.css'};
  if(files[path]){res.setHeader('content-type',path.endsWith('.js')?'text/javascript':path.endsWith('.css')?'text/css':'text/html');
   return res.end((await readFile(resolve(root,files[path]),'utf8')).replace('/*STAFF_BROWSER_CONFIGURATION*/null',JSON.stringify(scope)));}
  res.setHeader('content-type','application/json');let raw='';for await(const part of req)raw+=part;
  const body=raw?JSON.parse(raw):null;state.calls.push({path,body,csrf:req.headers['x-company-csrf']});
  if(state.handlers.has(path))return state.handlers.get(path)({body,res});
  if(path.endsWith('/status'))return res.end(JSON.stringify({code:'ok',csrf_token:'a'.repeat(64),appointments:[appointment],reviews:state.reviews}));
  if(path.endsWith('/time-context'))return res.end(JSON.stringify({code:'ok',timezone:'Asia/Kolkata'}));
  if(path.endsWith('/lookup'))return res.end(JSON.stringify(appointment));
  if(path.endsWith('/resolve-time'))return res.end(JSON.stringify({code:'ok',local:body.local,timezone:body.timezone,instant:'2031-04-04T11:30:00Z'}));
  if(path.includes('/actions/')){const id=path.split('/').pop();return res.end(JSON.stringify({...(state.results.get(id)||{code:'operation_not_found'}),operation_id:state.wrongResult?reference:id}));}
  const name=path.split('/').pop();const code={cancel:'cancelled',reschedule:'rescheduled',support:'support_saved','verified-refund':'refund_verified','resource-reviewed':'resource_reviewed'}[name];
  if(code){const result={code,operation_id:body.operation_id,revision:body.expected_revision+(name==='support'&&body.action==='receipt_recovery'?0:1),...(name==='reschedule'?{starts_at:body.starts_at}:{}),...(name==='support'?{active:true,activation_code:'12345678',expires_at:'2031-04-04T12:00:00Z'}:{}),...state.resultChange};
   if(state.failure==='lost'){state.results.set(body.operation_id,result);res.writeHead(503);return res.end('{"code":"reply_lost"}');}
   if(state.failure){res.writeHead(409);return res.end(JSON.stringify({code:state.failure}));}
   state.results.set(body.operation_id,result);return res.end(JSON.stringify(result));}
  res.writeHead(404);res.end('{}');
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:true,executablePath:process.env.BOOKING_CHROME_EXECUTABLE,args:['--no-sandbox']});
 try{const page=await browser.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',route=>route.request().url().startsWith(origin+'/')?route.continue():route.abort());
  await page.goto(origin+'/company/booking-support');await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('1 upcoming'));
  await run(page,state,origin);assert.deepEqual(errors,[]);
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
}
async function lookup(page){await page.fill('#reference',reference);await page.locator('#lookup button').click();await page.locator('#detail').waitFor({state:'visible'});}
async function action(page,kind){await lookup(page);await page.selectOption('#action',kind);await page.fill('#reason','Synthetic support verification');}
test('company support resolves practice time and sends only the selected appointment action',{skip:!available},()=>fixture(async(page,state)=>{
 await action(page,'reschedule');await page.fill('#starts-at','2031-04-04T17:00');await page.click('#submit-change');
 await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('rescheduled'));
 const moved=state.calls.find(row=>row.path.endsWith('/reschedule'));assert.equal(moved.body.starts_at,'2031-04-04T11:30:00Z');assert.equal(moved.body.expected_revision,2);assert.equal(moved.csrf,'a'.repeat(64));
 await action(page,'cancel');assert.match(await page.locator('#action-note').textContent(),/does not issue a refund/);await page.click('#submit-change');
 await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('cancelled'));assert.equal(state.calls.filter(row=>row.path.endsWith('/cancel')).length,1);
 await action(page,'contact_correction');await page.fill('#email','corrected@example.test');await page.fill('#phone','+919888888888');await page.fill('#payment','pay_fixture');await page.check('#verified');
 await page.click('#submit-change');await page.locator('#activation').waitFor({state:'visible'});assert.match(await page.locator('#activation').textContent(),/12345678/);
 const corrected=state.calls.find(row=>row.path.endsWith('/support'));assert.equal(corrected.body.email,'corrected@example.test');assert.equal(corrected.body.verification_confirmed,true);
 assert.equal(await page.evaluate(()=>JSON.stringify(localStorage).includes('corrected@example.test')),false);
}));
test('lost company support reply checks the saved operation after reload and rejects a different operation result',{skip:!available},()=>fixture(async(page,state)=>{
 state.failure='lost';await action(page,'cancel');await page.click('#submit-change');await page.locator('#retry').waitFor({state:'visible'});
 const sent=state.calls.find(row=>row.path.endsWith('/cancel'));await page.reload();await page.locator('#retry').waitFor({state:'visible'});
 state.wrongResult=true;await page.click('#retry');await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('still needs checking'));
 assert.equal(await page.locator('#retry').isVisible(),true);
 state.wrongResult=false;await page.click('#retry');await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Earlier results checked'));
 assert.equal(await page.locator('#retry').isVisible(),false);assert.equal(state.calls.filter(row=>row.path.endsWith('/cancel')).length,1);
 assert.ok(state.calls.some(row=>row.path.endsWith('/actions/'+sent.body.operation_id)));
}));
test('definitive support refusal leaves no pending retry and an unavailable storage write sends nothing',{skip:!available},()=>fixture(async(page,state)=>{
 state.failure='time_unavailable';await action(page,'reschedule');await page.fill('#starts-at','2031-04-04T17:00');await page.click('#submit-change');
 await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('That time is unavailable'));
 assert.equal(await page.locator('#retry').isVisible(),false);assert.equal(await page.locator('#detail').isVisible(),false);
 state.failure=null;await action(page,'cancel');await page.evaluate(()=>{Storage.prototype.setItem=()=>{throw Error('Synthetic storage refusal');};});
 await page.click('#submit-change');await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('could not safely save'));
 assert.equal(state.calls.filter(row=>row.path.endsWith('/cancel')).length,0);
}));
test('company financial review controls distinguish unresolved disputes from verified refund completion',{skip:!available},()=>fixture(async(page,state)=>{
 state.reviews=[{reference,reason:'dispute_open',resource_kind:'dispute',resource_verified:false,resource_status:'open'},
  {reference,reason:'refund_review',resource_kind:'refund',case_id:reference,revision:4},
  {reference,reason:'dispute_closed',resource_kind:'dispute',resource_verified:true,resource_attention:false,resource_status:'won',case_id:appointment.claim_id,revision:5}];
 await page.click('#refresh');await page.waitForFunction(()=>document.querySelectorAll('#reviews li').length===3);
 assert.equal(await page.locator('#reviews button').count(),2);await page.getByText('The dispute remains open until its current outcome is verified.',{exact:true}).waitFor();
 page.on('dialog',dialog=>dialog.accept('Synthetic verified evidence'));await page.getByRole('button',{name:'Close after verified full refund'}).click();
 await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('refund verified'));
 await page.getByRole('button',{name:'Finish dispute review'}).click();await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('resource reviewed'));
 assert.equal(state.calls.filter(row=>row.path.endsWith('/verified-refund')).length,1);assert.equal(state.calls.filter(row=>row.path.endsWith('/resource-reviewed')).length,1);
}));
test('unexpected success code or revision cannot clear a pending company change',{skip:!available},()=>fixture(async(page,state)=>{
 state.resultChange={code:'ok'};await action(page,'cancel');await page.click('#submit-change');await page.waitForFunction(()=>!document.querySelector('#submit-change').disabled||!document.querySelector('#retry').hidden);
 assert.equal(await page.locator('#retry').isVisible(),true,'An unrelated success must remain uncertain');assert.equal(await page.evaluate(()=>window.PracticeStaffActions('company').get().length),1);
 const sent=state.calls.find(x=>x.path.endsWith('/cancel'));state.results.set(sent.body.operation_id,{code:'ok'});await page.click('#retry');await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('still needs checking'));assert.equal(await page.evaluate(()=>window.PracticeStaffActions('company').get().length),1);
 state.results.set(sent.body.operation_id,{code:'cancelled',revision:3});await page.click('#retry');await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Earlier results checked'));
 state.resultChange={revision:99};await action(page,'cancel');await page.click('#submit-change');await page.locator('#retry').waitFor();assert.equal(await page.evaluate(()=>window.PracticeStaffActions('company').get().length),1);
}));
test('company access expiry removes previously loaded customer details while keeping the pending action identity',{skip:!available},()=>fixture(async(page,state)=>{
 await action(page,'cancel');state.handlers.set('/api/company/support/status',({res})=>{res.writeHead(401);res.end('{"code":"company_session_required"}');});await page.click('#refresh');await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Sign in with company'));
 assert.equal(await page.locator('#detail').isVisible(),false);assert.equal(await page.locator('#summary').textContent(),'');assert.equal(await page.locator('#appointments li').count(),0);
}));
test('inactive or malformed support codes are never shown as usable access',{skip:!available},()=>fixture(async(page,state)=>{
 state.resultChange={active:false,activation_code:'12345678'};await action(page,'receipt_recovery');await page.fill('#payment','pay_fixture');await page.check('#verified');await page.click('#submit-change');await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('support saved'));assert.equal(await page.locator('#activation').isVisible(),false);
 state.resultChange={active:true,activation_code:'bad'};await action(page,'receipt_recovery');await page.fill('#payment','pay_fixture');await page.check('#verified');await page.click('#submit-change');await page.locator('#retry').waitFor();assert.equal(await page.locator('#activation').isVisible(),false);assert.equal(await page.evaluate(()=>window.PracticeStaffActions('company').get().length),1);
}));
test('permission expiry during a change keeps the exact operation for later checking',{skip:!available},()=>fixture(async(page,state)=>{
 state.handlers.set('/api/company/support/cancel',({res})=>{res.writeHead(401);res.end('{"code":"company_session_required"}');});await action(page,'cancel');await page.click('#submit-change');await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Renew company access'));assert.equal(await page.locator('#summary').textContent(),'');assert.equal(await page.locator('#detail').isVisible(),false);assert.equal(await page.evaluate(()=>window.PracticeStaffActions('company').get().length),1);
}));
test('a late lookup cannot re-expose customer information after another request loses permission',{skip:!available},()=>fixture(async(page,state)=>{
 let respond;state.handlers.set('/api/company/support/lookup',({res})=>{respond=()=>res.end(JSON.stringify(appointment));});await page.fill('#reference',reference);await page.locator('#lookup button').click();
 await page.waitForFunction(()=>document.querySelector('#reference').value.length===36);while(!respond)await new Promise(resolve=>setTimeout(resolve,5));
 state.handlers.set('/api/company/support/status',({res})=>{res.writeHead(401);res.end('{"code":"company_session_required"}');});await page.click('#refresh');await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('Sign in with company'));respond();await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('We could not find'));assert.equal(await page.locator('#summary').textContent(),'');assert.equal(await page.locator('#detail').isVisible(),false);
}));
test('failed time resolution does not submit a move and unanswered financial prompt does not close review',{skip:!available},()=>fixture(async(page,state)=>{
 state.handlers.set('/api/company/support/resolve-time',({res})=>res.end(JSON.stringify({code:'ok',timezone:'UTC',local:'different',instant:'bad'})));await action(page,'reschedule');await page.fill('#starts-at','2031-04-04T17:00');await page.click('#submit-change');await page.waitForFunction(()=>document.querySelector('#status').textContent.startsWith('We could not check that local time'));assert.equal(state.calls.filter(x=>x.path.endsWith('/reschedule')).length,0);
 state.reviews=[{reference,reason:'refund_review',resource_kind:'refund',case_id:reference,revision:4}];await page.click('#refresh');await page.getByRole('button',{name:'Close after verified full refund'}).waitFor();page.once('dialog',dialog=>dialog.dismiss());await page.getByRole('button',{name:'Close after verified full refund'}).click();assert.equal(state.calls.filter(x=>x.path.endsWith('/verified-refund')).length,0);
}));
