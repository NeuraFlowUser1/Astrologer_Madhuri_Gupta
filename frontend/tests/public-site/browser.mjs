/** Source-bound local browser qualification; all application responses are synthetic. */
import assert from 'node:assert/strict';
import {mkdirSync,readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {chromium,firefox,webkit} from 'playwright-core';
import {displayProof} from '../../../appointment-system/tools/checks/website-display.mjs';
import {fixture,paths,viewports,ready} from './browser-fixtures.mjs';
const project=resolve(import.meta.dirname,'../../..'),site=resolve(project,'frontend');
const output=resolve(process.env.SARSA_EVIDENCE_DIR||'/tmp/sarsa-public-browser');mkdirSync(output,{recursive:true});
const proof=await displayProof(project,site,{enabled:true}),report={kind:'local-built-source-synthetic-only',origin:proof.origin,started:new Date().toISOString(),layouts:[],interactions:[],accessibility:[],failures:[]};
const axePath=process.env.SARSA_AXE_SOURCE;
if(!axePath)throw Error('Set SARSA_AXE_SOURCE to the installed axe-core/axe.min.js testing tool.');
const axe=readFileSync(axePath,'utf8');
async function check(name,run){try{await run();report.interactions.push({name,status:'passed'});}catch(error){report.failures.push({name,error:error.message});console.error(name,error.message);}}
async function audit(page,label){await page.addScriptTag({content:axe});const result=await page.evaluate(async()=>({version:axe.version,...await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}})}));const violations=result.violations.map(v=>({id:v.id,impact:v.impact,targets:v.nodes.map(n=>n.target)}));report.accessibility.push({label,version:result.version,violations});assert.deepEqual(violations,[],label+' accessibility');}
try{
 for(const [engine,launcher,views] of [['chromium',chromium,viewports],['firefox',firefox,[[390,844],[1440,900]]],['webkit',webkit,[[390,844],[1440,900]]]]){
  const browser=await launcher.launch({headless:true});report[engine]=browser.version();
  try{for(const [width,height] of views){const context=await browser.newContext({viewport:{width,height}});await fixture(context,proof.origin);const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
   for(const path of paths)await check(`${engine} ${width} ${path}`,async()=>{
    await ready(page,path,proof.origin);
    const geometry=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth-innerWidth,headers:document.querySelectorAll('.sarsa-header').length,footers:document.querySelectorAll('.sarsa-footer').length,h1:document.querySelectorAll('main h1').length,bar:document.querySelector('.sarsa-header-bar').getBoundingClientRect().height,hero:document.querySelector('.hero')?.getBoundingClientRect().height,copy:document.querySelector('.hero-copy')?.getBoundingClientRect().width}));
    report.layouts.push({engine,width,height,path,...geometry});assert(geometry.overflow<=1,`Horizontal overflow ${geometry.overflow}px`);assert.equal(geometry.headers,1);assert.equal(geometry.footers,1);assert.equal(geometry.h1,1);assert.deepEqual(errors,[]);
    if(engine==='chromium'&&[390,1440].includes(width)){await page.screenshot({path:resolve(output,`page-${path.replaceAll('/','-')||'home'}-${width}.png`),fullPage:true});await audit(page,`${width} ${path}`);}
   });
   await check(`${engine} ${width} exclusive FAQ and menu`,async()=>{
    await ready(page,'/',proof.origin);const summaries=page.locator('.faq summary');await summaries.nth(0).click();await summaries.nth(1).click();assert.equal(await page.locator('.faq details[open]').count(),1);
    await summaries.nth(0).focus();await page.keyboard.press('Enter');assert.equal(await summaries.nth(0).evaluate(n=>n.parentElement.open),true);assert.equal(await page.locator('.faq details[open]').count(),1);await page.keyboard.press('Space');assert.equal(await page.locator('.faq details[open]').count(),0);
    if(engine==='chromium'&&width===1440){await page.locator('.service-card').first().hover();await page.screenshot({path:resolve(output,'state-card-hover.png'),fullPage:true});await page.locator('.service-card a').first().focus();await page.screenshot({path:resolve(output,'state-card-keyboard-focus.png'),fullPage:true});}
    if(width<1024){const menu=page.getByRole('button',{name:/Menu/});await menu.click();assert.equal(await menu.getAttribute('aria-expanded'),'true');if(engine==='chromium'&&width===390){await page.screenshot({path:resolve(output,'state-phone-menu-open.png')});await audit(page,'Phone menu open');}await page.keyboard.press('Escape');assert.equal(await menu.getAttribute('aria-expanded'),'false');assert(await menu.evaluate(node=>node===document.activeElement));}
   });console.log(JSON.stringify({engine,width,layouts:report.layouts.length,failures:report.failures.length}));await context.close();}
  }finally{await browser.close();}
 }
 const browser=await chromium.launch({headless:true});
 try{
  const context=await browser.newContext({viewport:{width:390,height:844}}),f=await fixture(context,proof.origin,{otp:true}),page=await context.newPage();
  await check('booking fields survive menu, resize and tab return with OTP active',async()=>{
   await ready(page,'/booking',proof.origin);await page.locator('input[name=service][value=kundli-matching]').check();await page.waitForTimeout(300);assert.equal(await page.locator('#appointment-title').evaluate(n=>n===document.activeElement),true);
   await page.locator('.abs-date-group').first().click();const tomorrow=new Date(Date.now()+86400000),day=Number(new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata',day:'2-digit'}).format(tomorrow));
   const cell=page.locator('.abs-calendar-cell').filter({hasText:new RegExp('^'+day+'$')}).filter({visible:true}).first();if(!(await cell.count())||await cell.getAttribute('aria-disabled')==='true')await page.getByRole('button',{name:'Next',exact:true}).click();await page.locator('.abs-calendar-cell').filter({hasText:new RegExp('^'+day+'$')}).filter({visible:true}).first().click();
   await page.locator('input[name=time]').first().check();await page.getByRole('button',{name:'Fill your details →',exact:true}).click();await page.locator('#full_name').fill('Synthetic Tester');await page.locator('#email').fill('synthetic@example.com');await page.locator('#phone').fill('9999999999');await page.getByRole('button',{name:'Send email code',exact:true}).click();await page.getByLabel('Email verification code',{exact:true}).fill('123456');
   const before=await page.locator('input[name=time]:checked').inputValue(),name=await page.locator('#full_name').inputValue();await page.getByRole('button',{name:/Menu/}).click();await page.keyboard.press('Escape');await page.setViewportSize({width:768,height:1024});const other=await context.newPage();await other.goto('about:blank');await page.bringToFront();await page.evaluate(()=>window.dispatchEvent(new Event('focus')));await page.waitForTimeout(600);
   assert.equal(await page.locator('#full_name').inputValue(),name);assert.equal(await page.locator('input[name=time]:checked').inputValue(),before);assert.equal(await page.getByLabel('Email verification code',{exact:true}).inputValue(),'123456');assert.equal(f.calls.filter(c=>c.path==='/api/booking-verification/start').length,1);await other.close();
  });
  await check('Contact topic, invalid code, retained draft and successful synthetic outcome',async()=>{
   await ready(page,'/contact',proof.origin);await page.getByRole('link',{name:/Ask about your booking/}).click();await page.waitForTimeout(350);assert.equal(await page.locator('#topic').inputValue(),'Existing booking');assert.equal(await page.locator('#visitor-name').evaluate(n=>n===document.activeElement),true);
   await page.locator('#visitor-name').fill('Synthetic Tester');await page.locator('#visitor-email').fill('synthetic@example.com');await page.locator('#message').fill('A local test only. No real message is sent.');await page.getByRole('button',{name:/Send email code/}).click();await page.locator('#code').waitFor();await page.locator('#code').fill('123');await page.locator('#enquiry').evaluate(form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));assert.match(await page.locator('#form-status').innerText(),/six-digit/);await page.locator('#code').fill('123456');await page.getByRole('link',{name:'Ask a question',exact:true}).click();await page.waitForTimeout(350);assert.equal(await page.locator('#code').inputValue(),'123456');await page.getByRole('button',{name:/Verify and send/}).click();await page.locator('#outcome').waitFor();assert.equal(await page.locator('#outcome').evaluate(n=>n===document.activeElement),true);await audit(page,'Contact received');
  });await context.close();
  await check('smooth anchors, repeated same hash, history and back-to-top preserve focus',async()=>{
   const c=await browser.newContext({viewport:{width:1440,height:900}});await fixture(c,proof.origin);const p=await c.newPage();await ready(p,'/about',proof.origin);await p.getByRole('link',{name:/Discover her approach/}).click();await p.waitForTimeout(350);assert.equal(await p.locator('#approach h2').evaluate(n=>n===document.activeElement),true);const position=await p.locator('#approach').evaluate(n=>n.getBoundingClientRect().top);const header=await p.locator('.sarsa-header-bar').evaluate(n=>n.getBoundingClientRect().height);assert(Math.abs(position-header-20)<=2);
   await p.getByRole('link',{name:/Find your service/}).click();await p.waitForTimeout(350);await p.goBack();await p.waitForTimeout(100);assert.equal(await p.locator('#approach h2').evaluate(n=>n===document.activeElement),true);await p.goForward();await p.waitForTimeout(100);assert.equal(await p.locator('#starting-point h2').evaluate(n=>n===document.activeElement),true);await p.getByRole('button',{name:'Back to top'}).click();await p.waitForTimeout(350);assert.equal(await p.evaluate(()=>scrollY),0);assert.equal(await p.locator('h1').evaluate(n=>n===document.activeElement),true);
   await p.getByRole('link',{name:/Discover her approach/}).click();await p.mouse.wheel(0,40);await p.waitForTimeout(400);assert.equal(await p.locator('#approach h2').evaluate(n=>n===document.activeElement),false);await c.close();
  });
  await check('200 percent text and 400 percent equivalent reflow retain readable controls',async()=>{
   const c=await browser.newContext({viewport:{width:320,height:740}});await fixture(c,proof.origin);const p=await c.newPage();
   for(const path of paths){await ready(p,path,proof.origin);await p.evaluate(()=>{const sizes=[...document.querySelectorAll('body h1,body h2,body h3,body p,body a,body button,body label,body small,body input,body select,body textarea,body span,body summary,body address,body dt,body dd')].map(n=>[n,parseFloat(getComputedStyle(n).fontSize),parseFloat(getComputedStyle(n).lineHeight)]);for(const[n,size,height]of sizes){n.style.fontSize=size*2+'px';if(Number.isFinite(height))n.style.lineHeight=height*2+'px';}});await p.waitForTimeout(100);assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,path+' enlarged text overflow');await p.screenshot({path:resolve(output,`enlarged-${path.replaceAll('/','-')||'home'}.png`),fullPage:true});}
   await c.close();
  });
  for(const mode of ['off','unknown'])await check(`${mode}: fail closed routes and asset boundary`,async()=>{
   proof.setEnabled(mode!=='off');const c=await browser.newContext({viewport:{width:390,height:844}});const f=await fixture(c,proof.origin,{mode});const p=await c.newPage();await ready(p,'/',proof.origin);assert.equal(await p.locator('a[href="/booking"]').count(),0);assert.match(await p.locator('main').innerText(),mode==='off'?/currently unavailable/:/could not be confirmed/);await ready(p,'/contact',proof.origin);assert(await p.locator('#visitor-name').isVisible());if(mode==='off'){const response=await p.goto(proof.origin+'/booking');assert.equal(response.status(),404);}else await ready(p,'/booking',proof.origin);assert.equal(await p.locator('input[name=service]').count(),0);
   if(mode==='off'){const entry=Object.entries(proof.manifest.assets).find(([,v])=>v==='booking');assert(entry,'Booking asset classified');const response=await c.request.get(proof.origin+entry[0]);assert.equal(response.status(),404);}
   assert.equal(f.calls.filter(v=>v.path==='/api/booking-policy').length,0);assert.deepEqual(f.assets.filter(path=>proof.manifest.assets[path]==='booking'),[]);await ready(p,'/',proof.origin);await p.screenshot({path:resolve(output,'state-'+mode+'.png'),fullPage:true});await audit(p,'Booking '+mode);await c.close();
  });proof.setEnabled(true);
  await check('reduced motion, blocked art/fonts, old anchor, keyboard skip and reflow',async()=>{
   const c=await browser.newContext({viewport:{width:320,height:740},reducedMotion:'reduce'});await fixture(c,proof.origin,{blockedAssets:true});const p=await c.newPage();await ready(p,'/about#consultations',proof.origin);await p.waitForTimeout(100);assert.equal(await p.locator('#starting-point h2').evaluate(n=>n===document.activeElement),true);assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);await ready(p,'/',proof.origin);await p.keyboard.press('Tab');assert.equal(await p.evaluate(()=>document.activeElement.textContent),'Skip to content');await p.keyboard.press('Enter');await p.waitForTimeout(100);assert.equal(await p.locator('main').evaluate(n=>n===document.activeElement),true);
   await p.evaluate(()=>{document.documentElement.style.fontSize='200%';});assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);await c.close();
  });
 }finally{await browser.close();}
}finally{await proof.close();report.finished=new Date().toISOString();writeFileSync(resolve(output,'browser-report.json'),JSON.stringify(report,null,2));}
console.log(JSON.stringify({layouts:report.layouts.length,checks:report.interactions.length,accessibility:report.accessibility.length,failures:report.failures.length,report:resolve(output,'browser-report.json')}));
if(report.failures.length)process.exitCode=1;
