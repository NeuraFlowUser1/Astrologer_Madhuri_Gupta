// Actual built project views consume the common public response contracts.
// This fixture cannot reach providers, customer data or either live website.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {displayProof} from '../tools/checks/website-display.mjs';
import {policy,availability,receipt} from './booking-browser-fixture.mjs';
import {money} from '../browser/display-formatting.mjs';
const root=process.env.BOOKING_WEBSITE_PROOF_PROJECT,site=process.env.BOOKING_WEBSITE_PROOF_SITE;
const reference='11111111-1111-4111-8111-111111111111';
test('actual project booking and receipt views distinguish payment, meeting, refund and unavailable states',{skip:!root||!site},async()=>{
 const profile=JSON.parse(readFileSync(resolve(root,'appointment-settings/booking-browser.json')));
 const {chromium}=await import(pathToFileURL(resolve(site,'node_modules/playwright-core/index.mjs')).href);
 const browser=await chromium.launch({headless:true,executablePath:process.env.BOOKING_CHROME_EXECUTABLE,args:['--no-sandbox']});
 const proof=await displayProof(root,site,{enabled:true});
 const cases=[
  {name:'held',patch:{next_actions:['check_status','resume_payment']}},
  {name:'expired',patch:{appointment_state:'expired',hold_expires_at:'2026-10-03T04:00:00Z',next_actions:['check_status','choose_new_time']}},
  {name:'review',patch:{appointment_state:'payment_review',payment_state:'needs_attention',next_actions:['contact_support','check_status']}},
  {name:'cancelled',patch:{appointment_state:'cancelled',payment_state:'refunded',captured_paise:210000,refunded_paise:210000,meeting_state:'cancelled',next_actions:['contact_support']}},
  {name:'meeting-ready',patch:{appointment_state:'confirmed',payment_state:'captured',captured_paise:210000,meeting_state:'ready',meet_url:'https://meet.google.com/abc-defg-hij',acknowledgement_state:'delivered',meeting_email_state:'provider_accepted',next_actions:['check_status']}},
  {name:'meeting-review',patch:{appointment_state:'confirmed',payment_state:'captured',captured_paise:210000,meeting_state:'needs_attention',acknowledgement_state:'bounced',meeting_email_state:'failed',next_actions:['contact_support','check_status']}},
  {name:'meeting-pending',patch:{appointment_state:'confirmed',payment_state:'captured',captured_paise:210000,meeting_state:'preparing',next_actions:['check_status']}},
  {name:'unavailable',unavailable:true},
 ];
 try{
  for(const path of ['/booking','/booking/receipt'])for(const scenario of cases){
   const context=await browser.newContext({viewport:{width:1280,height:900},reducedMotion:'reduce'}),page=await context.newPage();page.setDefaultTimeout(10000);
   const errors=[],calls=[];page.on('pageerror',error=>errors.push(error.message));
   const credential={version:1,installation_id:profile.installation_id,environment:profile.environment,request_id:reference,secret:'r1.current.'+'a'.repeat(43)};
   await context.addInitScript(({credential})=>sessionStorage.setItem(`appointment:${credential.installation_id}:${credential.environment}:booking:v1`,JSON.stringify(credential)),{credential});
   const saved={...receipt(reference),...scenario.patch};
   await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());if(url.origin!==proof.origin)return route.abort();
    if(!url.pathname.startsWith('/api/')||url.pathname==='/api/service-state')return route.continue();
    calls.push({path:url.pathname,body:request.postDataJSON()});
    const send=(value,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(value)});
    if(url.pathname==='/api/booking-policy')return send(policy());
    if(url.pathname==='/api/availability')return send(availability());
    if(url.pathname==='/api/checkout/status'){
     assert.equal(request.postDataJSON().request_id,reference);assert.equal(request.headers()['x-booking-receipt'],credential.secret);
     return scenario.unavailable?send({code:'temporarily_unavailable'},503):send(saved);
    }
    return send({code:'unexpected_local_fixture_request'},500);
   });
   try{
    await page.goto(proof.origin+path);
    if(scenario.unavailable){
     await page.locator('[role=alert]').filter({hasText:/\S/}).first().waitFor();
     assert.equal(await page.getByRole('heading',{name:/Your appointment is confirmed/}).count(),0);
    }else{
     await page.getByText(reference,{exact:false}).first().waitFor();
     await page.getByRole('heading',{name:({held:/Your time is reserved/,expired:/This reservation has ended|Let’s check the payment/,cancelled:/This appointment was cancelled|Your appointment is cancelled/,payment_review:/Your payment is being checked|Your payment needs a closer look/,confirmed:/Your appointment is confirmed/})[saved.appointment_state]}).waitFor();
     const fact=label=>page.locator('.abs-receipt dt').filter({hasText:new RegExp('^'+label+'$')}).locator('xpath=following-sibling::dd[1]');
     assert.equal(await fact('Payment recorded').innerText(),money(saved.captured_paise));
     assert.equal(await fact('Refund recorded').innerText(),money(saved.refunded_paise));
     assert.equal(await page.getByRole('button',{name:'Download appointment PDF',exact:true}).count(),0,'Legacy projections cannot enable actions without the current contract');
     if(saved.meet_url)assert.equal(await page.locator('a[href="'+saved.meet_url+'"]').count(),1);
     else assert.equal(await page.locator('a[href^="https://meet.google.com/"]').count(),0);
     if(path==='/booking/receipt'){
      await page.getByRole('button',{name:'Check status',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('button[type=button]')?.disabled);
     }
    }
    assert.ok(calls.some(call=>call.path==='/api/checkout/status'),scenario.name+' did not check the saved booking');
    assert.ok(calls.every(call=>['/api/booking-policy','/api/availability','/api/checkout/status'].includes(call.path)),'Merely reading a receipt must never create or resume an order');
    assert.deepEqual(errors,[]);
   }catch(error){throw new Error(JSON.stringify({path,scenario:scenario.name,calls:calls.map(call=>call.path),errors,displayed:await page.locator('body').innerText()})+'\n'+error.message,{cause:error});}
   finally{await context.close();}
  }
  const context=await browser.newContext(),page=await context.newPage();page.setDefaultTimeout(10000);
  await context.route('**/*',route=>new URL(route.request().url()).origin===proof.origin?route.continue():route.abort());
  await page.goto(proof.origin+'/booking/receipt');await page.getByText('This browser has no saved receipt.',{exact:false}).waitFor();
  assert.equal(await page.getByRole('button',{name:'Check status',exact:true}).isDisabled(),true);await context.close();
 }finally{await browser.close();await proof.close();}
});
