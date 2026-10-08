import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';

const root=fileURLToPath(new URL('../',import.meta.url));
const assets=resolve(root,'engine/appointment_system');
const epoch='bd01549f-d36a-4aef-ae9d-11257192d1af';
const owner=['/studio','/enquiries-studio','/company/booking-control'];
const company=['/company/booking-control','/company/booking-support','/company/google-repair','/studio','/enquiries-studio'];
const pages=new Map([
 ['/studio','studio_assets/index.html'], ['/enquiries-studio','studio_assets/enquiries.html'],
 ['/company/booking-control','company_assets/control.html'],
 ['/company/booking-support','company_assets/support.html'],
 ['/company/google-repair','company_assets/google-repair.html'],
]);

test('private links connect every existing page, wrap on phones, retain keyboard focus and grant no authority',
 {skip:!process.env.BOOKING_CHROME_EXECUTABLE||!process.env.BOOKING_BROWSER_NODE_MODULES},async()=>{
 const files=new Map();
 for(const name of ['interface.js','calendar.js','inbox.js','appointments.js','interface.css','booking-guard.mjs','staff-actions.js'])
  files.set('/api/studio/'+name,resolve(assets,'studio_assets',name));
 files.set('/api/studio/product-state.mjs',resolve(root,'browser/product-state.mjs'));
 for(const name of ['control.css','control.js','command-journal.js'])files.set('/api/company/assets/'+name,resolve(assets,'company_assets',name));
 files.set('/api/company/support.js',resolve(assets,'company_assets/support.js'));
 files.set('/api/company/google-repair.js',resolve(assets,'company_assets/google-repair.js'));
 files.set('/api/company/staff-actions.js',resolve(assets,'studio_assets/staff-actions.js'));
 files.set('/api/enquiry-studio/staff-actions.js',resolve(assets,'studio_assets/staff-actions.js'));
 files.set('/api/enquiry-studio/interface.js',resolve(assets,'studio_assets/enquiries.js'));
 files.set('/api/enquiry-studio/interface.css',resolve(assets,'studio_assets/enquiries.css'));
 let enabled=true;const errors=[],requests=[];
 const configuration=JSON.stringify({version:1,installation_id:epoch,environment:'test',legacy:{client:[],company:[],calendar:[],inbox:[],enquiry:[]}});
 const server=createServer(async(req,res)=>{
  try{
   const path=new URL(req.url,'http://fixture.invalid').pathname;
   requests.push({path,method:req.method});res.setHeader('cache-control','no-store');
   if(pages.has(path)){
    res.setHeader('content-type','text/html');
    return res.end((await readFile(resolve(assets,pages.get(path)),'utf8'))
      .replaceAll('{{PRACTICE_NAME}}','Synthetic Practice').replaceAll('CLIENT_NAME','Synthetic Practice').replaceAll('PROJECT_NUMBER','fixture'));
   }
   if(files.has(path)){
    res.setHeader('content-type',path.endsWith('.css')?'text/css':'text/javascript');
    return res.end((await readFile(files.get(path),'utf8'))
      .replace('/*STAFF_BROWSER_CONFIGURATION*/null',configuration)
      .replace('/*COMPANY_BROWSER_CONFIGURATION*/null',JSON.stringify({installation_id:epoch,environment:'test'})));
   }
   res.setHeader('content-type','application/json');
   if(path==='/api/service-state')return res.end(JSON.stringify({enabled,activation_epoch:epoch}));
   res.writeHead(401);res.end('{"code":"company_session_required","signed_in":false}');
  }catch(error){errors.push(error.message);res.destroy();}
 });
 await new Promise(done=>server.listen(0,'127.0.0.1',done));const origin='http://127.0.0.1:'+server.address().port;
 const {chromium}=await import(pathToFileURL(resolve(process.env.BOOKING_BROWSER_NODE_MODULES,'playwright-core/index.mjs')).href);
 const browser=await chromium.launch({headless:true,executablePath:process.env.BOOKING_CHROME_EXECUTABLE,args:['--no-sandbox']});
 try{
  const context=await browser.newContext();const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
  await context.route('**/*',route=>route.request().url().startsWith(origin+'/')?route.continue():route.abort());
  for(const width of [320,1440]){
   await page.setViewportSize({width,height:900});
   for(const path of pages.keys()){
    await page.goto(origin+path);const nav=page.getByRole('navigation',{name:'Private pages'});await nav.waitFor();
    assert.deepEqual(await nav.locator('a').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('href'))),path.startsWith('/company/')?company:owner);
    assert.equal(await nav.locator('[aria-current=page]').getAttribute('href'),path);
    assert.equal(await page.locator('a[href="/company/records"]').count(),0);
    const bounds=await nav.locator('a').evaluateAll(nodes=>nodes.map(n=>({height:n.getBoundingClientRect().height,left:n.getBoundingClientRect().left,right:n.getBoundingClientRect().right})));
    for(const box of bounds){assert.ok(box.height>=44);assert.ok(box.left>=0&&box.right<=width);}
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await nav.locator('a').first().focus();
    assert.equal(await nav.locator('a').first().evaluate(n=>getComputedStyle(n).outlineStyle),'solid');
    // Follow every link as the browser would, then check the actual target page.
    for(const target of path.startsWith('/company/')?company:owner){
     await page.goto(origin+path);await page.getByRole('navigation',{name:'Private pages'}).waitFor();
     await page.locator('.private-nav a[href="'+target+'"]').click();
     await page.waitForURL(origin+target);
     await page.getByRole('navigation',{name:'Private pages'}).waitFor();
    }
   }
  }
  enabled=false;await page.goto(origin+'/studio');
  await page.waitForFunction(()=>window.bookingVisibility?.getSnapshot().verified);
  assert.equal(await page.locator('.private-nav').isVisible(),false);
  await page.goto(origin+'/enquiries-studio');await page.getByRole('navigation',{name:'Private pages'}).waitFor();
  assert.equal(await page.locator('#workspace').isVisible(),false);
  await page.locator('.private-nav a[href="/company/booking-control"]').click();
  await page.locator('#signed-out').waitFor({state:'visible'});
  assert.equal(await page.locator('#signed-in').isVisible(),false);
  assert.equal(requests.filter(r=>r.method!=='GET').length,0);
  assert.deepEqual(errors,[]);await context.close();
 }finally{await browser.close();await new Promise(done=>server.close(done));}
});
