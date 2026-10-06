/** Actual website enquiry forms, booking OFF, real local HTTP/SQL and synthetic mail codes. */
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
const settings=(await bridge('test:settings')).body,paths=settings.forms;
try{
 proof.setEnabled(false);
 for(const path of paths){
  const context=await browser.newContext({viewport:{width:path==='/'?800:1440,height:1000},reducedMotion:'reduce'}),errors=[];
  let requestID,starts=0,page;const outcomes=[];
  try{
   await context.route('**/*',async route=>{
    const request=route.request(),url=new URL(request.url());
    if(url.origin!==proof.origin)return route.abort();
    if(!url.pathname.startsWith('/api/') || url.pathname==='/api/service-state')return route.continue();
    if(!url.pathname.startsWith('/api/contact/'))return route.abort();
    const body=request.postDataJSON(),secret=request.headers()['x-enquiry-receipt'];
    const result=await bridge(url.pathname,{...(body?{body}:{}),headers:secret?{'X-Enquiry-Receipt':secret}:{}});
    outcomes.push({path:url.pathname,status:result.status,code:result.body.code});
    if(url.pathname.endsWith('/start') && result.status===200){requestID=result.body.request_id;starts++;}
    return route.fulfill({status:result.status,contentType:'application/json',headers:{'cache-control':'no-store',...result.headers},body:JSON.stringify(result.body)});
   });
   page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));await page.goto(proof.origin+path);
   await page.locator('#visitor-name,#form-name,#prashna-name,#name').first().waitFor();
   if(await page.locator('#visitor-name').count()){
    await page.locator('#visitor-name').fill('Synthetic Customer');await page.locator('#visitor-email').fill('customer@example.com');
    await page.locator('#message').fill('A synthetic website enquiry.');await page.getByRole('button',{name:/Continue to email verification/}).click();
   }else if(path==='/'){
    await page.locator('#form-name').fill('Synthetic Customer');await page.locator('#form-email').fill('customer@example.com');
    await page.locator('#form-dob').fill('1990-01-01');
    await page.getByRole('button',{name:'Select Service of Interest (Required)*',exact:true}).click();
    await page.locator('#home-inquiry-service-options button').first().click();
    await page.locator('form button[type="submit"]').click();
   }else if(path.startsWith('/services/')){
    await page.locator('#prashna-name').fill('Synthetic Customer');await page.locator('#prashna-email').fill('customer@example.com');
    await page.locator('#prashna-phone').fill('+919876543210');await page.locator('#prashna-location').fill('Synthetic city');
    await page.locator('#prashna-question').fill('A synthetic question for local browser proof.');await page.locator('#prashna-form button[type="submit"]').click();
   }else{
    await page.locator('#name').fill('Synthetic Customer');await page.locator('#email').fill('customer@example.com');await page.locator('#phone').fill('+919876543210');
    await page.locator('#message').fill('A synthetic website enquiry.');await page.getByRole('button',{name:'Submit Message',exact:true}).click();
   }
   await page.locator('#code,input[aria-label="Verification digit 1"]').waitFor();
   assert.ok(requestID,'The form must save its owned enquiry before asking for a code');
   // A reload loses all draft fields but retains only the owned reference.
   await page.reload();await page.locator('#code,input[aria-label="Verification digit 1"]').waitFor();
   if(await page.getByRole('dialog',{name:'Verify your enquiry'}).count()){
    // A lost draft must not prevent reopening a saved enquiry after dismissal.
    await page.getByRole('button',{name:'Close email verification',exact:true}).click();
    await page.getByRole('dialog',{name:'Verify your enquiry'}).waitFor({state:'hidden'});
    await page.getByRole('button',{name:'Continue saved enquiry',exact:true}).click();
    await page.getByLabel('Verification digit 1',{exact:true}).waitFor();
    assert.equal(starts,1,'Reopening must not create another enquiry');
   }
   const code=(await bridge('test:code',{request_id:requestID})).body.value;
   if(await page.locator('#code').count()){
    await page.locator('#code').fill(code);await page.getByRole('button',{name:/Verify & send enquiry/}).click();
    await page.locator('#outcome').waitFor();
   }else{
    for(let index=0;index<6;index++)await page.getByLabel('Verification digit '+(index+1),{exact:true}).fill(code[index]);
    await page.getByRole('button',{name:'Verify and send enquiry',exact:true}).click();
    await page.getByRole('dialog',{name:'Verify your enquiry'}).waitFor({state:'hidden'});
    if(path==='/contact')await page.getByRole('heading',{name:'Message Submitted!',exact:true}).waitFor();
    else if(path.startsWith('/services/'))await page.getByRole('heading',{name:'Question Submitted Successfully!',exact:true}).waitFor();
    else await page.getByText('Your inquiry has been saved.',{exact:false}).waitFor();
   }
   assert.equal(starts,1,'Reload must not create a second enquiry');assert.deepEqual(errors,[]);
   await page.screenshot({path:'/tmp/abs-enquiry-'+(settings.forms.length===1?'sarsa':'astro')+'-'+(path.replaceAll('/','-')||'home')+'.png',fullPage:false});
  }catch(error){
   if(page)await page.screenshot({path:'/tmp/abs-enquiry-website-failure.png',fullPage:false}).catch(()=>{});
   throw new Error(JSON.stringify({page:path,outcomes,errors,visibleStatus:page?await page.locator('[role="status"],[role="alert"]').allTextContents():[]})+' '+error.message);
  }finally{await context.close();}
 }
 await bridge('test:finished');
}finally{lines.close();await browser.close();await proof.close();}
