import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const assets=fileURLToPath(new URL('../engine/appointment_system/company_assets/',import.meta.url));
const available=Boolean(process.env.BOOKING_CHROME_EXECUTABLE&&process.env.BOOKING_BROWSER_NODE_MODULES);
const scope={installation_id:'1bbbc890-7c26-4ba6-b3ef-7c9b363c5bc2',environment:'test'};
async function fixture(run){
 const {chromium}=await import(pathToFileURL(resolve(process.env.BOOKING_BROWSER_NODE_MODULES,'playwright-core/index.mjs')).href);
 const calls={mode:[],business:[]},lost={mode:true,business:true};let signed=false;
 const business={revision:'1',settings:{timezone:'Asia/Kolkata',slot_step_minutes:15,notice_minutes:60,horizon_days:90,
  buffer_before_minutes:0,buffer_after_minutes:0,meeting:'google_meet',booking_verification:{email:false},weekly_windows:[{weekday:0,start:'09:00',end:'17:00'}],
  services:[{id:'consultation',name:'Synthetic consultation',enabled:true,duration_minutes:30,pricing:{kind:'fixed',amount_paise:100}}]}};
 const snapshot={enabled:false,revision:'1',restore_generation:'cb122b99-90c2-42ec-b165-f77e6d0caa22'};
 const server=createServer(async(req,res)=>{
  const path=new URL(req.url,'http://fixture.invalid').pathname;res.setHeader('cache-control','no-store');
  if(path==='/company/booking-control'){res.setHeader('content-type','text/html');return res.end((await readFile(resolve(assets,'control.html'),'utf8')).replaceAll('CLIENT_NAME','Synthetic Practice').replaceAll('PROJECT_NUMBER','fixture'));}
  const name=path.split('/').pop();
  if(path.startsWith('/api/company/assets/')&&['control.css','control.js','command-journal.js'].includes(name)){
   res.setHeader('content-type',name.endsWith('.css')?'text/css':'text/javascript');return res.end((await readFile(resolve(assets,name),'utf8')).replace('/*COMPANY_BROWSER_CONFIGURATION*/null',JSON.stringify(scope)));
  }
  res.setHeader('content-type','application/json');
  if(path==='/api/company/sign-in/start'){signed=true;return res.end('{}');}
  if(path==='/api/company/sign-out'){signed=false;return res.end('{}');}
  if(!signed){res.writeHead(401);return res.end('{"code":"company_session_required"}');}
  const status=()=>({snapshot,csrf_token:'a'.repeat(64),progress:'effective'});
  if(path==='/api/company/control/status')return res.end(JSON.stringify(status()));
  if(path==='/api/company/settings'&&req.method==='GET')return res.end(JSON.stringify(business));
  const kind=path==='/api/company/control/change'?'mode':path==='/api/company/settings'?'business':null;
  if(kind&&req.method==='POST'){
   let body='';for await(const chunk of req)body+=chunk;const value=JSON.parse(body);calls[kind].push(value);
   if(lost[kind]){lost[kind]=false;res.writeHead(503);return res.end('{"code":"saved_reply_unavailable"}');}
   if(kind==='mode')snapshot.enabled=value.enabled;
   else {business.revision='2';business.settings=value.settings;}
   return res.end(JSON.stringify(kind==='mode'?{...status(),operation_id:value.operation_id}:{saved:true,revision:business.revision,quote_version:'a'.repeat(64)}));
  }
  res.writeHead(404);res.end('{}');
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:true,executablePath:process.env.BOOKING_CHROME_EXECUTABLE,args:['--no-sandbox']});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',route=>route.request().url().startsWith(origin+'/')?route.continue():route.abort());
  await page.goto(origin+'/company/booking-control');await page.locator('#signed-out').waitFor({state:'visible'});
  await page.fill('#username','synthetic.owner');await page.fill('#password','Synthetic browser password');await page.click('#login');
  await page.locator('#signed-in').waitFor({state:'visible'});await run(page,calls,origin);assert.deepEqual(errors,[]);
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
}
test('actual company mode and settings commands survive reload and retry the same saved body',{skip:!available},()=>fixture(async(page,calls)=>{
 await page.click('#change');await page.getByRole('button',{name:'Check the saved change',exact:true}).waitFor();
 await page.reload();await page.getByRole('button',{name:'Check the saved change',exact:true}).click();
 await page.getByRole('button',{name:'Turn booking off',exact:true}).waitFor();
 assert.equal(calls.mode.length,2);assert.deepEqual(calls.mode[0],calls.mode[1]);
 await page.getByText('Prices, appointment lengths and working hours',{exact:true}).click();await page.click('#load-business');
 await page.fill('#business-notice','45');await page.fill('#business-reason','Synthetic opening-hours change');await page.click('#save-business');
 await page.getByRole('button',{name:'Check the saved settings change',exact:true}).waitFor();await page.reload();
 await page.getByText('Prices, appointment lengths and working hours',{exact:true}).click();await page.click('#load-business');
 await page.getByRole('button',{name:'Check the saved settings change',exact:true}).waitFor();
 await page.fill('#business-notice','120');await page.fill('#business-reason','A different edit must not replace the pending one');await page.click('#save-business');
 await page.getByText('Settings saved. Existing accepted appointments are unchanged.',{exact:true}).waitFor();
 assert.equal(calls.business.length,2);assert.deepEqual(calls.business[0],calls.business[1]);assert.equal(calls.business[1].settings.notice_minutes,45);
}));
test('actual company page sends no mutation when the browser refuses to save its retry record',{skip:!available},()=>fixture(async(page,calls)=>{
 await page.evaluate(()=>{Storage.prototype.setItem=()=>{throw new Error('Synthetic storage denial');};});
 await page.click('#change');await page.getByText('This browser could not safely save or read the change reference. Allow site storage, then refresh before trying again.',{exact:true}).waitFor();
 assert.equal(calls.mode.length,0);assert.equal(await page.locator('#change').isDisabled(),true);
 await page.getByText('Prices, appointment lengths and working hours',{exact:true}).click();await page.click('#load-business');
 await page.fill('#business-reason','Synthetic storage-denial check');await page.click('#save-business');
 await page.waitForFunction(()=>document.querySelector('#business-status').textContent.includes('could not safely save'));
 assert.equal(calls.business.length,0);
}));
test('a delayed settings reload after a successful save cannot restore private controls after sign-out',{skip:!available},()=>fixture(async(page,calls,origin)=>{
 await page.getByText('Prices, appointment lengths and working hours',{exact:true}).click();await page.click('#load-business');
 await page.fill('#business-reason','Synthetic delayed settings-response check');await page.click('#save-business');
 await page.getByRole('button',{name:'Check the saved settings change',exact:true}).waitFor();
 let release;const held=new Promise(resolve=>{release=resolve;});let received;
 const responseReady=new Promise(resolve=>{received=resolve;});
 await page.route(origin+'/api/company/settings',async route=>{
  if(route.request().method()!=='GET')return route.continue();
  const response=await route.fetch();received();await held;await route.fulfill({response});
 });
 try{
  await page.click('#save-business');await responseReady;
  assert.equal(calls.business.length,2);assert.deepEqual(calls.business[0],calls.business[1]);
  await page.click('#logout');await page.getByText('You are signed out.',{exact:true}).waitFor();
  const finished=page.waitForResponse(response=>response.url()===origin+'/api/company/settings'&&response.request().method()==='GET');
  release();await finished;
  // Wait for queued response handlers, not an arbitrary time interval.
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  assert.equal(await page.locator('#business-section').isVisible(),false);
  assert.equal(await page.locator('#business-form').isVisible(),false);
  assert.equal(await page.locator('#business-services').locator('input').count(),0);
  assert.equal(await page.locator('#business-status').textContent(),'');
  assert.equal(await page.locator('#status').textContent(),'You are signed out.');
 }finally{release();}
}));
