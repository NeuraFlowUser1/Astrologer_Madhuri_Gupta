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
const context=await browser.newContext(),errors=[];proof.setEnabled(true);
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
  return route.fulfill({status:response.status,contentType:'application/json',headers:{'cache-control':'no-store'},body:JSON.stringify(response.body)});
 });
 const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
 await page.goto(proof.origin+'/booking');await page.locator('#full_name,#name').waitFor();
 const date=(await bridge('test:date')).body.value;
 if(await page.locator('#appointment-date').count()){
  await page.locator('#appointment-date').fill(date);
 }else{
  for(let moves=0;!(await page.locator(`[data-booking-day="${date}"]`).count()) && moves<2;moves++)await page.getByRole('button',{name:'Next month',exact:true}).click();
  await page.locator(`[data-booking-day="${date}"]`).click();
 }
 await page.locator('#full_name,#name').fill('Synthetic Customer');await page.locator('#email').fill('Customer@example.com');await page.locator('#phone').fill('9876543210');
 if(await page.locator('#birth_date,#birthDate').count())await page.locator('#birth_date,#birthDate').fill('1990-01-01');
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
}finally{lines.close();await context.close();await browser.close();await proof.close();}
