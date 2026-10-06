// Actual contact pages, synthetic mail outcomes, booking OFF throughout.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {displayProof} from '../tools/checks/website-display.mjs';
const root=process.env.BOOKING_WEBSITE_PROOF_PROJECT,site=process.env.BOOKING_WEBSITE_PROOF_SITE;
test('actual enquiry form preserves one request through uncertain save, wrong code, expiry and resend',{skip:!root||!site},async()=>{
 const {chromium}=await import(pathToFileURL(resolve(site,'node_modules/playwright-core/index.mjs')).href);
 const browser=await chromium.launch({headless:true,executablePath:process.env.BOOKING_CHROME_EXECUTABLE,args:['--no-sandbox']});
 const proof=await displayProof(root,site,{enabled:false}),context=await browser.newContext({reducedMotion:'reduce'});
 const page=await context.newPage();page.setDefaultTimeout(10000);
 let startFailure=true,wrongCode=true,phase='awaiting_verification',generation=1,delivery='failed',id=null,secret=null;
 const calls=[],errors=[];page.on('pageerror',error=>errors.push(error.message));
 const reply=()=>({code:'ok',request_id:id,state:phase,generation,sends_remaining:3-generation,verification_delivery:delivery,
  server_now:new Date().toISOString(),code_expires_at:new Date(Date.now()+(phase==='expired'?-1000:600000)).toISOString(),resend_after:new Date(Date.now()-1000).toISOString()});
 await context.route('**/*',async route=>{
  const request=route.request(),url=new URL(request.url());if(url.origin!==proof.origin)return route.abort();
  if(!url.pathname.startsWith('/api/')||url.pathname==='/api/service-state')return route.continue();
  const send=(value,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(value)});
  if(url.pathname==='/api/contact/policy')return send({version:1,receipt_key_id:'current'});
  assert.ok(url.pathname.startsWith('/api/contact/'),'Enquiries must not use a booking or payment endpoint');
  const action=url.pathname.split('/').at(-1),body=request.postDataJSON();calls.push({action,body,secret:request.headers()['x-enquiry-receipt']});
  id??=body.request_id;secret??=request.headers()['x-enquiry-receipt'];assert.equal(body.request_id,id);assert.equal(request.headers()['x-enquiry-receipt'],secret);
  if(action==='start'&&startFailure)return send({code:'temporarily_unavailable'},503);
  if(action==='resend'){generation++;phase='awaiting_verification';delivery='delivered';}
  if(action==='verify'){
   assert.equal(body.generation,generation);
   if(wrongCode)return send({code:'invalid_code'},400);
   phase='received';
  }
  return send(reply());
 });
 try{
  await page.goto(proof.origin+'/contact');await page.locator('#visitor-name,#name').first().waitFor();
  const inline=await page.locator('#visitor-name').count()>0;
  if(!inline){
   const offlineHelp=page.getByRole('button',{name:'How do I arrange a consultation?',exact:true});
   await offlineHelp.click();
   await page.getByText('Please call the practice to discuss a suitable time and meeting arrangements.',{exact:true}).waitFor();
   assert.equal(await page.getByText('How are website bookings conducted?',{exact:true}).count(),0);
   await offlineHelp.click();
   await page.getByText('Please call the practice to discuss a suitable time and meeting arrangements.',{exact:true}).waitFor({state:'hidden'});
   await page.getByRole('button',{name:'Submit Message',exact:true}).click();
   for(const text of ['Full name is required.','Email address is required.','Phone number is required.'])await page.getByText(text,{exact:false}).waitFor();
   await page.locator('#email').fill('wrong');await page.locator('#phone').fill('abc');
   await page.getByText('Please enter a valid email address.',{exact:false}).waitFor();
   await page.getByText('Enter a valid phone number (7-15 digits).',{exact:false}).waitFor();
   assert.equal(calls.length,0,'Invalid local fields must not create an enquiry');
   // Isolated clipboard double: this never changes the owner's system clipboard.
   await page.evaluate(()=>Object.defineProperty(navigator,'clipboard',{value:{writeText:async value=>{window.__copiedPublicContact=value;}}}));
   for(const button of await page.getByRole('button',{name:/^Copy /}).all()){
    await button.click();assert.ok(await page.evaluate(()=>window.__copiedPublicContact));
   }
  }
  await page.locator('#visitor-name,#name').fill('Synthetic Customer');await page.locator('#visitor-email,#email').fill('customer@example.com');
  // AstroAdvice allows a blank message and normalises a local Indian number;
  // Sarsa requires a question. Exercise each actual project's input contract.
  await page.locator('#visitor-phone,#phone').fill(inline?'+919876543210':'98765 43210');
  await page.locator('#message').fill(inline?'A synthetic question for the practice.':'');
  if(inline){
   const topicLink=page.locator('[data-route]').first();if(await topicLink.count())await topicLink.click();
   await page.locator('#topic').selectOption('Payment question');await page.locator('#reference').fill('synthetic-reference');
   await page.locator('#message').fill('q'.repeat(4000));await page.getByRole('button',{name:/^Continue to email verification/}).click();
   await page.getByText('Please shorten your question slightly to leave room for the booking reference.',{exact:true}).waitFor();
   await page.locator('#visitor-name').fill('  ');await page.locator('#message').fill('     ');
   await page.getByRole('button',{name:/^Continue to email verification/}).click();
   await page.getByText('Please enter your name and a question of at least five characters.',{exact:true}).waitFor();
   assert.equal(calls.length,0);
   await page.locator('#visitor-name').fill('Synthetic Customer');await page.locator('#message').fill('A synthetic question for the practice.');
  }
  await page.getByRole('button',{name:/^(Continue to email verification|Submit Message)/}).click();
  await page.getByRole('button',{name:'Retry the same request',exact:true}).waitFor();
  assert.equal(await page.locator('#code,input[aria-label="Verification digit 1"]').count(),0,'A failed save is not a delivered code');
  startFailure=false;await page.getByRole('button',{name:'Retry the same request',exact:true}).click();
  await page.locator('#code,input[aria-label="Verification digit 1"]').waitFor();
  const starts=calls.filter(call=>call.action==='start');assert.equal(starts.length,2);assert.deepEqual(starts[0],starts[1],'Retry preserves the exact enquiry and owned access');
  if(inline)assert.match(starts[0].body.message,/^Booking reference: synthetic-reference\n\n/);
  else{
   assert.equal(starts[0].body.phone,'+919876543210');
   assert.equal(starts[0].body.message,'Please contact me about this inquiry.');
   await page.getByLabel('Verification digit 1',{exact:true}).fill('x');assert.equal(await page.getByLabel('Verification digit 1',{exact:true}).inputValue(),'');
   await page.getByLabel('Verification digit 2',{exact:true}).focus();await page.keyboard.press('Backspace');
   assert.equal(await page.getByLabel('Verification digit 1',{exact:true}).evaluate(node=>document.activeElement===node),true);
   await page.keyboard.press('Escape');await page.getByRole('dialog',{name:'Verify your enquiry'}).waitFor({state:'hidden'});
   await page.getByRole('button',{name:'Continue saved enquiry',exact:true}).click();
   const dialog=page.getByRole('dialog',{name:'Verify your enquiry'});
   const focusable=dialog.locator('button:not(:disabled), input:not(:disabled)');
   await focusable.first().focus();await page.keyboard.press('Shift+Tab');assert.equal(await focusable.last().evaluate(node=>document.activeElement===node),true);
   await page.keyboard.press('Tab');assert.equal(await focusable.first().evaluate(node=>document.activeElement===node),true);
   await page.getByLabel('Verification digit 1',{exact:true}).evaluate(node=>{
    const clipboardData=new DataTransfer();clipboardData.setData('text','123456');node.dispatchEvent(new ClipboardEvent('paste',{bubbles:true,clipboardData}));
   });
   assert.equal(await page.getByLabel('Verification digit 6',{exact:true}).inputValue(),'6');
  }
  async function fillCode(){if(inline)await page.locator('#code').fill('123456');else for(let i=1;i<=6;i++)await page.getByLabel('Verification digit '+i,{exact:true}).fill(String(i));}
  const verify=()=>page.getByRole('button',{name:inline?/^Verify & send enquiry/:/^Verify and send enquiry$/});
  await fillCode();await verify().click();
  await page.locator(inline?'#form-status':'[role=alert]').filter({hasText:/\S/}).first().waitFor();
  assert.equal(await page.locator('#outcome').count(),0);assert.equal(await page.getByRole('heading',{name:'Message Submitted!',exact:true}).count(),0);
  const check=()=>page.getByRole('button',{name:inline?'Check enquiry status':'Check saved enquiry',exact:true});
  phase='expired';await check().click();
  await page.getByText(inline?/This code is no longer usable/:/This code has expired/).waitFor();
  if(inline)assert.equal(await page.locator('#code').count(),0);else assert.equal(await verify().isDisabled(),true);
  const resend=()=>page.getByRole('button',{name:inline?'Request a new code':'Resend Code',exact:true});
  await resend().click();await page.locator('#code,input[aria-label="Verification digit 1"]').waitFor();
  await page.waitForFunction(()=>{const input=document.querySelector('#code,input[aria-label="Verification digit 1"]');return input&&!input.disabled;});
  assert.equal(generation,2);assert.equal(await page.locator('#code,input[aria-label="Verification digit 1"]').inputValue(),'');
  wrongCode=false;await fillCode();await verify().click();
  if(inline)await page.locator('#outcome').waitFor();else await page.getByRole('heading',{name:'Message Submitted!',exact:true}).waitFor();
  assert.equal(calls.filter(call=>call.action==='start').length,2);assert.equal(calls.filter(call=>call.action==='resend').length,1);
  assert.deepEqual(errors,[]);
  if(inline){await page.getByRole('button',{name:'Write another enquiry',exact:true}).click();await page.locator('#visitor-name').waitFor();assert.equal(await page.locator('#visitor-name').inputValue(),'');}
  else{await page.getByRole('button',{name:'Send Another Message',exact:true}).click();await page.locator('#name').waitFor();assert.equal(await page.locator('#name').inputValue(),'');}
 }finally{await context.close();await browser.close();await proof.close();}
});
