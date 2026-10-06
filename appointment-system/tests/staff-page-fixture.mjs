// Local synthetic HTTP responses around the actual shipped staff document.
// No account, customer record, provider request or production login is used.
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
const root=fileURLToPath(new URL('../',import.meta.url));
export const available=Boolean(process.env.BOOKING_CHROME_EXECUTABLE&&process.env.BOOKING_BROWSER_NODE_MODULES);
export const id='11111111-1111-4111-8111-111111111111';
export const other='22222222-2222-4222-8222-222222222222';
export async function staffFixture(run){
 const state={calls:[],handlers:new Map(),enabled:true,status:{signed_in:true,role:'client',email:'practice@example.test',resources:[],authorization_saved:false},errors:[]};
 const server=createServer(async(req,res)=>{
  try{
   const path=new URL(req.url,'http://fixture.invalid').pathname;res.setHeader('cache-control','no-store');
   if(path==='/studio'){res.setHeader('content-type','text/html');return res.end((await readFile(resolve(root,'engine/appointment_system/studio_assets/index.html'),'utf8')).replaceAll('{{PRACTICE_NAME}}','Synthetic Practice'));}
   const name=path.split('/').pop();
   if(path.startsWith('/api/studio/')&&['interface.js','calendar.js','appointments.js','inbox.js','staff-actions.js','interface.css','booking-guard.mjs','product-state.mjs'].includes(name)){
    const file=name==='product-state.mjs'?'browser/'+name:'engine/appointment_system/studio_assets/'+name;
    res.setHeader('content-type',name.endsWith('.css')?'text/css':'text/javascript');
    return res.end((await readFile(resolve(root,file),'utf8')).replace('/*STAFF_BROWSER_CONFIGURATION*/null',JSON.stringify({installation_id:id,environment:'test',legacy:{client:[],company:[],calendar:[],inbox:[],enquiry:[]}})));
   }
   let raw='';for await(const part of req)raw+=part;const body=raw?JSON.parse(raw):null;state.calls.push({path,body});
   const reply=(value,status=200)=>{res.writeHead(status,{'content-type':'application/json'});res.end(JSON.stringify(value));};
   if(state.handlers.has(path))return await state.handlers.get(path)({body,reply,req,res});
   if(path==='/api/service-state')return reply({enabled:state.enabled,activation_epoch:id});
   if(path==='/api/studio/status')return reply(state.status);
   if(path==='/api/studio/calendar/time-context')return reply({code:'ok',timezone:'Asia/Kolkata',today:'2031-04-04'});
   if(path==='/api/studio/calendar/list')return reply({code:'ok',day:body.day,timezone:'Asia/Kolkata',items:[],next_cursor:null});
   if(path==='/api/studio/calendar/resolve-time')return reply({code:'ok',local:body.local,timezone:body.timezone,instant:new Date(body.local+':00+05:30').toISOString()});
   if(path==='/api/studio/calendar/month'){
    const date=new Date(body.month+'T12:00:00Z'),count=new Date(Date.UTC(date.getUTCFullYear(),date.getUTCMonth()+1,0)).getUTCDate();
    return reply({code:'ok',timezone:'Asia/Kolkata',month:body.month,days:Array.from({length:count},(_,i)=>({date:body.month.slice(0,8)+String(i+1).padStart(2,'0'),appointments:i===3?1:0,closures:i===4?1:0}))});
   }
   if(path==='/api/studio/inbox/list')return reply({code:'ok',view:body.view,items:[],next_cursor:null});
   reply({code:'fixture_route_missing'},404);
  }catch(error){state.errors.push(error.message);res.destroy();}
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin='http://127.0.0.1:'+server.address().port;
 const {chromium}=await import(pathToFileURL(resolve(process.env.BOOKING_BROWSER_NODE_MODULES,'playwright-core/index.mjs')).href);
 const browser=await chromium.launch({headless:true,executablePath:process.env.BOOKING_CHROME_EXECUTABLE,args:['--no-sandbox']});
 try{
  const context=await browser.newContext(),page=await context.newPage();page.setDefaultTimeout(10000);page.on('pageerror',error=>state.errors.push(error.message));
  await context.route('**/*',route=>route.request().url().startsWith(origin+'/')?route.continue():route.abort());
  await page.goto(origin+'/studio');await page.waitForFunction(()=>!!document.querySelector('#calendar-month button')&&!document.querySelector('#calendar-next').disabled);
  await run(page,state,origin);assert.deepEqual(state.errors,[]);await context.close();
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
}
export async function waitText(page,selector,text){await page.waitForFunction(({selector,text})=>document.querySelector(selector).textContent.includes(text),{selector,text});}
export function within(promise){let timer;return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Expected local request did not arrive within ten seconds')),10000);})]).finally(()=>clearTimeout(timer));}
