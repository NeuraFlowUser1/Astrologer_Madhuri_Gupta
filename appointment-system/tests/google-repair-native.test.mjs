import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {within} from './staff-page-fixture.mjs';
const assets=fileURLToPath(new URL('../engine/appointment_system/company_assets/',import.meta.url));
const available=Boolean(process.env.BOOKING_CHROME_EXECUTABLE&&process.env.BOOKING_BROWSER_NODE_MODULES);
const operation='11111111-1111-4111-8111-111111111111',secret='a'.repeat(64);
async function fixture(fragment,run){
 const {chromium}=await import(pathToFileURL(resolve(process.env.BOOKING_BROWSER_NODE_MODULES,'playwright-core/index.mjs')).href);
 const state={calls:[],lost:false,bad:false,denied:false};let origin;
 const server=createServer(async(req,res)=>{
  const path=new URL(req.url,'http://fixture.invalid').pathname;res.setHeader('cache-control','no-store');
  const file={'/company/google-repair':'google-repair.html','/api/company/google-repair.js':'google-repair.js','/api/company/assets/control.css':'control.css'}[path];
  if(file){res.setHeader('content-type',file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html');return res.end(await readFile(resolve(assets,file)));}
  res.setHeader('content-type','application/json');let raw='';for await(const part of req)raw+=part;
  const body=raw?JSON.parse(raw):null;state.calls.push({path,body,csrf:req.headers['x-company-csrf']});
  if(state.denied){res.writeHead(401);return res.end('{}');}
  if(path==='/api/company/control/status')return res.end(JSON.stringify({csrf_token:'b'.repeat(64)}));
  if(path.endsWith('/owner-start'))return res.end(JSON.stringify({authorization_url:state.bad?'https://foreign.example.test/collect':'https://accounts.google.com/o/oauth2/v2/auth?client_id=synthetic'}));
  if(path.endsWith('/owner-link')){
   if(state.lost){state.lost=false;res.writeHead(503);return res.end('{}');}
   return res.end(JSON.stringify({owner_link:(state.bad?'https://foreign.example.test':origin)+'/company/google-repair#link='+operation+'.'+secret}));}
  res.writeHead(404);res.end('{}');
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));origin='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:true,executablePath:process.env.BOOKING_CHROME_EXECUTABLE,args:['--no-sandbox']});
 try{const page=await browser.newPage(),errors=[];page.setDefaultTimeout(10000);page.on('pageerror',error=>errors.push(error.message));
  // No real account approval or outside network traffic is permitted.
  await page.route('**/*',route=>route.request().url().startsWith(origin+'/')?route.continue():route.abort());
  await page.goto(origin+'/company/google-repair'+fragment);await run(page,state,origin);assert.deepEqual(errors,[]);
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
}
test('owner approval removes its private fragment and refuses an outside approval destination',{skip:!available},()=>fixture('#link='+operation+'.'+secret,async(page,state,origin)=>{
 await page.locator('#owner').waitFor({state:'visible'});assert.equal(page.url(),origin+'/company/google-repair');assert.equal(state.calls.length,0);
 state.bad=true;await page.click('#approve');await page.getByText('The Google approval address could not be confirmed.',{exact:true}).waitFor();
 assert.deepEqual(state.calls[0].body,{operation_id:operation,secret});assert.equal(await page.locator('#approve').isDisabled(),false);assert.equal(page.url(),origin+'/company/google-repair');
 state.denied=true;await page.click('#approve');await page.waitForFunction(()=>document.querySelector('#message').textContent.includes('could not be confirmed. Check your company'));
 assert.equal(state.calls.length,2);assert.equal(await page.locator('#company').isVisible(),false);
}));
test('company owner-link retry keeps the original request and refuses a foreign link before displaying it',{skip:!available},()=>fixture('',async(page,state)=>{
 await page.locator('#company').waitFor({state:'visible'});state.lost=true;
 await page.fill('#reference',operation);await page.fill('#reason','Synthetic owner repair');await page.selectOption('#resource','client_sheet');await page.locator('#issue button').click();
 await page.waitForFunction(()=>document.querySelector('#message').textContent.includes('could not be confirmed. Check your company'));
 state.bad=true;await page.fill('#reason','Changed form must not alter the pending request');await page.locator('#issue button').click();
 await page.getByText('The owner link could not be confirmed.',{exact:true}).waitFor();assert.equal(await page.locator('#link-label').isVisible(),false);
 state.bad=false;await page.locator('#issue button').click();await page.locator('#owner-link').waitFor({state:'visible'});
 const sent=state.calls.filter(row=>row.path.endsWith('/owner-link'));assert.equal(sent.length,3);assert.deepEqual(sent[0],sent[1]);assert.deepEqual(sent[1],sent[2]);assert.equal(sent[0].csrf,'b'.repeat(64));
 await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{value:{writeText:()=>Promise.reject(Error('Synthetic clipboard refusal'))},configurable:true}));
 await page.click('#copy');await page.getByText('Select and copy the displayed link.',{exact:true}).waitFor();
 await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{value:{writeText:text=>{window.copiedFixture=text;return Promise.resolve();}},configurable:true}));
 await page.click('#copy');await page.getByText('The private link is copied.',{exact:true}).waitFor();assert.equal(await page.evaluate(()=>window.copiedFixture),await page.inputValue('#owner-link'));
}));
test('approval return states do not disclose company controls or create another connection',{skip:!available},async()=>{
 for(const [fragment,expected] of [['#approved=pending','Your approval was received.'],['#approved=denied','The approval was not saved.']]){
  await fixture(fragment,async(page,state,origin)=>{await page.waitForFunction(text=>document.querySelector('#message').textContent.startsWith(text),expected);
   assert.equal(page.url(),origin+'/company/google-repair');assert.equal(state.calls.length,0);assert.equal(await page.locator('#company').isVisible(),false);assert.equal(await page.locator('#owner').isVisible(),false);});
 }
});
test('expired company permission clears an already displayed private owner link',{skip:!available},()=>fixture('',async(page,state)=>{
 await page.locator('#company').waitFor();await page.fill('#reference',operation);await page.fill('#reason','Synthetic existing obligation');await page.locator('#issue button').click();await page.locator('#owner-link').waitFor();
 assert.match(await page.inputValue('#owner-link'),/#link=/);
 state.denied=true;await page.locator('#issue button').click();await page.waitForFunction(()=>document.querySelector('#message').textContent.includes('could not be confirmed'));
 assert.equal(await page.locator('#company').isVisible(),false);assert.equal(await page.inputValue('#owner-link'),'');assert.equal(await page.locator('#copy').isVisible(),false);
}));
test('valid owner approval opens only Google and does not grant company access',{skip:!available},()=>fixture('#link='+operation+'.'+secret,async(page,state)=>{
 await page.route('https://accounts.google.com/**',route=>route.fulfill({status:200,contentType:'text/html',body:'Local synthetic consent page'}));await page.click('#approve');await page.waitForURL('https://accounts.google.com/o/oauth2/v2/auth?client_id=synthetic');
 assert.equal(state.calls.length,1);assert.equal(state.calls[0].path,'/api/company/resources/owner-start');assert.equal(state.calls[0].csrf,undefined);
}));
test('double owner approval and double owner-link submission each keep one pending request',{skip:!available},async()=>{
 for(const ownerPage of [true,false])await fixture(ownerPage?'#link='+operation+'.'+secret:'',async(page,state,origin)=>{
  const received=Promise.withResolvers(),release=Promise.withResolvers();let calls=0;
  await page.route('**/api/company/resources/'+(ownerPage?'owner-start':'owner-link'),async route=>{calls++;received.resolve();await release.promise;await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(ownerPage?{authorization_url:'https://foreign.example.test'}:{owner_link:origin+'/company/google-repair#link='+operation+'.'+secret})});});
  if(ownerPage)await page.click('#approve');else{await page.locator('#company').waitFor();await page.fill('#reference',operation);await page.fill('#reason','Synthetic saved obligation');await page.locator('#issue button').click();}
  await within(received.promise);
  await page.evaluate(ownerPage=>ownerPage?document.querySelector('#approve').dispatchEvent(new Event('click')):document.querySelector('#issue').dispatchEvent(new Event('submit',{cancelable:true})),ownerPage);
  release.resolve();await page.waitForFunction(ownerPage=>document.querySelector('#message').textContent.includes(ownerPage?'address could not be confirmed':'Send this link privately'),ownerPage);
  assert.equal(calls,1);
 });
});
