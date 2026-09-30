/** Isolated browser fixtures only: all API requests are intercepted, no real sends. */
async page => {
 const browser=page.context().browser(),context=await browser.newContext({viewport:{width:1440,height:1000}}),p=await context.newPage();
 const errors=[];p.on('pageerror',e=>errors.push(e.message));
 const root='/mnt/d/coding/business/neuraflow-website-factory/03-client-projects/004-sarsa-jyotish-sansthan';
 const target='http://127.0.0.1:3014/#/contact';
 let record=null,startBodies=[],verifyCount=0,mode='normal';const resends=new Map(),resendBodies=[];
 const snapshot=()=>({code:'ok',request_id:record.request_id,state:record.received?'received':'awaiting_verification',generation:record.generation,
  server_now:new Date().toISOString(),code_expires_at:new Date(Date.now()+300000).toISOString(),resend_after:new Date(Date.now()-1000).toISOString(),sends_remaining:3-record.generation,verification_delivery:'accepted'});
 await context.route('**/api/**',async route=>{
  const request=route.request(),path=new URL(request.url()).pathname;
  if(!path.startsWith('/api/contact/'))return route.fulfill({status:503,json:{code:'booking_unavailable'}});
  const body=request.postDataJSON();
  if(mode==='unavailable')return route.fulfill({status:503,json:{code:'contact_unavailable'}});
  if(path.endsWith('/start')){
   startBodies.push(body);record||={...body,generation:1,received:false};
   if(mode==='lost-start'){mode='normal';return route.abort('failed');}
  }else if(!record)return route.fulfill({status:403,json:{code:'access_unavailable'}});
  else if(path.endsWith('/verify')){
   verifyCount++;
   if(body.code!=='654321')return route.fulfill({status:422,json:{code:'verification_incorrect'}});
   record.received=true;
   if(mode==='lost-verify'){mode='normal';return route.abort('failed');}
  }else if(path.endsWith('/resend')){
   resendBodies.push(body);if(!resends.has(body.operation_id)){record.generation=Math.min(3,record.generation+1);resends.set(body.operation_id,true);}
   if(mode==='lost-resend'){mode='normal';return route.abort('failed');}
  }
  return route.fulfill({status:200,json:snapshot()});
 });
 const fill=async()=>{
  await p.locator('#visitor-name').fill('Synthetic Visitor');await p.locator('#visitor-email').fill('synthetic@example.com');
  await p.locator('#message').fill('A synthetic question for browser verification.');
 };
 const submit=()=>p.getByRole('button',{name:'Continue to email verification',exact:true}).click();
 const assert=(value,message)=>{if(!value)throw Error(message);};
 try{
  await p.goto(target);await p.locator('#visitor-name').waitFor();
  await p.waitForFunction(()=>document.querySelector('#scene-listening').dataset.motionProgress==='1');
  await p.screenshot({path:root+'/design-review/2026-09-17/15-automatic-booking-plan/qa/contact-desktop-hero.png'});
  await submit();assert(startBodies.length===0,'Required fields did not prevent submit');
  await fill();await submit();await p.locator('#code').waitFor();
  assert(record.phone==='','Optional phone became required');
  await p.getByRole('button',{name:'Request a new code',exact:true}).click();await p.waitForFunction(()=>document.querySelector('#code')?.value==='');
  assert(record.generation===2,'Resend did not use next generation');
  mode='lost-resend';await p.getByRole('button',{name:'Request a new code',exact:true}).click();
  await p.getByRole('button',{name:'Retry the same request',exact:true}).waitFor();
  await p.reload();await p.locator('#code').waitFor();
  assert(record.generation===3,'Refresh repeated resend');
  assert(await p.evaluate(()=>!JSON.parse(sessionStorage.getItem('sarsa:004:enquiry-receipt:v1')).resend_id),'Completed resend identity was not cleared on recovery');
  assert(await p.getByRole('button',{name:'Request a new code',exact:true}).isDisabled(),'Three generation cap ignored');
  const storage=await p.evaluate(()=>JSON.stringify(sessionStorage));
  assert(!storage.includes('synthetic@example.com')&&!storage.includes('Synthetic Visitor')&&!storage.includes('question'),'Personal data persisted');
  await p.locator('#code').fill('000000');await p.getByRole('button',{name:'Verify & send enquiry',exact:true}).click();
  await p.getByText('That code did not match.',{exact:false}).waitFor();
  assert(!record.received,'Wrong code saved enquiry');
  await p.locator('#code').fill('654321');await p.getByRole('button',{name:'Verify & send enquiry',exact:true}).click();
  await p.getByText('ENQUIRY RECEIVED',{exact:true}).waitFor();
  assert(verifyCount===2,'Duplicate verification');
  assert(await p.locator('#outcome').evaluate(el=>{for(let e=el;e;e=e.parentElement)if(Number(getComputedStyle(e).opacity)===0||getComputedStyle(e).visibility==='hidden')return false;return true;}),'Received result has an invisible ancestor');
  await p.locator('#outcome').scrollIntoViewIfNeeded();await p.waitForFunction(()=>document.querySelector('#scene-desk').dataset.motionProgress==='1');await p.locator('#outcome').scrollIntoViewIfNeeded();await p.screenshot({path:root+'/design-review/2026-09-17/15-automatic-booking-plan/qa/contact-desktop-received.png'});
  await p.reload();await p.getByText('ENQUIRY RECEIVED',{exact:true}).waitFor();assert(startBodies.length===1,'Refresh created another enquiry');
  // Lost start response retries the identical request, never a fresh identity.
  await p.evaluate(()=>sessionStorage.clear());record=null;mode='lost-start';startBodies=[];
  await p.reload();await fill();await submit();await p.getByRole('button',{name:'Retry the same request',exact:true}).waitFor();
  await p.getByRole('button',{name:'Retry the same request',exact:true}).click();await p.locator('#code').waitFor();
  assert(startBodies.length===2&&JSON.stringify(startBodies[0])===JSON.stringify(startBodies[1]),'Uncertain start was replaced');
  // Lost verification response recovers by reading, without resubmitting a code.
  mode='lost-verify';await p.locator('#code').fill('654321');await p.getByRole('button',{name:'Verify & send enquiry',exact:true}).click();
  await p.getByRole('button',{name:'Check saved enquiry',exact:true}).waitFor();
  const verified=verifyCount;await p.getByRole('button',{name:'Check saved enquiry',exact:true}).click();
  await p.getByText('ENQUIRY RECEIVED',{exact:true}).waitFor();assert(verifyCount===verified,'Status resent verification');
  for(const width of [390,320]){
   await p.setViewportSize({width,height:844});await p.locator('#outcome').scrollIntoViewIfNeeded();await p.waitForFunction(()=>document.querySelector('#scene-desk').dataset.motionProgress==='1');await p.locator('#outcome').scrollIntoViewIfNeeded();
   assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Mobile horizontal overflow');
   await p.screenshot({path:root+`/design-review/2026-09-17/15-automatic-booking-plan/qa/contact-${width}-received.png`});
  }
  await p.evaluate(()=>sessionStorage.clear());record=null;mode='unavailable';await p.reload();await fill();
  await p.waitForFunction(()=>document.querySelector('#scene-desk').dataset.motionProgress==='1');
  await p.locator('#visitor-name').scrollIntoViewIfNeeded();await p.screenshot({path:root+'/design-review/2026-09-17/15-automatic-booking-plan/qa/contact-320-form.png'});await submit();
  await p.getByText('The enquiry form is temporarily unavailable.',{exact:false}).waitFor();
  assert(await p.getByText('ENQUIRY RECEIVED',{exact:true}).count()===0,'Unavailable service showed received');
  await p.emulateMedia({reducedMotion:'reduce'});await p.reload();await p.locator('#verification').waitFor();
  assert(await p.locator('.sarsa-contact.motion-off').count()===1,'Reduced motion ignored');
  assert(errors.length===0,'Page errors: '+errors.join(', '));
  return {passed:true,checks:['visible assembled sections','required fields','optional phone','wrong code','saved receipt','private storage','refresh recovery','identical start retry','lost verification response','lost resend recovery','390 and 320px','unavailable service','reduced motion'],pageErrors:errors};
 }finally{await context.close();}
}
