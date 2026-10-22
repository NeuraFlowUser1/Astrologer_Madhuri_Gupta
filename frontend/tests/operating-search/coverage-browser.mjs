/** Source-bound browser qualification against loopback fixtures only. */
import {chromium} from 'playwright-core';
import {writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
import coverage from 'istanbul-lib-coverage';
import {startReview} from '../public-site/review-server.mjs';
import {publicPaths} from '../../src/site/page-metadata.mjs';
const root=resolve(import.meta.dirname,'../..'),output=resolve(root,'coverage/operating-browser');
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
const map=coverage.createCoverageMap({}),observations=[],servers=[];
async function collect(page){const data=await page.evaluate(()=>globalThis.__sarsaCoverage__||{});map.merge(data);}
try{
 for(const mode of ['on','off']){
  const server=await startReview({mode,distRoot:resolve(output,'client')});servers.push(server);
  const context=await browser.newContext({viewport:{width:390,height:844},reducedMotion:'reduce'});
  await context.route('**/*',route=>route.request().url().startsWith(server.origin)?route.continue():route.abort());
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  for(const path of publicPaths){
   await page.goto(server.origin+path,{waitUntil:'load'});await page.waitForTimeout(350);
   assert.equal(await page.locator('main h1').count(),1);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   if(path==='/services/prashna-kundali'){
    const tabs=page.getByRole('tab');for(let i=0;i<await tabs.count();i++){await tabs.nth(i).click();assert.equal(await tabs.nth(i).getAttribute('aria-selected'),'true');}
    for(const key of ['Home','End','ArrowLeft','ArrowRight','Enter'])await page.keyboard.press(key);
    assert.equal(await page.getByRole('tab',{selected:true}).count(),1);
    const faqs=page.locator('details');await faqs.nth(0).locator('summary').click();await faqs.nth(1).locator('summary').click();assert.equal(await page.locator('details[open]').count(),1);
   }
   if(['kundli-matching','kundli-prediction','vastu-consultation','numerology'].some(id=>path==='/services/'+id)){
    const choices=page.locator('.story-choices button');for(let i=0;i<await choices.count();i++){await choices.nth(i).click();assert.equal(await choices.nth(i).getAttribute('aria-pressed'),'true');}
    await page.getByRole('button',{name:'Next →',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.story-viewer')?.getAttribute('aria-busy')!=='true');await page.waitForTimeout(300);assert.equal(await page.getByRole('button',{name:'Next →',exact:true}).getAttribute('aria-disabled'),'true');
    await page.getByRole('button',{name:'← Previous',exact:true}).click();await page.waitForTimeout(300);assert.equal(await page.getByRole('button',{name:'← Previous',exact:true}).getAttribute('aria-disabled'),'true');
   }
   if(path==='/contact'){
    await page.locator('#visitor-name').focus();await page.locator('#visitor-name').fill('Local Coverage Visitor');
    await page.getByRole('link',{name:'Ask a question',exact:false}).first().click();assert.equal(await page.locator('#topic').inputValue(),'Before booking');
   }
   assert.deepEqual(errors,[]);observations.push({path,mode,reduced:true,actions:'Actual public route and available controls'});await collect(page);
  }
  await context.close();
 }
 for(const width of [1440,390]){
  const server=servers[0];const context=await browser.newContext({viewport:{width,height:width===390?844:900},reducedMotion:'no-preference'});
  await context.route('**/*',route=>route.request().url().startsWith(server.origin)?route.continue():route.abort());
  const page=await context.newPage();
  for(const path of ['/','/about','/contact','/services/prashna-kundali']){
   await page.goto(server.origin+path,{waitUntil:'load'});await page.waitForTimeout(250);
   const scenes=page.locator('[data-motion-progress]');for(let i=0;i<await scenes.count();i++){await scenes.nth(i).scrollIntoViewIfNeeded();await page.waitForTimeout(100);}
   await page.waitForFunction(()=>[...document.querySelectorAll('[data-motion-progress]')].every(el=>Number(el.dataset.motionProgress)>=.999),null,{timeout:16000});
   if(path==='/contact'){await page.locator('#visitor-name').click();await page.mouse.up();await page.keyboard.press('Tab');}
   if(path==='/services/prashna-kundali'){const tabs=page.getByRole('tab');await tabs.nth(1).click();await tabs.nth(2).click();await page.emulateMedia({reducedMotion:'reduce'});await page.emulateMedia({reducedMotion:'no-preference'});}
   await page.evaluate(()=>{Object.defineProperty(document,'hidden',{value:true,configurable:true});document.dispatchEvent(new Event('visibilitychange'));Object.defineProperty(document,'hidden',{value:false,configurable:true});document.dispatchEvent(new Event('visibilitychange'));window.dispatchEvent(new Event('resize'));});
   await page.getByRole('link',{name:'Services',exact:true}).first().click();await page.waitForTimeout(200);
   observations.push({path,width,normalMotion:true,settled:true,cleanupNavigation:true});await collect(page);
  }
  await context.close();
 }
 await writeFile(resolve(output,'browser-coverage.json'),JSON.stringify(map.toJSON()));await writeFile(resolve(output,'browser-observations.json'),JSON.stringify(observations,null,2)+'\n');console.log(JSON.stringify({observations:observations.length,files:map.files().length,providerCalls:0,output}));
}finally{await browser.close();for(const server of servers)await server.close();}
