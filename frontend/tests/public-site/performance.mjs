/** Matched local lab samples; no field-performance or provider-latency claim. */
import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdirSync,readdirSync} from 'node:fs';
import {resolve} from 'node:path';
import {gzipSync} from 'node:zlib';
import {cpus} from 'node:os';
import {chromium} from 'playwright-core';
import {displayProof} from '../../../appointment-system/tools/checks/website-display.mjs';
import {compressedProof} from './performance-server.mjs';
import {fixture,ready} from './browser-fixtures.mjs';
const candidate=resolve(import.meta.dirname,'../../..'),baseline=process.env.SARSA_BASELINE_ROOT;if(!baseline)throw Error('Set SARSA_BASELINE_ROOT to the original locked-source build.');
const output=resolve(process.env.SARSA_EVIDENCE_DIR||'/tmp/sarsa-performance');mkdirSync(output,{recursive:true});
const browser=await chromium.launch({headless:true});const proofs={baseline:await compressedProof(await displayProof(baseline,resolve(baseline,'frontend'),{enabled:true})),candidate:await compressedProof(await displayProof(candidate,resolve(candidate,'frontend'),{enabled:true}))};
const report={kind:'matched-local-lab-not-field',machine:cpus()[0].model,node:process.version,browser:browser.version(),profile:{cpu_slowdown:4,down_bps:1600000,up_bps:750000,latency_ms:150,cold_cache:true,text_compression:'gzip on both built versions',synthetic_api_delay_ms:30,external_fonts_and_map:'blocked in both samples; local font assets included'},samples:[],assets:{}};
async function observation(page,label){await page.waitForTimeout(350);return page.evaluate(label=>({label,...window.__sarsaLab}),label);}
try{
 for(const [name,root] of Object.entries({baseline,candidate})){const assets=resolve(root,'frontend/dist/assets');report.assets[name]={javascript_gzip_bytes:readdirSync(assets).filter(n=>n.endsWith('.js')).reduce((sum,n)=>sum+gzipSync(readFileSync(resolve(assets,n))).byteLength,0)};}
 for(const width of [390,1440])for(let sample=0;sample<5;sample++)for(const name of ['baseline','candidate']){
  const context=await browser.newContext({viewport:{width,height:width===390?844:900}}),proof=proofs[name];await fixture(context,proof.origin,{responseDelay:30});
  await context.addInitScript(()=>{window.__sarsaLab={lcp:0,cls:0,events:[]};new PerformanceObserver(list=>{for(const e of list.getEntries())window.__sarsaLab.lcp=e.startTime;}).observe({type:'largest-contentful-paint',buffered:true});new PerformanceObserver(list=>{for(const e of list.getEntries())if(!e.hadRecentInput)window.__sarsaLab.cls+=e.value;}).observe({type:'layout-shift',buffered:true});new PerformanceObserver(list=>{for(const e of list.getEntries())if(e.interactionId)window.__sarsaLab.events.push({type:e.name,duration:e.duration,interaction:e.interactionId});}).observe({type:'event',buffered:true,durationThreshold:16});});
  const page=await context.newPage(),cdp=await context.newCDPSession(page);await cdp.send('Network.enable');await cdp.send('Network.setCacheDisabled',{cacheDisabled:true});await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:150,downloadThroughput:1600000/8,uploadThroughput:750000/8});await cdp.send('Emulation.setCPUThrottlingRate',{rate:4});
  await ready(page,'/',proof.origin);await page.waitForTimeout(600);const home=await observation(page,'home-load');
  const interactions=[];
  if(width===390){const menu=page.getByRole('button',{name:/Menu/}).first();if(await menu.isVisible()){await menu.click();await page.keyboard.press('Escape');interactions.push(await observation(page,'phone-menu'));}}
  await page.locator('main summary').first().click();interactions.push(await observation(page,'FAQ-open'));
  await ready(page,'/contact',proof.origin);await page.locator('#visitor-name').click();await page.keyboard.type('Synthetic');interactions.push(await observation(page,'Contact-name-typing'));
  await ready(page,'/booking',proof.origin);await page.locator('input[name=service]').first().check();interactions.push(await observation(page,'booking-service-step'));
  const durations=interactions.flatMap(v=>v.events.map(e=>e.duration));const result={name,width,sample:sample+1,lcp_ms:home.lcp,cls:home.cls,interaction_max_ms:durations.length?Math.max(...durations):null,interactions};report.samples.push(result);console.log(JSON.stringify({name,width,sample:sample+1,lcp_ms:home.lcp,cls:home.cls,interaction_max_ms:result.interaction_max_ms}));await context.close();
 }
 const median=values=>[...values].sort((a,b)=>a-b)[Math.floor(values.length/2)];report.summary=[];
 for(const width of [390,1440])for(const name of ['baseline','candidate']){const rows=report.samples.filter(r=>r.width===width&&r.name===name);report.summary.push({name,width,count:rows.length,lcp_median_ms:median(rows.map(r=>r.lcp_ms)),lcp_range_ms:[Math.min(...rows.map(r=>r.lcp_ms)),Math.max(...rows.map(r=>r.lcp_ms))],cls_max:Math.max(...rows.map(r=>r.cls)),interaction_max_ms:Math.max(...rows.map(r=>r.interaction_max_ms||0)),interactions_measured:rows.every(r=>r.interaction_max_ms!==null)});}
 report.javascript_gzip_delta=report.assets.candidate.javascript_gzip_bytes-report.assets.baseline.javascript_gzip_bytes;
 report.failures=[];if(report.javascript_gzip_delta>25*1024)report.failures.push('New JavaScript exceeds +25KiB gzip budget');
 for(const row of report.summary.filter(r=>r.name==='candidate')){if(row.lcp_median_ms>2500)report.failures.push(`${row.width} median LCP exceeds 2500ms`);if(row.cls_max>.1)report.failures.push(`${row.width} CLS exceeds .1`);if(!row.interactions_measured||row.interaction_max_ms>200)report.failures.push(`${row.width} interactions missing or exceed 200ms`);}
 assert.equal(report.samples.length,20);writeFileSync(resolve(output,'performance-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({summary:report.summary,failures:report.failures,javascript_gzip_delta:report.javascript_gzip_delta}));if(report.failures.length)process.exitCode=1;
}finally{await browser.close();for(const proof of Object.values(proofs))await proof.close();writeFileSync(resolve(output,'performance-report.json'),JSON.stringify(report,null,2));}
