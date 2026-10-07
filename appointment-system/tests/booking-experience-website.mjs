/** Actual built pages, local signed OFF boundary and synthetic API/provider contracts. */
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {randomUUID} from 'node:crypto';
import {displayProof} from '../tools/checks/website-display.mjs';
import {localDate} from '../browser/display-formatting.mjs';

const project=process.env.BOOKING_WEBSITE_PROOF_PROJECT,site=process.env.BOOKING_WEBSITE_PROOF_SITE;
if(!project||!site)throw Error('Explicit local project and built website required.');
const {chromium}=await import(pathToFileURL(resolve(site,'node_modules/playwright-core/index.mjs')).href);
const headed=process.env.BOOKING_EXPERIENCE_HEADED==='1';
const browser=await chromium.launch({headless:!headed,executablePath:process.env.BOOKING_CHROME_EXECUTABLE,args:['--no-sandbox']});
const proof=await displayProof(project,site,{enabled:true});
const evidence=resolve(process.env.BOOKING_EXPERIENCE_EVIDENCE||'/tmp/booking-experience-browser');mkdirSync(evidence,{recursive:true});
const business=JSON.parse(readFileSync(resolve(project,'appointment-settings/business-settings.json')));
const otp=process.env.BOOKING_EXPERIENCE_OTP!=='off';
business.booking_verification.email=otp;business.required_contacts=otp?['email','phone']:['phone'];
const errors=[],calls=[],assets=[],checks=[],now=new Date(),tomorrow=new Date(now);tomorrow.setUTCDate(tomorrow.getUTCDate()+1);
const day=localDate(tomorrow,business.timezone),service=business.services.find(s=>s.enabled),id=project.endsWith('003')?'003':'004';
const quote='a'.repeat(64),binding='b'.repeat(64),operation=randomUUID();let status=null;
const check=(label)=>{checks.push(label);console.log(label);},accessibility=[];
const context=await browser.newContext({viewport:{width:1440,height:900}});
await context.addInitScript(()=>{window.__testPayment={opened:0};window.Razorpay=function(options){this.open=()=>{window.__testPayment.opened++;window.__testPayment.options=options;};this.close=()=>{};};});
await context.route('**/*',async route=>{
 const request=route.request(),url=new URL(request.url());
 if(url.origin!==proof.origin)return route.abort();
 if(!url.pathname.startsWith('/api/')){assets.push(url.pathname);return route.continue();}
 if(url.pathname==='/api/service-state')return route.continue();
 const body=request.postData()?request.postDataJSON():null;calls.push({path:url.pathname,body});
 let reply;
 if(url.pathname==='/api/booking-policy')reply={policy:business,quote_version:quote,booking_verification_policy_hash:binding,
  server_now:new Date().toISOString(),schedule_browsing_open:true,receipt_access:{version:1,key_id:'current'}};
 else if(url.pathname==='/api/availability'){
  const selected=business.services.find(s=>s.id===url.searchParams.get('service_id')),date=url.searchParams.get('day');
  const starts=date+'T06:00:00Z',ends=new Date(Date.parse(starts)+selected.duration_minutes*60000).toISOString();
  reply={date,server_now:new Date().toISOString(),service:{...selected,amount_paise:selected.pricing.amount_paise,questions:1,currency:'INR',timezone:business.timezone,quote_version:quote},
   slots:Date.parse(starts)>Date.now()?[{starts_at:starts,ends_at:ends}]:[]};
 }else if(url.pathname==='/api/checkout-context')reply={ready:true,renewed:false};
 else if(url.pathname.startsWith('/api/booking-verification/'))reply=url.pathname.endsWith('verify')?
  {code:'ok',state:'verified',booking_verification_policy_hash:binding,verification_grant:'bv1.current.'+'a'.repeat(43),expires_at:new Date(Date.now()+300000).toISOString()}:
  {code:'ok',state:'awaiting_verification',challenge_id:operation,generation:1,booking_verification_policy_hash:binding,expires_at:new Date(Date.now()+300000).toISOString()};
 else if(url.pathname==='/api/checkout/status')reply=status;
 else if(url.pathname==='/api/checkout'){
  const booked=business.services.find(s=>s.id===body.service_id);
  status={request_id:body.request_id,appointment_state:'held',order_state:'ready',payment_state:'unobserved',service_name:booked.name,amount_paise:booked.pricing.amount_paise*body.questions,
   currency:'INR',captured_paise:0,refunded_paise:0,starts_at:body.starts_at,ends_at:new Date(Date.parse(body.starts_at)+booked.duration_minutes*60000).toISOString(),
   timezone:business.timezone,server_now:new Date().toISOString(),hold_expires_at:new Date(Date.now()+900000).toISOString(),next_actions:['resume_payment','check_status'],
   booking_revision:1,meeting_mode:'google_meet',meeting_state:'not_created',meet_url:null,acknowledgement_state:body.email===null?'not_requested':'pending',meeting_email_state:body.email===null?'not_requested':'pending',
   email_copy:{operation_id:null,booking_revision:null,state:'not_requested',has_booking_email:body.email!==null,target_hint:null,next_request_at:null,remaining_requests:3,can_request:false,blocked_reason:'booking_unavailable'}};
  reply={receipt:status,checkout:{key_id:'rzp_live_synthetic',order_id:'order_synthetic',amount_paise:status.amount_paise,currency:'INR',email_optional:body.email===null}};
 }else if(url.pathname==='/api/checkout/verify-payment'){
  status={...status,appointment_state:'confirmed',payment_state:'captured',captured_paise:status.amount_paise,meeting_state:'ready',meet_url:'https://meet.google.com/abc-defg-hij',next_actions:['check_status'],
   email_copy:{...status.email_copy,can_request:true,blocked_reason:null}};reply={receipt:status};
 }else if(url.pathname==='/api/checkout/email-details'){
  status={...status,email_copy:{...status.email_copy,operation_id:body.operation_id,booking_revision:1,state:'pending',target_hint:'c***@example.test',remaining_requests:2,can_request:false,blocked_reason:'delivery_pending'}};
  reply={code:'receipt_copy_accepted',request_id:body.request_id,operation_id:body.operation_id,booking_revision:1,email_copy:status.email_copy};
 }else return route.fulfill({status:404,contentType:'application/json',body:'{"code":"fixture_route_unavailable"}'});
 return route.fulfill({status:200,contentType:'application/json',headers:{'cache-control':'no-store'},body:JSON.stringify(reply)});
});
const page=await context.newPage();if(headed)await (await context.newCDPSession(page)).send('Emulation.setFocusEmulationEnabled',{enabled:false});page.on('pageerror',error=>errors.push(error.message));
async function pickerFits(label){
 const caption=label==='birth-date'?'Date of birth (Optional)':label==='birth-time'?'Exact time of birth (Optional)':'Appointment date';
 for(const [width,height] of [[320,740],[390,844],[768,1024],[1440,900]]){
  await page.keyboard.press('Escape');await page.locator('.abs-booking-picker').waitFor({state:'hidden'});
  await page.setViewportSize({width,height});
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  await page.waitForTimeout(200);
  await page.locator('.abs-date-picker').filter({has:page.getByText(caption,{exact:true})}).locator('.abs-date-group').click();
  await page.waitForTimeout(180);
  writeFileSync(resolve(evidence,label+'-'+width+'-geometry.json'),JSON.stringify(await page.evaluate(()=>({
   picker:{rect:document.querySelector('.abs-booking-picker')?.getBoundingClientRect().toJSON(),style:document.querySelector('.abs-booking-picker')?.getAttribute('style')},
   portal:document.querySelector('.abs-booking-picker')?.offsetParent?.getBoundingClientRect().toJSON(),
   viewport:{width:innerWidth,height:innerHeight,visual:visualViewport.height,y:scrollY}})),null,2));
  await page.waitForFunction(()=>{
   const node=document.querySelector('.abs-booking-picker');if(!node)return false;
   const r=node.getBoundingClientRect();
   return r.width>0 && r.left>=11 && r.right<=innerWidth-11 && r.top>=11 && r.bottom<=innerHeight-11;
  },null,{timeout:3000});
  const r=await page.locator('.abs-booking-picker').boundingBox();
  assert.ok(r.x>=11 && r.x+r.width<=width-11 && r.y>=11 && r.y+r.height<=height-11,label+' stays in the viewport');
  await page.screenshot({path:resolve(evidence,id+'-'+label+'-'+width+'.png'),fullPage:false});
 }
}
async function a11y(label,selectors){
 if(!process.env.BOOKING_EXPERIENCE_AXE)return;
 await page.waitForFunction(()=>[...document.querySelectorAll('.abs-booking-picker')].every(n=>parseFloat(getComputedStyle(n).opacity)>.99 && n.getAnimations().every(a=>a.playState!=='running')));
 if(!await page.evaluate(()=>!!window.axe))await page.addScriptTag({path:process.env.BOOKING_EXPERIENCE_AXE});
 const result=await page.evaluate(async selectors=>window.axe.run({include:selectors},{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa','wcag22aa']}}),selectors);
 accessibility.push({label,violations:result.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),incomplete:result.incomplete.map(v=>v.id)});
 assert.deepEqual(result.violations.map(v=>v.id),[],label+' accessibility');
}
try{
 await page.goto(proof.origin+'/booking');await page.locator('#full_name,#name').waitFor();
 await page.locator('#full_name,#name').fill('Uncommitted synthetic draft');await page.reload();
 await page.locator('#full_name,#name').waitFor();assert.equal(await page.locator('#full_name,#name').inputValue(),'');
 check('Deliberate refresh starts an empty draft');
 if(id==='003')await page.waitForFunction(()=>[...document.querySelectorAll('.astro-booking-form > *, .astro-booking-form .contents > *')].every(n=>parseFloat(getComputedStyle(n).opacity)>.99));
 for(const width of [390,1440]){
  await page.setViewportSize({width,height:width===390?844:900});
  await page.screenshot({path:resolve(evidence,id+'-'+width+'-form.png'),fullPage:true});
 }
 await a11y('Unfilled booking form',['#booking-form','.sarsa-booking form','.sarsa-booking .journey-nav']);
 if(id==='004'){
  const radios=page.locator('input[name="service"]');await radios.first().focus();const initial=await page.evaluate(()=>window.scrollY);
  await radios.first().press('ArrowRight');await page.waitForTimeout(300);assert.ok(Math.abs(await page.evaluate(()=>window.scrollY)-initial)<10);
  const selected=page.locator('input[name="service"]:checked');await selected.press('Enter');await page.waitForTimeout(350);
  assert.equal(await page.locator('#appointment-title').evaluate(n=>document.activeElement===n),true);
  assert.ok(await page.locator('.journey-nav').evaluate(n=>Math.abs(n.getBoundingClientRect().top-parseFloat(getComputedStyle(n).top))<2));
  check('Arrow navigation stays in services; deliberate Enter advances with the strip below the header');
 }
 if(id==='003'){
  await page.locator('.abs-date-picker').filter({has:page.getByText('Date of birth (Optional)',{exact:true})}).locator('.abs-date-group').click();
  const jump=page.locator('.abs-calendar-jump');await jump.waitFor();
  await jump.getByLabel('Year',{exact:true}).fill('2000');
  await jump.getByLabel('Month',{exact:true}).selectOption('2');
  await pickerFits('birth-date');
  writeFileSync(resolve(evidence,'picker-geometry.json'),JSON.stringify(await page.evaluate(()=>({
   picker:{rect:document.querySelector('.abs-booking-picker')?.getBoundingClientRect().toJSON(),style:document.querySelector('.abs-booking-picker')?.getAttribute('style')},
   anchor:document.querySelector('.abs-date-group')?.getBoundingClientRect().toJSON(),viewport:{height:innerHeight,visual:visualViewport.height,y:scrollY},
   body:{rect:document.body.getBoundingClientRect().toJSON(),position:getComputedStyle(document.body).position}})),null,2));
  await page.screenshot({path:resolve(evidence,id+'-birth-date-open.png'),fullPage:false});
  await page.locator('.abs-calendar-cell:not([data-outside-month])').filter({hasText:/^29$/}).click();
  await page.locator('.abs-date-picker').filter({has:page.getByText('Exact time of birth (Optional)',{exact:true})}).locator('.abs-date-group').click();
  assert.equal(await page.getByLabel('Minute',{exact:true}).locator('option').count(),60);
  await pickerFits('birth-time');
  await page.getByLabel('Hour',{exact:true}).selectOption('12');await page.getByLabel('Minute',{exact:true}).selectOption('59');await page.getByLabel('AM / PM',{exact:true}).selectOption('AM');
  await a11y('Open birth time',['.abs-booking-picker']);
  await page.screenshot({path:resolve(evidence,id+'-birth-time-open.png'),fullPage:false});
  await page.getByRole('button',{name:'Apply',exact:true}).click();check('Birth controls support a direct year jump, leap day and all 60 minutes');
 }
 await page.locator('.abs-date-picker').filter({has:page.getByText('Appointment date',{exact:true})}).locator('.abs-date-group').click();
 const cells=page.getByRole('gridcell');await cells.first().waitFor();
 await a11y('Open calendar',['.abs-booking-picker']);
 await pickerFits('appointment-date');check('Date and time menus remain fully within phone, tablet and desktop screens');
 await page.screenshot({path:resolve(evidence,id+'-appointment-date-open.png'),fullPage:false});
 const targetDay=Number(day.slice(-2));const cell=page.locator('.abs-calendar-cell').filter({hasText:new RegExp('^'+targetDay+'$')}).filter({visible:true});
 if(!await cell.count()||await cell.first().getAttribute('data-disabled')!==null)await page.getByRole('button',{name:'Next month',exact:true}).click();
 await page.locator('.abs-calendar-cell').filter({hasText:new RegExp('^'+targetDay+'$')}).filter({visible:true}).first().click();
 await page.locator('input[name="time"],button[data-booking-time]').first().waitFor();check('Whole-field date control opens and selects an authoritative day');
 await page.locator('#full_name,#name').fill('Synthetic Customer');if(otp)await page.locator('#email').fill('Customer@example.test');await page.locator('#phone').fill('9876543210');
 assert.equal(await page.locator('#email').evaluate(n=>n.required),otp);
 if(!otp)assert.match(await page.locator('label[for="email"]').innerText(),/optional/i);
 const slot=page.locator('input[name="time"],button[data-booking-time]').first();if(await slot.evaluate(node=>node.tagName==='INPUT'))await slot.check();else await slot.click();
 if(otp){await page.getByRole('button',{name:'Send email code',exact:true}).click();await page.getByLabel('Email verification code',{exact:true}).fill('123456');}
 const selectedBefore=await page.evaluate(()=>({day:document.querySelector('input[name="bookingDate"],input[name="appointmentDate"]')?.value,
  slot:document.querySelector('input[name="time"]:checked')?.value||document.querySelector('button[data-booking-time][aria-pressed="true"]')?.dataset.bookingTime}));
 assert.equal(selectedBefore.day,day);assert.equal(typeof selectedBefore.slot,'string');assert.ok(selectedBefore.slot.length>0);
 if(headed)await (await context.newCDPSession(page)).send('Emulation.setFocusEmulationEnabled',{enabled:false});
 await page.evaluate(()=>{window.__tabEvents=[];window.addEventListener('focus',()=>window.__tabEvents.push('focus'));
  document.addEventListener('visibilitychange',()=>window.__tabEvents.push(document.visibilityState));});
 const tab=await context.newPage();if(headed)await (await context.newCDPSession(tab)).send('Emulation.setFocusEmulationEnabled',{enabled:false});await tab.goto('about:blank');if(headed)await (await context.newCDPSession(tab)).send('Emulation.setFocusEmulationEnabled',{enabled:false});await tab.bringToFront();await page.waitForTimeout(300);await page.bringToFront();await page.waitForTimeout(300);await tab.close();
 const nativeEvents=await page.evaluate(()=>window.__tabEvents);
 if(headed)assert.ok(nativeEvents.length>0,'A visible Chrome tab change must emit native browser events');
 const reads=calls.length;await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
 await page.waitForTimeout(600);if(otp)assert.equal(await page.getByLabel('Email verification code',{exact:true}).inputValue(),'123456');
 assert.equal(await page.locator('#full_name,#name').inputValue(),'Synthetic Customer');assert.equal(await page.locator('#email').inputValue(),otp?'Customer@example.test':'');
 assert.equal(await page.locator('#phone').inputValue(),'9876543210');
 assert.deepEqual(await page.evaluate(()=>({day:document.querySelector('input[name="bookingDate"],input[name="appointmentDate"]')?.value,
  slot:document.querySelector('input[name="time"]:checked')?.value||document.querySelector('button[data-booking-time][aria-pressed="true"]')?.dataset.bookingTime})),selectedBefore);
 assert.ok(calls.slice(reads).filter(c=>c.path==='/api/booking-policy').length<=1);check('Focus return preserves personal details, chosen time and typed email code');
 if(otp){await page.getByRole('button',{name:'Verify code',exact:true}).click();await page.getByText('Your email address is verified.',{exact:true}).waitFor();}
 await page.locator('input[type="checkbox"]').check();await page.locator('button[type="submit"]').click();await page.waitForFunction(()=>window.__testPayment.opened===1);
 if(!otp){assert.equal(calls.find(c=>c.path==='/api/checkout').body.email,null);assert.equal(await page.evaluate(()=>window.__testPayment.options.hidden.email),true);}
 await page.evaluate(()=>window.__testPayment.options.handler({razorpay_order_id:'order_synthetic',razorpay_payment_id:'pay_synthetic',razorpay_signature:'a'.repeat(64)}));
 await page.getByRole('heading',{name:'Your appointment is confirmed',exact:true}).waitFor();check('The real page completes its booking using the shared contract');
 assert.equal(await page.getByRole('link',{name:'Open Google Meet ↗',exact:true}).getAttribute('rel'),'noopener noreferrer');
 assert.equal(assets.filter(path=>/fontkit|receipt-pdf|\.ttf$/i.test(path)).length,0,'PDF code and font are not loaded before the deliberate document request');
 await page.getByRole('button',{name:'Download appointment PDF',exact:true}).click();await page.getByRole('link',{name:'Download PDF',exact:true}).waitFor();
 assert.ok(assets.some(path=>/fontkit/i.test(path)));assert.ok(assets.some(path=>/\.ttf$/i.test(path)));
 check('Document tools and the rupee font load only after the PDF request');
 const download=page.waitForEvent('download');await page.getByRole('link',{name:'Download PDF',exact:true}).click();const file=await download;
 await file.saveAs(resolve(evidence,'appointment-'+id+'.pdf'));check('A real PDF is downloadable from fresh owned receipt facts');
 await page.getByRole('button',{name:'Email appointment details',exact:true}).click();
 if(!otp){await page.getByLabel('Email address for this copy',{exact:true}).fill('copy@example.test');await page.getByRole('button',{name:'Send email copy',exact:true}).click();}
 await page.getByText('Your email-copy request is saved. Delivery status is shown below.',{exact:true}).waitFor();
 assert.equal(calls.filter(c=>c.path==='/api/checkout/email-details').length,1);check('One deliberate email request creates one copy operation');
 for(const width of [320,390,768,1440,1920]){
  await page.setViewportSize({width,height:900});await page.waitForTimeout(100);
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
  await page.screenshot({path:resolve(evidence,id+'-'+width+'-receipt.png'),fullPage:false});
 }
 check('Receipt layout fits 320, 390, 768, 1440 and 1920 pixel widths');
 await a11y('Confirmation',['.abs-receipt']);
 proof.setEnabled(false);await page.evaluate(()=>window.dispatchEvent(new Event('focus')));
 await page.waitForFunction(()=>!document.body.innerText.includes('Your appointment is confirmed'));
 assert.equal(await page.locator('a[href^="blob:"]').count(),0);check('OFF removes the receipt and prepared document links');
 for(const path of [...new Set(assets.filter(path=>/fontkit|receipt-pdf|\.ttf$/i.test(path)))]){
  const response=await context.request.get(proof.origin+path);assert.equal(response.status(),404,'OFF guards document asset '+path);
 }
 assert.equal(await page.locator('.abs-picker-portal').count(),0,'OFF disposes the calendar portal containers');
 assert.deepEqual(errors,[]);
 writeFileSync(resolve(evidence,id+'-result.json'),JSON.stringify({project:id,otp,checks,passed:checks.length,browser_errors:errors,accessibility,headed,native_tab_events:nativeEvents,handler_injection:true,assets:[...new Set(assets)],real_provider_calls:0},null,2)+'\n');
 console.log(JSON.stringify({project:id,passed:checks.length,errors:0,evidence}));
}catch(error){
 writeFileSync(resolve(evidence,id+'-failure.json'),JSON.stringify({error:error.message,checks,browser_errors:errors,
  page_text:await page.locator('body').innerText(),calls,accessibility},null,2)+'\n');
 await page.screenshot({path:resolve(evidence,id+'-failure.png'),fullPage:true});throw error;
}finally{await context.close();await browser.close();await proof.close();}
