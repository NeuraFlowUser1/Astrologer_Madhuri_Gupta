import {createInterface} from 'node:readline';
import assert from 'node:assert/strict';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {displayProof} from '../tools/checks/website-display.mjs';
const root=process.env.BOOKING_WEBSITE_PROOF_PROJECT,site=process.env.BOOKING_WEBSITE_PROOF_SITE;
if(!root || !site)throw Error('Explicit isolated project and site required');
const lines=createInterface({input:process.stdin,crlfDelay:Infinity}),pending=new Map();let sequence=0;
lines.on('line',line=>{const value=JSON.parse(line),resolve=pending.get(value.id);pending.delete(value.id);resolve(value);});
const bridge=(path,options={})=>new Promise(resolve=>{const id=++sequence;pending.set(id,resolve);process.stdout.write(JSON.stringify({id,path,...options})+'\n');});
const {chromium}=await import(pathToFileURL(resolve(site,'node_modules/playwright-core/index.mjs')).href);
const browser=await chromium.launch({headless:true,executablePath:process.env.BOOKING_CHROME_EXECUTABLE,args:['--no-sandbox']}),proof=await displayProof(root,site);
const settings=(await bridge('test:settings')).body,context=await browser.newContext({viewport:{width:1280,height:900},reducedMotion:'reduce'});
let redemptions=0;const errors=[];
try{
 proof.setEnabled(true);
 await context.route('**/*',async route=>{
  const request=route.request(),url=new URL(request.url());if(url.origin!==proof.origin)return route.abort();
  if(!url.pathname.startsWith('/api/') || url.pathname==='/api/service-state')return route.continue();
  if(!['/api/booking-policy','/api/checkout/status','/api/checkout/recover-receipt'].includes(url.pathname))return route.abort();
  const body=request.postDataJSON(),secret=request.headers()['x-booking-receipt'];
  const result=await bridge(url.pathname,{...(body?{body}:{}),headers:secret?{'X-Booking-Receipt':secret}:{}});
  if(url.pathname.endsWith('/recover-receipt')){
   redemptions++;assert.equal(result.status,200,JSON.stringify(result.body));
   // Server succeeded. The browser never receives that response.
   return route.abort('connectionreset');
  }
  return route.fulfill({status:result.status,contentType:'application/json',headers:{'cache-control':'no-store'},body:JSON.stringify(result.body)});
 });
 const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
 await page.goto(proof.origin+'/booking-help');await page.getByLabel('Booking request reference').fill(settings.reference);
 await page.getByLabel('Eight-digit access code').fill(settings.code);await page.getByRole('button',{name:'Open my booking',exact:true}).click();
 await page.waitForFunction(()=>document.querySelector('[role="status"]')?.textContent?.trim());
 await page.reload();await page.waitForURL('**/booking/receipt');
 await page.getByRole('heading',{name:'Your appointment is confirmed',exact:true}).waitFor();assert.equal(redemptions,1);assert.deepEqual(errors,[]);
 await page.screenshot({path:'/tmp/abs-recovered-receipt-'+(site===root?'astro':'sarsa')+'.png',fullPage:false});
 proof.setEnabled(false);const response=await page.goto(proof.origin+'/booking-help');assert.equal(response.status(),404);
 assert.equal(await page.getByLabel('Eight-digit access code').count(),0);
 await bridge('test:finished');
}finally{lines.close();await context.close();await browser.close();await proof.close();}
