/** Official-site GET-only gate. No credentials, sends, charges or saved settings. */
import {mkdir,writeFile} from 'node:fs/promises';
import {resolve,join} from 'node:path';
import {chromium} from 'playwright-core';
import {origin,pageRegistry,publicPaths} from '../../src/site/page-metadata.mjs';
import {checkPublicReadback} from './public-readback.mjs';
import './read-only-review.js';
const output=resolve(process.env.SARSA_HOSTED_EVIDENCE||'../docs/qa/2026-10-22-operating-search/hosted');
await mkdir(output,{recursive:true});
await checkPublicReadback(output);
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE?{executablePath:process.env.CHROMIUM_EXECUTABLE}:{}),args:['--no-sandbox','--disable-dev-shm-usage']});
const reports=[];
try{
 const control=await browser.newPage();
 for(const phase of ['routes-390','routes-1440','edges','interfaces','services','api','booking-layouts','prashna','links']){
  const links=[...new Set(reports.flatMap(report=>report.internalLinks))];
  await control.goto('about:blank#'+phase+(phase==='links'?'?'+encodeURIComponent(JSON.stringify(links)):''));
  const report=await globalThis.hostedReadOnlyReview(control);reports.push(report);
  await writeFile(join(output,phase+'.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({phase,passed:report.passed,failed:report.failed,assertions:report.assertions}));
 }
 const summary={started:reports[0].started,finished:reports.at(-1).finished,phases:reports.length,passed:reports.reduce((sum,r)=>sum+r.passed,0),failed:reports.reduce((sum,r)=>sum+r.failed,0),assertions:reports.reduce((sum,r)=>sum+r.assertions,0),blockedWrites:reports.flatMap(r=>r.blockedWrites),cases:reports.flatMap(r=>r.cases)};
 await writeFile(join(output,'summary.json'),JSON.stringify(summary,null,2)+'\n');
 if(summary.failed)throw Error('Hosted gate has '+summary.failed+' failed cases');
 if(process.argv.includes('--capture')){
  const captures=[];
  for(const viewport of [{width:1440,height:900},{width:390,height:844}]){
   const context=await browser.newContext({viewport,reducedMotion:'no-preference'});
   await context.route('**/*',route=>{const request=route.request();if(new URL(request.url()).origin===origin&&!['GET','HEAD'].includes(request.method()))return route.abort();return route.continue();});
   const page=await context.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message));page.on('console',m=>{if(m.type()==='error'&&/hydration|Minified React error #418|server rendered HTML/i.test(m.text()))errors.push(m.text());});
   for(const path of publicPaths){
    await page.goto(origin+path,{waitUntil:'load'});await page.evaluate(()=>document.fonts.ready);
    // Visit the entire page: some lazy photographs have no motion owner.
    await page.evaluate(async()=>{const step=Math.max(300,innerHeight*.75);for(let y=0;y<document.documentElement.scrollHeight;y+=step){scrollTo(0,y);await new Promise(resolve=>setTimeout(resolve,80));}});
    const scenes=page.locator('[data-motion-progress]');for(let i=0;i<await scenes.count();i++){await scenes.nth(i).scrollIntoViewIfNeeded();await page.waitForTimeout(120);}
    await page.waitForFunction(()=>[...document.querySelectorAll('[data-motion-progress]')].every(el=>Number(el.dataset.motionProgress)>=.999),null,{timeout:18000});
    await page.waitForFunction(()=>[...document.querySelectorAll('main img')].every(el=>el.complete),null,{timeout:20000});
    await page.evaluate(()=>window.scrollTo(0,0));await page.waitForTimeout(150);
    await page.waitForFunction(()=>document.getAnimations().every(animation=>animation.effect?.getTiming().iterations===Infinity||(!animation.pending&&animation.playState!=='running')),null,{timeout:12000});
    const filename=viewport.width+'-'+(path==='/'?'home':path.slice(1).replaceAll('/','-'))+'.png';
    await page.screenshot({path:join(output,filename),fullPage:true});
    const state=await page.evaluate(()=>({title:document.title,overflow:document.documentElement.scrollWidth>innerWidth,broken:[...document.querySelectorAll('main img')].filter(e=>e.complete&&!e.naturalWidth).length}));
    if(state.title!==pageRegistry[path].title||state.overflow||state.broken||errors.length)throw Error('Hosted capture differs: '+path+' '+JSON.stringify({state,errors}));
    captures.push({path,...viewport,...state,filename});
   }
   await context.close();
  }
  await writeFile(join(output,'captures.json'),JSON.stringify(captures,null,2)+'\n');
 }
 console.log(JSON.stringify({output,phases:summary.phases,passed:summary.passed,failed:summary.failed,assertions:summary.assertions}));
}finally{await browser.close();}
