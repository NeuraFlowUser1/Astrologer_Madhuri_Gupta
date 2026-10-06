import {createInterface} from 'node:readline';
import {createServer} from 'node:http';
import assert from 'node:assert/strict';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const lines=createInterface({input:process.stdin,crlfDelay:Infinity}),pending=new Map();let sequence=0;
lines.on('line',line=>{const value=JSON.parse(line),complete=pending.get(value.id);pending.delete(value.id);complete(value);});
const bridge=(path,options={})=>new Promise(resolve=>{const id=++sequence;pending.set(id,resolve);process.stdout.write(JSON.stringify({id,path,...options})+'\n');});
const {chromium}=await import(pathToFileURL(resolve(process.env.BOOKING_BROWSER_NODE_MODULES,'playwright-core/index.mjs')).href);
const server=createServer((req,res)=>{res.writeHead(404);res.end();});await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin='http://127.0.0.1:'+server.address().port,settings=JSON.parse((await bridge('test:settings')).body);
const browser=await chromium.launch({headless:true,executablePath:process.env.BOOKING_CHROME_EXECUTABLE,args:['--no-sandbox']});
const context=await browser.newContext({viewport:{width:1280,height:900},reducedMotion:'reduce'}),errors=[];let page,moves=0,reviews=0;
try{
 await context.route('**/*',async route=>{
  const request=route.request(),url=new URL(request.url());if(url.origin!==origin)return route.abort();
  if(!['/studio','/enquiries-studio','/api/service-state'].includes(url.pathname)&&!url.pathname.startsWith('/api/studio/')&&!url.pathname.startsWith('/api/enquiry-studio/'))return route.abort();
  const result=await bridge(url.pathname,request.method()==='POST'?{body:request.postDataJSON()}:{});
  if(result.status>=400)process.stderr.write(url.pathname+' '+result.status+' '+result.body.slice(0,300)+'\n');
  if(url.pathname==='/api/studio/appointments/reschedule'){
   moves++;assert.equal(result.status,200,result.body);return route.abort('connectionreset');
  }
  if(url.pathname==='/api/enquiry-studio/inbox/review'){
   reviews++;assert.equal(result.status,200,result.body);return route.abort('connectionreset');
  }
  await route.fulfill({status:result.status,contentType:result.contentType,headers:{'cache-control':'no-store'},body:result.body});
 });
 page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));await page.goto(origin+'/studio');
 const local=value=>{const d=new Date(value);return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(d).replace(' ','T');};
 const day=local(settings.starts_at).slice(0,10);
 await page.waitForFunction(()=>!document.querySelector('#calendar-day').disabled&&document.querySelector('#calendar-month button'));
 await page.getByRole('button',{name:new RegExp('^'+day+': 1 appointments,')}).click();
 await page.getByRole('button',{name:'Manage appointment',exact:true}).click();await page.locator('#appointment-reschedule').waitFor();
 await page.locator('#appointment-start').fill(local(settings.next_start));await page.locator('#appointment-move-reason').fill('Synthetic browser reschedule');
 await page.locator('#appointment-reschedule button[type=submit]').click();
 await page.waitForFunction(()=>document.querySelector('#appointment-status').textContent.includes('could not confirm'));
 assert.equal(moves,1);await page.reload();await page.locator('#appointment-repeat').waitFor();await page.locator('#appointment-repeat').click();
 await page.waitForFunction(()=>document.querySelector('#appointment-status').textContent.includes('Earlier actions checked'));
 assert.equal(moves,1);assert.equal(await page.evaluate(()=>window.PracticeStaffActions('client').get().length),0);
 await page.screenshot({path:'/tmp/abs-staff-native-database.png',fullPage:false});
 await bridge('test:off');await page.evaluate(()=>window.bookingVisibility.refresh({force:true}));assert.equal(await page.locator('[data-booking-shell]').isVisible(),false);
 await page.goto(origin+'/enquiries-studio');await page.getByRole('button',{name:'Open details',exact:true}).click();await page.locator('#note').fill('Synthetic saved enquiry review');await page.locator('#save').click();
 await page.waitForFunction(()=>!document.querySelector('#check-saved').hidden&&!document.querySelector('#check-saved').disabled);assert.equal(reviews,1);
 await page.reload();await page.locator('#check-saved').waitFor();await page.locator('#check-saved').click();
 await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('Earlier actions checked'));
 assert.equal(reviews,1);assert.equal(await page.evaluate(()=>window.PracticeStaffActions('enquiry').get().length),0);assert.deepEqual(errors,[]);
 await bridge('test:finished');
}catch(error){if(page)process.stderr.write(JSON.stringify(await page.evaluate(()=>({status:document.querySelector('#status')?.textContent,appointment:document.querySelector('#appointment-status')?.textContent,calendar:document.querySelector('#calendar-status')?.textContent})))+'\n');throw error;}finally{lines.close();await context.close();await browser.close();await new Promise(resolve=>server.close(resolve));}
