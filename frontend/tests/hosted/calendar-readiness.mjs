/** Test-only real-response delay proves the existing picker freshness contract. */
import assert from 'node:assert/strict';
import {writeFileSync} from 'node:fs';
import {chromium} from 'playwright-core';
const origin='https://www.sarsajyotishsansthan.com';
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE,args:['--no-sandbox','--disable-dev-shm-usage']});
const context=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});
let armed=false,held=false,release;
const gate=new Promise(resolve=>{release=resolve;}),requests=[],writes=[],errors=[];
await context.route('**/*',async route=>{
 const request=route.request(),url=new URL(request.url());
 if(!['GET','HEAD'].includes(request.method())){writes.push({path:url.pathname,method:request.method()});return route.abort();}
 if(url.origin===origin&&url.pathname==='/api/service-state'&&armed&&!held){
  held=true;await Promise.race([gate,new Promise(resolve=>setTimeout(resolve,5000))]);
 }
 return route.continue();
});
const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
page.on('response',async response=>{
 const url=new URL(response.url());if(url.origin!==origin||url.pathname!=='/api/availability')return;
 try{const value=await response.json();requests.push({utc:new Date().toISOString(),query:url.search,status:response.status(),slots:value.slots?.length,service:value.service?.id});}catch{}
});
const snapshot=()=>page.evaluate(()=>({utc:new Date().toISOString(),clinicTime:new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Kolkata',dateStyle:'full',timeStyle:'long'}).format(new Date()),checking:!!document.querySelector('.booking-checking'),draftDisabled:document.querySelector('.draft-fields')?.disabled,date:document.querySelector('.abs-date-group')?.innerText,readonly:document.querySelector('.abs-booking-picker [role="grid"]')?.getAttribute('aria-readonly')}));
try{
 await page.goto(origin+'/booking',{waitUntil:'domcontentloaded'});
 await page.locator('.draft-fields:not(:disabled) input[value="kundli-matching"]').waitFor({state:'attached',timeout:30000});
 const policy=await(await context.request.get(origin+'/api/booking-policy')).json();let choice;
 for(let offset=1;offset<=Math.min(policy.policy.horizon_days,10);offset++){
  const next=new Date(Date.parse(policy.server_now)+offset*86400000),day=new Intl.DateTimeFormat('en-CA',{timeZone:policy.policy.timezone,year:'numeric',month:'2-digit',day:'2-digit'}).format(next);
  const response=await context.request.get(origin+'/api/availability?'+new URLSearchParams({service_id:'kundli-matching',day,questions:'1'}));assert.equal(response.status(),200);
  const value=await response.json();if(value.slots.length){choice={day,label:new Intl.DateTimeFormat('en-GB',{timeZone:policy.policy.timezone,weekday:'long',day:'numeric',month:'long',year:'numeric'}).format(next)};break;}
 }
 assert(choice,'The inspected live policy must have a future available day.');
 await page.locator('.service-card').filter({hasText:'Kundli Matching'}).click();
 await page.locator('.abs-date-group button[aria-haspopup="dialog"]').click();armed=true;
 const bound=Date.now()+12000;while(!held&&Date.now()<bound)await page.waitForTimeout(25);assert(held,'The natural5second state read did not begin.');
 await page.waitForFunction(()=>document.querySelector('.abs-booking-picker [role="grid"]')?.getAttribute('aria-readonly')==='true');
 const during=await snapshot();assert(during.checking&&during.draftDisabled&&during.readonly==='true');
 await page.getByRole('button',{name:new RegExp(choice.label)}).click({timeout:2000});
 const afterReadonlyClick=await snapshot();assert.equal(afterReadonlyClick.date,during.date);assert.equal(afterReadonlyClick.readonly,'true');
 assert(!requests.some(request=>new URLSearchParams(request.query).get('day')===choice.day),'A readonly click unexpectedly fetched the future day.');
 release();
 await page.locator('.abs-booking-picker [role="grid"]:not([aria-readonly="true"])').getByRole('button',{name:new RegExp(choice.label)}).click();
 await page.locator('.slot-option').first().waitFor({state:'visible',timeout:20000});
 const fresh=await snapshot();assert(!fresh.checking&&!fresh.draftDisabled);assert.equal(fresh.date.replace(/\s/g,''),choice.day.split('-').reverse().join('/'));
 assert(requests.some(request=>new URLSearchParams(request.query).get('day')===choice.day&&request.status===200&&request.slots>0),'No actual successful future-day availability response.');
 assert.equal(writes.length,0);assert.equal(errors.length,0);
 const report={passed:true,scope:'Actual hosted picker; bounded test-only delay of one genuine GET, no response or product mutation',choice,during,afterReadonlyClick,fresh,requests,slots:await page.locator('.slot-option').count(),writes,errors,forcedWorkerRuns:0,customerSubmissions:0};
 writeFileSync(process.env.SARSA_CALENDAR_EVIDENCE||'/tmp/sarsa004-calendar-readiness.json',JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({passed:true,readonlyClickSafelyIgnored:true,editableCalendarCommitted:choice.day,actualFutureAvailability:true,slots:report.slots,writes:0}));
}finally{release();await browser.close();}
