// Real company page in Chrome; every response and identity is synthetic.
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';
export {available,id,other,waitText} from './staff-page-fixture.mjs';
import {id} from './staff-page-fixture.mjs';
const assets=fileURLToPath(new URL('../engine/appointment_system/company_assets/',import.meta.url));
export async function companyFixture(run,{login=true}={}){
 const state={signed:false,calls:[],handlers:new Map(),errors:[],progress:'effective',snapshot:{enabled:false,revision:'1',restore_generation:id},
  business:{revision:'1',settings:{timezone:'Asia/Kolkata',slot_step_minutes:15,notice_minutes:60,horizon_days:90,buffer_before_minutes:0,buffer_after_minutes:0,
   meeting:'google_meet',booking_verification:{email:false},weekly_windows:[{weekday:0,start:'09:00',end:'17:00'}],services:[
    {id:'fixed',name:'Synthetic fixed',enabled:true,duration_minutes:30,pricing:{kind:'fixed',amount_paise:100}},
    {id:'question',name:'Synthetic question',enabled:true,duration_minutes:15,pricing:{kind:'per_question',amount_paise:125,maximum_questions:3}}]}}};
 const server=createServer(async(req,res)=>{
  try{
   const path=new URL(req.url,'http://fixture.invalid').pathname;res.setHeader('cache-control','no-store');
   if(path==='/company/booking-control'){res.setHeader('content-type','text/html');return res.end((await readFile(resolve(assets,'control.html'),'utf8')).replaceAll('CLIENT_NAME','Synthetic Practice').replaceAll('PROJECT_NUMBER','fixture'));}
   const name=path.split('/').pop();
   if(path.startsWith('/api/company/assets/')&&['control.css','control.js','command-journal.js'].includes(name)){
    res.setHeader('content-type',name.endsWith('.css')?'text/css':'text/javascript');return res.end((await readFile(resolve(assets,name),'utf8')).replace('/*COMPANY_BROWSER_CONFIGURATION*/null',JSON.stringify({installation_id:id,environment:'test'})));
   }
   let raw='';for await(const chunk of req)raw+=chunk;const body=raw?JSON.parse(raw):null;state.calls.push({path,body});
   const reply=(value,status=200)=>{res.writeHead(status,{'content-type':'application/json'});res.end(JSON.stringify(value));};
   if(state.handlers.has(path))return await state.handlers.get(path)({body,reply,req,res});
   if(path==='/api/company/sign-in/start'){state.signed=true;return reply({});}
   if(path==='/api/company/sign-out'){state.signed=false;return reply({});}
   if(!state.signed)return reply({code:'company_session_required'},401);
   const status=()=>({snapshot:state.snapshot,csrf_token:'a'.repeat(64),progress:state.progress});
   if(path==='/api/company/control/status')return reply(status());
   if(path==='/api/company/control/change'){state.snapshot.enabled=body.enabled;return reply({...status(),operation_id:body.operation_id});}
   if(path==='/api/company/settings'){
    if(req.method==='GET')return reply(state.business);
    state.business={revision:String(BigInt(body.revision)+1n),settings:body.settings};return reply({saved:true,revision:state.business.revision,quote_version:'a'.repeat(64)});
   }
   if(['/api/company/reauthenticate','/api/company/password'].includes(path))return reply({});
   if(path==='/api/company/resources/status')return reply({resources:[],pending:[]});
   if(path==='/api/company/operations/incidents')return reply({version:1,project:'fixture',incidents:[]});
   if(path==='/api/company/records/status')return reply({records:[],total:0,limited:false});
   reply({code:'fixture_route_missing'},404);
  }catch(error){state.errors.push(error.message);res.destroy();}
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin='http://127.0.0.1:'+server.address().port;
 const {chromium}=await import(pathToFileURL(resolve(process.env.BOOKING_BROWSER_NODE_MODULES,'playwright-core/index.mjs')).href);
 const browser=await chromium.launch({headless:true,executablePath:process.env.BOOKING_CHROME_EXECUTABLE,args:['--no-sandbox']});
 try{
  const context=await browser.newContext(),page=await context.newPage();page.on('pageerror',error=>state.errors.push(error.message));
  await context.route('**/*',route=>route.request().url().startsWith(origin+'/')?route.continue():route.abort());
  await page.goto(origin+'/company/booking-control');await page.locator('#signed-out').waitFor({state:'visible'});
  if(login){await page.fill('#username','synthetic.owner');await page.fill('#password','Synthetic browser password');await page.click('#login');await page.locator('#signed-in').waitFor({state:'visible'});}
  await run(page,state,origin);assert.deepEqual(state.errors,[]);await context.close();
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
}
