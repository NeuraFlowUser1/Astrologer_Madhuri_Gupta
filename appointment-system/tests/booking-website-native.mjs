/** Built real project view -> intercepted same-origin request -> native app/SQL.
 * All non-fixture browser traffic is blocked. The provider window is synthetic.
 */
import {createInterface} from 'node:readline';
import assert from 'node:assert/strict';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {displayProof} from '../tools/checks/website-display.mjs';
const root=process.env.BOOKING_WEBSITE_PROOF_PROJECT,site=process.env.BOOKING_WEBSITE_PROOF_SITE;
if(!root || !site)throw Error('Explicit isolated project and site required.');
const lines=createInterface({input:process.stdin,crlfDelay:Infinity}),pending=new Map();let sequence=0;
lines.on('line',line=>{const value=JSON.parse(line),resolve=pending.get(value.id);pending.delete(value.id);resolve(value);});
const bridge=(path,options={})=>new Promise(resolve=>{const id=++sequence;pending.set(id,resolve);process.stdout.write(JSON.stringify({id,path,...options})+'\n');});
const {chromium}=await import(pathToFileURL(resolve(site,'node_modules/playwright-core/index.mjs')).href);
const browser=await chromium.launch({headless:true,executablePath:process.env.BOOKING_CHROME_EXECUTABLE,args:['--no-sandbox']}),proof=await displayProof(root,site);
const context=await browser.newContext(),errors=[],observations=[];proof.setEnabled(true);let page;
try{
 await context.addInitScript(()=>{
  window.__isolatedPayment={opened:0,options:null};
  window.Razorpay=function(options){this.open=()=>{window.__isolatedPayment.opened++;window.__isolatedPayment.options=options;};this.close=()=>{};};
 });
 await context.route('**/*',async route=>{
  const request=route.request(),url=new URL(request.url());
  if(url.origin!==proof.origin)return route.abort();
  if(!url.pathname.startsWith('/api/') || url.pathname==='/api/service-state')return route.continue();
  const body=request.postDataJSON(),secret=request.headers()['x-booking-receipt'];
  const response=await bridge(url.pathname+url.search,{...(body?{body}:{}),...(secret?{credential:{secret}}:{})});
  observations.push({path:url.pathname,status:response.status,code:response.body.code,
   appointment_state:response.body.receipt?.appointment_state||response.body.appointment_state});
  return route.fulfill({status:response.status,contentType:'application/json',headers:{'cache-control':'no-store'},body:JSON.stringify(response.body)});
 });
 page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
 await page.goto(proof.origin+'/booking');await page.locator('#full_name,#name').waitFor();
 const settings=(await bridge('test:settings')).body;
 const date=(await bridge('test:date')).body.value;
 await page.locator('.abs-date-picker').filter({has:page.getByText('Appointment date',{exact:true})}).locator('.abs-date-group').click();
 const targetDay=Number(date.slice(-2));await page.locator('.abs-calendar-cell').first().waitFor();
 let cells=page.locator('.abs-calendar-cell:not([data-outside-month]):not([data-disabled])').filter({hasText:new RegExp('^'+targetDay+'$')});
 for(let moves=0;!(await cells.count()) && moves<2;moves++)await page.getByRole('button',{name:'Next month',exact:true}).click();
 await cells.first().click();
 await page.locator('#full_name,#name').fill('Synthetic Customer');
 if(!settings.no_email)await page.locator('#email').fill('Customer@example.com');
 await page.locator('#phone').fill('9876543210');
 const slot=page.locator('input[name="time"],button[data-booking-time]').first();await slot.waitFor();
 if(await slot.evaluate(node=>node.tagName==='INPUT'))await slot.check();else await slot.click();
 const send=page.getByRole('button',{name:'Send email code',exact:true});
 if(await send.count()){
  await send.click();await page.getByLabel('Email verification code',{exact:true}).waitFor();
  const code=(await bridge('test:verification-code')).body.value;
  await page.getByLabel('Email verification code',{exact:true}).fill(code);await page.getByRole('button',{name:'Verify code',exact:true}).click();
  await page.getByText('Your email address is verified.',{exact:true}).waitFor();
 }
 await page.locator('input[type="checkbox"]').check();await page.locator('button[type="submit"]').click();
 await page.waitForFunction(()=>window.__isolatedPayment.opened===1);
 const order=await page.evaluate(()=>window.__isolatedPayment.options.order_id),signed=(await bridge('test:payment-capture',{order})).body;
 await page.evaluate(signed=>window.__isolatedPayment.options.handler(signed),signed);
 await page.getByRole('heading',{name:/Your appointment is confirmed/}).waitFor();
 assert.equal(await page.evaluate(()=>window.__isolatedPayment.opened),1);assert.deepEqual(errors,[]);
 await page.screenshot({path:process.env.BOOKING_WEBSITE_SCREENSHOT||'/tmp/abs-booking-website-proof.png',fullPage:false});
 proof.setEnabled(false);await page.waitForFunction(()=>!document.body.innerText.includes('Your appointment is confirmed'),undefined,{timeout:10000});
 assert.equal(await page.evaluate(()=>window.__isolatedPayment.opened),1);
 await bridge('test:finished');
}catch(error){
 process.stderr.write(JSON.stringify({error:error.message,observations,synthetic_page_text:page?await page.locator('body').innerText():null})+'\n');throw error;
}finally{lines.close();await context.close();await browser.close();await proof.close();}
