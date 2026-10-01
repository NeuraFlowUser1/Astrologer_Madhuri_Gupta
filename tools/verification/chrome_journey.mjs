import * as fs from 'node:fs';
import * as path from 'node:path';
// A Playwright function used by chrome_run.mjs with the fixture directory.
// Application API calls reach real isolated PostgreSQL. Only Google identity is
// intercepted; its actual bound callback, secure cookie and session are retained.
export default async function journey(page, artifactsDirectory) {
  const root = (artifactsDirectory || [
    path.resolve('tools/verification/artifacts'),
    path.resolve('03-client-projects/004-sarsa-jyotish-sansthan/tools/verification/artifacts'),
  ].find(folder=>fs.existsSync(path.join(folder,'chrome-fixture.json')))) + '/';
  const fixture = JSON.parse(fs.readFileSync(root + 'chrome-fixture.json', 'utf8'));
  const browser = page.context().browser();
  const context = await browser.newContext({ignoreHTTPSErrors:true});
  const errors=[];
  context.on('page', p=>p.on('pageerror', e=>errors.push(e.message)));
  await context.route('**/*', route=>{
    const url=new URL(route.request().url());
    if(url.origin===fixture.origin)return route.continue();
    // Fonts or decorative third-party media are unnecessary for this functional
    // proof. Fail closed on external traffic; never forward a cookie or API body.
    if(url.origin!=='https://accounts.google.com'||url.pathname!=='/o/oauth2/v2/auth')return route.abort();
    const callback=new URL(fixture.origin+'/api/studio/sign-in/callback');
    callback.searchParams.set('state',url.searchParams.get('state'));
    callback.searchParams.set('code','synthetic-'+url.searchParams.get('login_hint'));
    return route.fulfill({status:302,headers:{location:callback.href},body:''});
  });
  const staff=await context.newPage();
  const wait = async (p,id,text) => p.waitForFunction(({id,text})=>document.querySelector(id)?.textContent.includes(text),{id,text});
  const assert = (value, message) => {if(!value)throw Error(message);};
  try {
    await staff.goto(fixture.origin+'/studio');
    await staff.locator('[data-role="client"]').click();
    await wait(staff,'#status','You are signed in.');
    await staff.locator('#calendar-day').fill(fixture.day);
    await staff.locator('#calendar-view button').click();
    await wait(staff,'#calendar-status','Saved reservations');
    assert(await staff.locator('#calendar-items li').count()===1,'Expected the single seeded appointment.');
    await staff.locator('#booking-reference').fill(fixture.reference);
    await staff.locator('#booking-lookup button').click();
    await wait(staff,'#booking-support-status','Saved booking found');
    await staff.locator('#support-action').selectOption('contact_correction');
    await staff.locator('#support-email').fill('corrected@example.com');
    await staff.locator('#support-phone').fill('+919876543211');
    await staff.locator('#support-payment').fill(fixture.payment);
    await staff.locator('#support-reason').fill('Isolated synthetic customer details correction');
    await staff.locator('#support-verified').check();
    await staff.locator('#booking-support-change button').click();
    await wait(staff,'#booking-support-status','Contact details corrected');
    const code=(await staff.locator('#support-code').textContent()).trim();
    assert(/^\d{8}$/.test(code),'Expected the actual generated recovery code.');
    const customer=await context.newPage();
    await customer.goto(fixture.origin+'/booking-help');
    await customer.locator('#recovery-reference').fill(fixture.reference);
    await customer.locator('#recovery-code').fill(code);
    await customer.locator('#recovery-form button').click();
    await wait(customer,'#recovery-status','Your access has been restored');
    await customer.locator('#recovery-open').click();
    await wait(customer,'#receipt-title','Your appointment is confirmed.');
    assert((await customer.locator('#receipt-facts').textContent()).includes('₹2,500'),'The regular fee is unchanged by recovery.');
    const rejected=await customer.evaluate(async fixture=>(await fetch('/api/checkout/status',{
      method:'POST',headers:{'Content-Type':'application/json','X-Booking-Receipt':fixture.old_receipt},
      body:JSON.stringify({request_id:fixture.reference})})).status,fixture);
    assert(rejected===403,'Old receipt must be rejected.');
    await staff.locator('#booking-reference').fill(fixture.reference);
    await staff.locator('#booking-lookup button').click();
    await wait(staff,'#booking-support-status','Saved booking found');
    await staff.locator('#booking-support-manage').click();
    await staff.locator('#appointment-start').waitFor({state:'visible'});
    await staff.locator('#appointment-start').fill(fixture.moved);
    await staff.locator('#appointment-move-reason').fill('Isolated synthetic reschedule');
    await staff.locator('#appointment-reschedule button').click();
    await wait(staff,'#appointment-status','Appointment moved.');
    await customer.reload();
    await wait(customer,'#receipt-title','Your appointment is confirmed.');
    await staff.locator('#calendar-items button').click();
    await staff.locator('#appointment-reason').waitFor({state:'visible'});
    await staff.locator('#appointment-reason').fill('Isolated synthetic cancellation');
    await staff.locator('#appointment-ack').check();
    await staff.locator('#appointment-cancel button').click();
    await wait(staff,'#appointment-status','Appointment cancelled.');
    await customer.reload();
    await wait(customer,'#receipt-title','Your appointment is cancelled.');
    await staff.locator('#closure-start').fill(fixture.closure_start);
    await staff.locator('#closure-end').fill(fixture.closure_end);
    await staff.locator('#closure-reason').fill('Isolated synthetic commitment');
    await staff.locator('#calendar-close button').click();
    await wait(staff,'#calendar-action-status','That time is now blocked.');
    await staff.getByRole('button',{name:'Make this time available',exact:true}).click();
    await staff.locator('#reopen-reason').fill('Isolated synthetic reopening');
    await staff.locator('#calendar-reopen button[type="submit"]').click();
    await wait(staff,'#calendar-action-status','That unavailable period is now open again.');
    await staff.setViewportSize({width:390,height:844});
    assert(await staff.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Staff page overflows phone width.');
    await customer.setViewportSize({width:390,height:844});
    assert(await customer.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Receipt overflows phone width.');
    assert(errors.length===0,'Unexpected Chrome page errors: '+errors.join('; '));
    const result={id:fixture.id,passed:true,browser:'Chromium',journeys:['bound staff sign-in','calendar visibility','contact correction','receipt recovery','old access rejection','reschedule','cancellation','blocked-time reopening'],mobile_overflow:false,page_errors:errors};
    fs.writeFileSync(root+'chrome-completed.json',JSON.stringify(result));
    return {passed:true,journeys:result.journeys,mobile_overflow:false,page_errors:errors};
  } finally {await context.close();}
}
