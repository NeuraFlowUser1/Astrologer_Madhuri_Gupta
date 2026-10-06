import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {available,id,other,waitText} from './staff-page-fixture.mjs';
const assets=fileURLToPath(new URL('../engine/appointment_system/studio_assets/',import.meta.url));
const item=()=>({item_key:'enquiry:'+id,review_revision:2,state:'verified',created_at:'2031-04-04T10:30:00Z',title:'Synthetic question',enquiry:{name:'Fixture Person',email:'fixture@example.test',phone:'',subject:'Consultation',message:'<script>window.unwanted=true</script>'}});
async function fixture(run){
 const state={calls:[],signedIn:true,row:item(),items:null,handlers:new Map(),errors:[]};
 const server=createServer(async(req,res)=>{
  try{
   const path=new URL(req.url,'http://fixture.invalid').pathname;res.setHeader('cache-control','no-store');
   const files={'/enquiries-studio':'enquiries.html','/api/enquiry-studio/interface.js':'enquiries.js','/api/enquiry-studio/interface.css':'enquiries.css','/api/enquiry-studio/staff-actions.js':'staff-actions.js'};
   if(files[path]){res.setHeader('content-type',path.endsWith('.js')?'text/javascript':path.endsWith('.css')?'text/css':'text/html');return res.end((await readFile(resolve(assets,files[path]),'utf8')).replace('/*STAFF_BROWSER_CONFIGURATION*/null',JSON.stringify({installation_id:id,environment:'test',legacy:{client:[],company:[],calendar:[],inbox:[],enquiry:[]}})));}
   let raw='';for await(const part of req)raw+=part;const body=raw?JSON.parse(raw):null;state.calls.push({path,body});const reply=(value,status=200)=>{res.writeHead(status,{'content-type':'application/json'});res.end(JSON.stringify(value));};
   if(state.handlers.has(path))return await state.handlers.get(path)({body,reply,res});
   if(path.endsWith('/status'))return reply(state.signedIn?{signed_in:true,email:'practice@example.test'}:{signed_in:false},state.signedIn?200:401);
   if(path.endsWith('/inbox/list'))return reply({code:'ok',items:state.items??[state.row],next_cursor:null});
   if(path.endsWith('/inbox/detail'))return reply({code:'ok',item:state.row});
   reply({code:'fixture_route_missing'},404);
  }catch(error){state.errors.push(error.message);res.destroy();}
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin='http://127.0.0.1:'+server.address().port;
 const {chromium}=await import(pathToFileURL(resolve(process.env.BOOKING_BROWSER_NODE_MODULES,'playwright-core/index.mjs')).href);
 const browser=await chromium.launch({headless:true,executablePath:process.env.BOOKING_CHROME_EXECUTABLE,args:['--no-sandbox']});
 try{const context=await browser.newContext(),page=await context.newPage();page.setDefaultTimeout(10000);page.on('pageerror',error=>state.errors.push(error.message));await context.route('**/*',route=>route.request().url().startsWith(origin+'/')?route.continue():route.abort());
  await page.goto(origin+'/enquiries-studio');await page.locator('#items button').waitFor();await run(page,state,origin);assert.deepEqual(state.errors,[]);await context.close();
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
}
test('standalone enquiries work without booking routes, escape text and save one revision-bound private note',{skip:!available},()=>fixture(async(page,state)=>{
 await page.locator('#items button').click();await page.locator('#detail').waitFor();assert.match(await page.locator('#detail-body').textContent(),/<script>/);assert.equal(await page.evaluate(()=>window.unwanted),undefined);assert.equal(await page.locator('#retry').isVisible(),false);
 await page.click('#save');await waitText(page,'#status','short note');state.handlers.set('/api/enquiry-studio/inbox/review',({reply})=>reply({code:'review_saved',revision:3}));await page.fill('#note','Synthetic private note');await page.click('#save');await waitText(page,'#status','note has been saved');
 const sent=state.calls.find(x=>x.path.endsWith('/review'));assert.equal(sent.body.expected_revision,2);assert.equal(sent.body.item_key,'enquiry:'+id);assert.equal(await page.evaluate(()=>JSON.stringify(localStorage).includes('Synthetic private note')),false);
 assert.ok(state.calls.every(x=>x.path.startsWith('/api/enquiry-studio/')));
}));
test('enquiry update retry only queues saved work and view/paging controls keep the selected cursor',{skip:!available},()=>fixture(async(page,state)=>{
 state.row={...item(),item_key:'enquiry-delivery:'+id,summary:'Saved update needs attention'};await page.click('#attention');await page.locator('#items button').click();await page.locator('#retry').waitFor();
 state.handlers.set('/api/enquiry-studio/inbox/retry',({reply})=>reply({code:'retry_queued',revision:3}));await page.fill('#note','Delivery connection checked');await page.click('#retry');await waitText(page,'#status','does not mean it has been delivered');
 state.row=item();state.handlers.set('/api/enquiry-studio/inbox/list',({body,reply})=>reply({code:'ok',items:[{...item(),item_key:'enquiry:'+(body.after?other:id)}],next_cursor:body.after?null:'enquiry:'+id}));await page.click('#messages');await page.locator('#more').waitFor();await page.click('#more');await page.waitForFunction(()=>document.querySelectorAll('#items article').length===2);assert.equal(state.calls.filter(x=>x.path.endsWith('/list')).at(-1).body.after,'enquiry:'+id);
 await page.locator('#items button').first().click();await page.locator('#detail').waitFor();await page.click('#close');assert.equal(await page.locator('#detail').isVisible(),false);
}));
test('lost enquiry note reply is read after reload, never resent, and rejects a foreign saved-action result',{skip:!available},()=>fixture(async(page,state)=>{
 let operation;state.handlers.set('/api/enquiry-studio/inbox/review',({body,reply})=>{operation=body.operation_id;reply({code:'unknown'},503);});await page.locator('#items button').click();await page.fill('#note','Synthetic follow-up');await page.click('#save');await waitText(page,'#status','could not complete');await page.reload();await page.locator('#check-saved').waitFor();
 state.handlers.set('/api/enquiry-studio/inbox/action-result',({reply})=>reply({code:'review_saved',operation_id:other}));await page.click('#check-saved');await waitText(page,'#status','could not complete');assert.equal(await page.evaluate(()=>window.PracticeStaffActions('enquiry').get().length),1);
 state.handlers.set('/api/enquiry-studio/inbox/action-result',({body,reply})=>reply({code:'review_saved',operation_id:body.operation_id}));await page.click('#check-saved');await waitText(page,'#status','Earlier actions checked');assert.equal(state.calls.filter(x=>x.path.endsWith('/review')).length,1);assert.equal(state.calls.filter(x=>x.path.endsWith('/action-result')).at(-1).body.operation_id,operation);
}));
test('definitive stale enquiry note is cleared but failed browser storage cannot send another action',{skip:!available},()=>fixture(async(page,state)=>{
 state.handlers.set('/api/enquiry-studio/inbox/review',({reply})=>reply({code:'revision_changed'},409));await page.locator('#items button').click();await page.fill('#note','Synthetic stale review');await page.click('#save');await waitText(page,'#status','could not complete');assert.equal(await page.evaluate(()=>window.PracticeStaffActions('enquiry').get().length),0);
 await page.evaluate(()=>{Storage.prototype.setItem=()=>{throw Error('Synthetic storage refusal');};});await page.click('#save');await waitText(page,'#status','could not safely save');assert.equal(state.calls.filter(x=>x.path.endsWith('/review')).length,1);
}));
test('enquiry signout and empty views remain usable and unauthorized Google destinations are refused',{skip:!available},()=>fixture(async(page,state,origin)=>{
 state.items=[];await page.click('#refresh');await waitText(page,'#status','no verified messages');await page.click('#attention');await waitText(page,'#status','No enquiry updates');
 state.handlers.set('/api/enquiry-studio/logout',({reply})=>{state.signedIn=false;reply({code:'signed_out'});});await page.click('#logout');await page.locator('#signin').waitFor();assert.equal(await page.locator('#workspace').isVisible(),false);
 state.handlers.set('/api/enquiry-studio/sign-in/start',({reply})=>reply({authorization_url:'https://example.test/collect'}));await page.click('#signin');await waitText(page,'#status','could not complete');assert.equal(page.url(),origin+'/enquiries-studio');
}));
test('enquiry detail must match the requested message and contain a valid saved revision before actions appear',{skip:!available},()=>fixture(async(page,state)=>{
 for(const row of [{...item(),item_key:'enquiry:'+other},{...item(),review_revision:-1},{...item(),review_revision:true}]){
  state.handlers.set('/api/enquiry-studio/inbox/detail',({reply})=>reply({code:'ok',item:row}));await page.click('#refresh');await page.locator('#items button').click();await page.waitForFunction(()=>!document.querySelector('#refresh').disabled);
  assert.equal(await page.locator('#detail').isVisible(),false,'A different or invalid message must not become the selected action target');
 }
}));
test('lost enquiry permission clears displayed private records and never resubmits an uncertain note',{skip:!available},()=>fixture(async(page,state)=>{
 await page.locator('#items button').click();await page.fill('#note','Synthetic confidential note');state.handlers.set('/api/enquiry-studio/inbox/review',({reply})=>reply({code:'access_unavailable'},403));await page.click('#save');await page.waitForFunction(()=>!document.querySelector('#save').disabled||!document.querySelector('#signin').hidden);
 assert.equal(await page.locator('#workspace').isVisible(),false);assert.equal(await page.locator('#items').textContent(),'');assert.equal(await page.locator('#detail-body').textContent(),'');assert.equal(await page.locator('#note').inputValue(),'');assert.equal(await page.locator('#signin').isVisible(),true);
 assert.equal(await page.evaluate(()=>window.PracticeStaffActions('enquiry').get().length),1);assert.equal(state.calls.filter(x=>x.path.endsWith('/review')).length,1);
}));
for(const status of [401,403])test(`enquiry permission loss clears private data before parsing a ${status} error body`,{skip:!available},()=>fixture(async(page,state)=>{
 await page.locator('#items button').click();await page.fill('#note','Synthetic confidential note');
 state.handlers.set('/api/enquiry-studio/inbox/review',({res})=>{res.writeHead(status,{'content-type':status===401?'text/html':'application/json'});res.end(status===401?'Sign in':'{broken');});
 await page.click('#save');await waitText(page,'#status','Sign in again');
 assert.equal(await page.locator('#workspace').isVisible(),false);
 assert.equal(await page.locator('#items').textContent(),'');
 assert.equal(await page.locator('#detail-body').textContent(),'');
 assert.equal(await page.locator('#note').inputValue(),'');
 assert.equal(await page.evaluate(()=>window.PracticeStaffActions('enquiry').get().length),1);
 assert.equal(state.calls.filter(x=>x.path.endsWith('/review')).length,1);
}));
