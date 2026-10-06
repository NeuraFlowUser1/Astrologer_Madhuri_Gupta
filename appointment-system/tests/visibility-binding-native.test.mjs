// Optional plain-HTML binding uses the same live OFF state as React.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {resolve} from 'node:path';
const available=Boolean(process.env.BOOKING_CHROME_EXECUTABLE&&process.env.BOOKING_BROWSER_NODE_MODULES);
const root=fileURLToPath(new URL('../browser/',import.meta.url));
test('plain HTML binding hides all marked booking content and updates inserted content and alternative wording',{skip:!available},async()=>{
 let enabled=false;const errors=[];
 const server=createServer(async(req,res)=>{try{
  const path=new URL(req.url,'http://fixture.invalid').pathname;
  if(path==='/api/service-state'){res.setHeader('content-type','application/json');return res.end(JSON.stringify({enabled,activation_epoch:'11111111-1111-4111-8111-111111111111'}));}
  if(['/visibility.js','/product-state.mjs'].includes(path)){res.setHeader('content-type','text/javascript');return res.end(await readFile(resolve(root,path.slice(1)),'utf8'));}
  res.setHeader('content-type','text/html');res.end('<!doctype html><main><section id="booking" data-booking-only>Book online</section><p id="copy" data-booking-on="Book online" data-booking-off="Call the practice">Call the practice</p><p id="ordinary">Ordinary enquiries remain available</p></main><script type="module" src="/visibility.js"></script>');
 }catch(error){errors.push(error.message);res.destroy();}});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin='http://127.0.0.1:'+server.address().port;
 const {chromium}=await import(pathToFileURL(resolve(process.env.BOOKING_BROWSER_NODE_MODULES,'playwright-core/index.mjs')).href);
 const browser=await chromium.launch({headless:true,executablePath:process.env.BOOKING_CHROME_EXECUTABLE,args:['--no-sandbox']});
 try{const page=await browser.newPage();page.on('pageerror',e=>errors.push(e.message));await page.route('**/*',route=>route.request().url().startsWith(origin+'/')?route.continue():route.abort());await page.goto(origin);await page.waitForFunction(()=>window.bookingVisibility!==undefined);
  assert.equal(await page.locator('#booking').isVisible(),false);assert.equal(await page.locator('#copy').textContent(),'Call the practice');
  enabled=true;await page.evaluate(()=>bookingVisibility.refresh({force:true}));await page.waitForFunction(()=>document.documentElement.dataset.bookingState==='on');assert.equal(await page.locator('#booking').isVisible(),true);assert.equal(await page.locator('#copy').textContent(),'Book online');
  enabled=false;await page.evaluate(()=>bookingVisibility.refresh({force:true}));await page.waitForFunction(()=>document.documentElement.dataset.bookingState==='off');
  await page.evaluate(()=>{const node=document.createElement('a');node.id='late-booking';node.dataset.bookingOnly='';node.textContent='Late booking link';document.querySelector('main').append(node);});await page.waitForFunction(()=>document.querySelector('#late-booking').hidden);assert.equal(await page.locator('#late-booking').evaluate(n=>n.inert),true);assert.equal(await page.locator('#ordinary').isVisible(),true);assert.equal(await page.locator('#ordinary').textContent(),'Ordinary enquiries remain available');assert.deepEqual(errors,[]);
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
});
