/** Local, disconnected rendering proof. It cannot contact production providers. */
import {createServer} from 'node:http';
import {readFile,stat,mkdir,writeFile} from 'node:fs/promises';
import {extname,resolve,join,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright-core';
import assert from 'node:assert/strict';
import {publicPaths,pageRegistry} from '../../src/site/page-metadata.mjs';
const frontend=resolve(fileURLToPath(new URL('../..',import.meta.url)));
const quick=process.argv.includes('--quick'),record=quick?'quick-review.json':'review.json';
const output=resolve(process.env.SARSA_REVIEW_OUTPUT||'/tmp/sarsa004-operating-search-review');await mkdir(output,{recursive:true});
const epoch='11111111-1111-4111-8111-111111111111';
const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.png':'image/png','.webp':'image/webp','.jpeg':'image/jpeg','.svg':'image/svg+xml','.ttf':'font/ttf','.txt':'text/plain','.xml':'application/xml'};
const servers=[];
async function serve(directory,mode){
 const server=createServer(async(req,res)=>{
  let pathname;try{pathname=new URL(req.url,'http://test.invalid').pathname;}catch{res.writeHead(400).end();return;}
  if(pathname==='/api/service-state'){res.writeHead(200,{'content-type':'application/json','cache-control':'no-store'}).end(JSON.stringify({enabled:mode==='on',activation_epoch:epoch}));return;}
  if(pathname.startsWith('/api/')||req.method!=='GET'){res.writeHead(503,{'content-type':'application/json'}).end('{"error":"disconnected_local_review"}');return;}
  let local=pathname==='/'?'index.html':pathname.slice(1);if(!extname(local))local+='.html';
  if(local.includes('..')){res.writeHead(400).end();return;}
  const variant=join(directory,'__booking_display',mode,local),ordinary=join(directory,local);
  let file=ordinary;try{if((await stat(variant)).isFile())file=variant;}catch{}
  if(!file.startsWith(directory+sep)){res.writeHead(400).end();return;}
  try{const bytes=await readFile(file);res.writeHead(200,{'content-type':mime[extname(file)]||'application/octet-stream'}).end(bytes);}catch{res.writeHead(404).end('Not found');}
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));servers.push(server);return 'http://127.0.0.1:'+server.address().port;
}
const origin=await serve(resolve(frontend,'dist'),'on'),off=await serve(resolve(frontend,'dist'),'off');
const baseline=process.env.SARSA_BASELINE_DIST?await serve(resolve(process.env.SARSA_BASELINE_DIST),'on'):null;
const axeSource=process.env.AXE_SOURCE?await readFile(process.env.AXE_SOURCE,'utf8'):null;
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{})});
const results={generated:new Date().toISOString(),scope:'Disconnected local rendering; no real enquiry, booking, payment, login or provider action.',pages:[],timelines:[],interactions:[]};
try{
 if(!quick)for(const viewport of [{width:1440,height:900},{width:390,height:844}]){
  const context=await browser.newContext({viewport,deviceScaleFactor:1});
  await context.route('**/*',route=>route.request().url().startsWith('http://127.0.0.1:')?route.continue():route.abort());
  await context.addInitScript(()=>{window.__reviewShifts=[];new PerformanceObserver(list=>list.getEntries().forEach(e=>{if(!e.hadRecentInput)window.__reviewShifts.push({value:e.value,time:e.startTime,nodes:e.sources.map(s=>({node:s.node?.tagName,id:s.node?.id,className:s.node?.className}))});})).observe({type:'layout-shift',buffered:true});});
  const page=await context.newPage();
  for(const path of publicPaths){
   const errors=[];page.removeAllListeners('pageerror');page.removeAllListeners('console');page.on('pageerror',error=>errors.push(error.message));page.on('console',message=>{if(message.type()==='error'&&/hydration|hydrated|server rendered|Minified React error #4/i.test(message.text()))errors.push(message.text());});
   const response=await page.goto(origin+path,{waitUntil:'load'});
   await page.waitForTimeout(path==='/about'?11200:4500);
   const check=await page.evaluate(()=>({earlyMedia:performance.getEntriesByType('resource').filter(e=>/consultation-still-life/.test(e.name)).map(e=>({url:e.name,bytes:e.transferSize,bodyBytes:e.encodedBodySize})),heroSource:document.querySelector('.hero-photo img')?.currentSrc,title:document.title,h1:[...document.querySelectorAll('h1')].map(e=>e.textContent),main:document.querySelectorAll('main').length,overflow:document.documentElement.scrollWidth>innerWidth,robots:document.querySelector('meta[name="robots"]').content,canonical:document.querySelector('link[rel="canonical"]')?.href,broken:[...document.images].filter(e=>e.complete&&e.naturalWidth===0).map(e=>e.getAttribute('src')),fallbacks:[...document.querySelectorAll('[data-motion-fallback]')].length,shifts:window.__reviewShifts}));
   if(path==='/'){assert.equal(check.earlyMedia.length,1,'Home downloads exactly one selected background');assert.match(check.heroSource,/consultation-still-life-(768|1280|1920)\.webp/);}
   await page.evaluate(async()=>{const step=Math.max(300,innerHeight*.75);for(let y=0;y<document.documentElement.scrollHeight;y+=step){scrollTo(0,y);await new Promise(resolve=>setTimeout(resolve,80));}});
   const scenes=page.locator('main [data-motion-progress]');
   for(let scene=0;scene<await scenes.count();scene++){
    const element=scenes.nth(scene);await element.evaluate(el=>el.scrollIntoView({block:'center',behavior:'instant'}));
    await page.waitForTimeout(120);
   }
   await page.waitForFunction(()=>[...document.querySelectorAll('main [data-motion-progress]')].every(el=>Number(el.dataset.motionProgress)>=.999),null,{timeout:12000});
   await page.waitForFunction(()=>[...document.querySelectorAll('main img')].every(el=>el.complete),null,{timeout:20000});
   check.broken=await page.locator('main img').evaluateAll(images=>images.filter(el=>!el.naturalWidth).map(el=>el.getAttribute('src')));
   await page.evaluate(()=>window.scrollTo(0,0));await page.waitForTimeout(150);
   // Reviews use their original finite Web Animations rather than the shared
   // progress attribute. Inspect their finished text, while retaining loops.
   await page.waitForFunction(()=>document.getAnimations().every(animation=>animation.effect?.getTiming().iterations===Infinity||(!animation.pending&&animation.playState!=='running')),null,{timeout:12000});
   if(axeSource){await page.addScriptTag({content:axeSource});const audit=await page.evaluate(async()=>{const result=await axe.run(document,{runOnly:{type:'rule',values:['color-contrast']}});return result.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}));});check.contrast=audit;}
   assert.equal(await page.title(),pageRegistry[path].title);assert.equal(check.canonical,'https://www.sarsajyotishsansthan.com'+path);
   await page.screenshot({path:join(output,`${viewport.width}-${path==='/'?'home':path.slice(1).replaceAll('/','-')}.png`),fullPage:true});
   results.pages.push({path,width:viewport.width,status:response.status(),errors,...check});
   if(check.h1.length!==1||check.main!==1||check.overflow||check.broken.length||check.fallbacks||errors.length)throw Error('Rendered page failed: '+viewport.width+' '+path+' '+JSON.stringify({errors,...check}));
  }
  // Uninterrupted real clock captures. The original and candidate use identical viewports.
  for(const [name,address] of [['candidate',origin],...(baseline?[['baseline',baseline]]:[])]){
   await page.goto(address+'/about',{waitUntil:'load'});await page.waitForSelector('#scene',{state:'attached'});const started=Date.now();
   for(const milliseconds of [0,2400,3090,7150,11000]){
    await page.waitForTimeout(Math.max(0,milliseconds-(Date.now()-started)));
    const state=await page.evaluate(()=>{const scene=document.querySelector('#scene'),portrait=document.querySelector('#portrait');return {progress:document.querySelector('#opening')?.dataset.motionProgress,scene:{width:scene.clientWidth,height:scene.clientHeight},portrait:getComputedStyle(portrait).transform,footer:document.querySelector('footer').getBoundingClientRect().top,shifts:window.__reviewShifts};});
    await page.screenshot({path:join(output,`${viewport.width}-about-${name}-${milliseconds}.png`)});results.timelines.push({name,width:viewport.width,milliseconds,...state});
   }
  }
  await page.goto(origin+'/about');await page.waitForTimeout(150);await page.getByRole('link',{name:'Services',exact:true}).first().click();await page.waitForTimeout(500);
  results.interactions.push({width:viewport.width,action:'public navigation retains a complete public route',path:new URL(page.url()).pathname,title:await page.title(),loading:await page.getByText('Loading the page…',{exact:true}).count()});
  await page.goto(origin+'/contact');await page.waitForTimeout(200);const form=page.locator('#enquiry');results.interactions.push({width:viewport.width,action:'bound enquiry',method:await form.getAttribute('method'),disabled:await form.locator('fieldset').evaluate(e=>e.disabled)});assert.equal(await form.getAttribute('method'),'post');assert.equal(await form.locator('fieldset').evaluate(e=>e.disabled),false);
  await page.goto(off+'/booking');await page.waitForTimeout(300);results.interactions.push({width:viewport.width,action:'utility remains excluded while OFF',robots:await page.locator('meta[name="robots"]').getAttribute('content')});
  await context.close();
 }
 if(quick){
  for(const config of [{width:320,height:740,reduced:true},{width:390,height:844,reduced:true},{width:1440,height:900,reduced:true,zoom:true},{width:390,height:844,reduced:true,blocked:true}]){
   const context=await browser.newContext({viewport:{width:config.width,height:config.height},reducedMotion:config.reduced?'reduce':'no-preference'});
   await context.route('**/*',route=>route.request().url().startsWith('http://127.0.0.1:')?route.continue():route.abort());
   if(config.blocked)await context.addInitScript(()=>Object.defineProperty(window,'sessionStorage',{get(){throw new DOMException('Unavailable','SecurityError');}}));
   const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
   for(const path of config.blocked?['/contact']:['/','/about','/contact','/services/kundli-matching','/services/numerology']){
    await page.goto(origin+path);await page.waitForTimeout(250);
    if(config.zoom)await page.evaluate(()=>document.body.style.zoom='2');
    const state=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,running:document.getAnimations().filter(a=>a.playState==='running').length,portrait:document.querySelector('#opening')?.dataset.motionProgress,formDisabled:document.querySelector('#enquiry fieldset')?.disabled}));
    assert.equal(state.overflow,false,'Narrow/zoom layout: '+path);assert.equal(state.running,0,'Reduced motion: '+path);assert.deepEqual(errors,[],'Early/blocked-storage errors');
    if(config.blocked)assert.equal(state.formDisabled,true);
    await page.locator('.sarsa-skip').focus();await page.keyboard.press('Enter');assert.equal(await page.evaluate(()=>document.activeElement.id),'page-content');
    results.interactions.push({action:'narrow, reduced motion, focus and storage',path,...config,...state});
   }
   await context.close();
  }
 }
 const noScript=await browser.newContext({javaScriptEnabled:false,viewport:{width:390,height:844}});await noScript.route('**/*',route=>route.request().url().startsWith('http://127.0.0.1:')?route.continue():route.abort());const page=await noScript.newPage();
 for(const path of publicPaths){await page.goto(origin+path);results.interactions.push({action:'no-script public body',path,h1:await page.locator('h1').count(),characters:(await page.locator('main').textContent()).length});}
 await page.goto(origin+'/contact');results.interactions.push({action:'unbound enquiry cannot submit personal data',method:await page.locator('#enquiry').getAttribute('method'),fieldsetDisabled:await page.locator('#enquiry fieldset').evaluate(e=>e.disabled),email:await page.locator('a[href="mailto:sarsajyotish@gmail.com"]').count()});assert.equal(await page.locator('#enquiry fieldset').evaluate(e=>e.disabled),true);assert.equal(await page.locator('#enquiry').getAttribute('method'),'post');await noScript.close();
 await writeFile(join(output,record),JSON.stringify(results,null,2)+'\n');const failedContrast=results.pages.filter(page=>page.contrast?.length);assert.equal(failedContrast.length,0,'Contrast remains on '+failedContrast.map(page=>page.width+':'+page.path).join(', '));console.log(JSON.stringify({output,pages:results.pages.length,timelineFrames:results.timelines.length,interactions:results.interactions.length}));
}catch(error){results.failure=String(error);await writeFile(join(output,record),JSON.stringify(results,null,2)+'\n');throw error;}finally{await browser.close();for(const server of servers)await new Promise(resolve=>server.close(resolve));}
