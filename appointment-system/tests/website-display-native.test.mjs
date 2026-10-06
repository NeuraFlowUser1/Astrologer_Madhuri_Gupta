/** Real Chrome + emitted project files. Display proof only; no live accounts. */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {readFileSync} from 'node:fs';
import {displayProof} from '../tools/checks/website-display.mjs';

const root=process.env.BOOKING_WEBSITE_PROOF_PROJECT,site=process.env.BOOKING_WEBSITE_PROOF_SITE;
test('built project in Chrome removes booking pages, assets and links while preserving ordinary pages',{skip:!root || !site},async()=>{
 const {chromium}=await import(pathToFileURL(resolve(site,'node_modules/playwright-core/index.mjs')).href);
 const browser=await chromium.launch({headless:true,...(process.env.BOOKING_CHROME_EXECUTABLE?{executablePath:process.env.BOOKING_CHROME_EXECUTABLE}:{}),args:['--no-sandbox']});
 const proof=await displayProof(root,site),context=await browser.newContext();
 try{
  // The test cannot reach either official site, a payment service or any other
  // third party through the browser. Every request stays in its owned fixture.
  await context.route('**/*',route=>new URL(route.request().url()).origin===proof.origin?route.continue():route.abort());
  const page=await context.newPage(),errors=[],requests=[];
  page.on('pageerror',error=>errors.push(error.message));page.on('request',request=>requests.push(new URL(request.url()).pathname));
  for(const path of proof.manifest.public_paths){
   const response=await page.goto(proof.origin+path);assert.equal(response.status(),200,path);
   await page.waitForFunction(()=>document.querySelector('h1') && document.body.innerText.trim().length>60 && !document.body.innerText.includes('Loading the page'));
   assert.equal(await page.locator('vite-error-overlay').count(),0);
   const exposed=await page.locator('a[href]').evaluateAll(nodes=>nodes.map(node=>node.getAttribute('href')).filter(href=>/^\/(?:booking|studio|checkout|receipt)(?:[/?#-]|$)/i.test(href)));
   assert.deepEqual(exposed,[],path+' exposes booking links OFF');
  }
  const assets=Object.entries(proof.manifest.assets);
  for(const [path,kind] of assets){
   const response=await context.request.head(proof.origin+path);
   assert.equal(response.status(),kind==='booking'?404:200,path);
  }
  for(const path of [...proof.manifest.booking_paths,'/studio','/api/checkout/status','/api/booking-policy','/api/availability',
   '/booking/index.html','/BOOKING//receipt/','/%62ooking','/%2562ooking','/__booking_display/on/index.html']){
   const response=await context.request.get(proof.origin+path);assert.equal(response.status(),404,path);
  }
  const sitemap=await (await context.request.get(proof.origin+'/sitemap.xml')).text();assert.ok(!sitemap.includes('/booking'));
  for(const path of requests)assert.notEqual(proof.manifest.assets[path],'booking','OFF page loaded booking-only code: '+path);
  await page.goto(proof.origin+'/');await page.waitForFunction(()=>document.querySelector('h1') && document.body.innerText.trim().length>60 && !document.body.innerText.includes('Loading the page'));
  proof.setEnabled(true);
  await page.waitForFunction(()=>[...document.querySelectorAll('a[href]')].some(node=>/^\/booking(?:[/?#]|$)/.test(node.getAttribute('href'))),undefined,{timeout:10000});
  proof.setEnabled(false);
  await page.waitForFunction(()=>![...document.querySelectorAll('a[href]')].some(node=>/^\/booking(?:[/?#]|$)/.test(node.getAttribute('href'))),undefined,{timeout:10000});
  await page.goto(proof.origin+'/contact');await page.waitForFunction(()=>document.querySelector('h1') && document.body.innerText.trim().length>60 && !document.body.innerText.includes('Loading the page'));
  assert.ok(await page.locator('input,textarea').count()>0,'Contact fields disappeared OFF');
  await page.goBack();await page.waitForFunction(()=>document.querySelector('h1') && document.body.innerText.trim().length>60 && !document.body.innerText.includes('Loading the page'));
  assert.equal(await page.locator('a[href="/booking"]').count(),0);
  assert.deepEqual(errors,[]);
  const evidence=JSON.parse(readFileSync(resolve(site,'dist/appointment-bundle-surfaces.json')));
  for(const item of evidence.unreferenced_assets){assert.equal((await context.request.get(proof.origin+item.path)).status(),404,item.path);}
  console.log(JSON.stringify({project:proof.project.project_id,public_pages:proof.manifest.public_paths.length,
   booking_pages:proof.manifest.booking_paths.length,assets:assets.length,unreferenced_assets:evidence.unreferenced_assets.length,
   browser_errors:errors.length,scope:'isolated-built-display-not-payment-or-provider-proof'}));
 }finally{await context.close();await browser.close();await proof.close();}
});
