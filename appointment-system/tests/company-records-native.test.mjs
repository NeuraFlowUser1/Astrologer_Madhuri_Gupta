import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));

test('actual company page preserves an interrupted check and hides record details after sign-out',
 {skip:!process.env.BOOKING_CHROME_EXECUTABLE||!process.env.BOOKING_BROWSER_NODE_MODULES},async()=>{
 const {chromium}=await import(pathToFileURL(resolve(process.env.BOOKING_BROWSER_NODE_MODULES,'playwright-core/index.mjs')).href);
 const assets=resolve(root,'engine/appointment_system/company_assets');
 let signed=false,lose=true,delay=false,releaseResponse=null;const commands=[];
 const server=createServer(async(req,res)=>{
  const path=new URL(req.url,'http://fixture.invalid').pathname;res.setHeader('cache-control','no-store');
  if(path==='/company/booking-control'){res.setHeader('content-type','text/html');return res.end((await readFile(resolve(assets,'control.html'),'utf8')).replaceAll('CLIENT_NAME','Synthetic Practice').replaceAll('PROJECT_NUMBER','fixture'));}
  if(['/api/company/assets/control.css','/api/company/assets/control.js','/api/company/assets/command-journal.js'].includes(path)){
   res.setHeader('content-type',path.endsWith('.css')?'text/css':'text/javascript');
   return res.end((await readFile(resolve(assets,path.split('/').pop()),'utf8')).replace('/*COMPANY_BROWSER_CONFIGURATION*/null',JSON.stringify({installation_id:'1bbbc890-7c26-4ba6-b3ef-7c9b363c5bc2',environment:'test'})));
  }
  res.setHeader('content-type','application/json');
  if(path==='/api/company/sign-in/start'){signed=true;return res.end('{}');}
  if(path==='/api/company/sign-out'){signed=false;return res.end('{}');}
  if(!signed){res.writeHead(401);return res.end('{"code":"company_session_required"}');}
  if(path==='/api/company/control/status')return res.end(JSON.stringify({csrf_token:'a'.repeat(64),snapshot:{enabled:false},progress:'effective'}));
  if(path==='/api/company/records/status'){
   const respond=()=>res.end(JSON.stringify({total:1,limited:false,records:[{role:'client',record_kind:'booking',
    record_id:'ac06e18a-af1a-4a53-b752-8e70c3aa709b',sequence:'3',reference:'<img src=x onerror=alert(1)>',
    last_error_code:'google_row_conflict',attention:true,busy:false}]}));
   if(delay){releaseResponse=respond;return;}return respond();
  }
  if(path==='/api/company/records/recheck'){
   let body='';for await(const chunk of req)body+=chunk;commands.push(JSON.parse(body));
   assert.equal(req.headers['x-company-csrf'],'a'.repeat(64));
   // A lost successful backend reply is surfaced as an unavailable result.
   // A raw socket reset can be transparently retried by Chromium itself.
   if(lose){lose=false;res.writeHead(503);return res.end('{"code":"saved_reply_unavailable"}');}return res.end('{"code":"check_queued"}');
  }
  res.writeHead(404);res.end('{}');
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const origin='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:true,executablePath:process.env.BOOKING_CHROME_EXECUTABLE,args:['--no-sandbox']});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>route.request().url().startsWith(origin+'/')?route.continue():route.abort());
  await page.goto(origin+'/company/booking-control');await page.locator('#signed-out').waitFor({state:'visible'});
  assert.equal(await page.locator('#record-list').isVisible(),false);
  await page.fill('#username','synthetic.owner');await page.fill('#password','Synthetic browser password');await page.click('#login');
  await page.locator('#signed-in').waitFor({state:'visible'});
  await page.getByText('Google connections and record copies',{exact:true}).click();await page.click('#record-refresh');
  await page.getByRole('button',{name:'Check this record again',exact:true}).waitFor();
  assert.equal(await page.locator('#record-list img').count(),0);
  assert.match(await page.locator('#record-list').innerText(),/<img src=x onerror=alert\(1\)>/);
  await page.getByRole('button',{name:'Check this record again',exact:true}).click();
  await page.getByRole('button',{name:'Check this request again',exact:true}).click();
  await page.getByRole('button',{name:'Check queued',exact:true}).waitFor();
  assert.equal(commands.length,2);assert.deepEqual(commands[0],commands[1]);
  delay=true;await page.click('#record-refresh');
  await new Promise((resolve,reject)=>{const started=Date.now();const check=()=>releaseResponse?resolve():Date.now()-started>5000?reject(new Error('Synthetic delayed request not started')):setTimeout(check,10);check();});
  const lateResponse=page.waitForResponse(response=>response.url()===origin+'/api/company/records/status');
  await page.click('#logout');await page.locator('#signed-out').waitFor({state:'visible'});releaseResponse();
  await (await lateResponse).finished();await page.waitForLoadState('networkidle');
  await page.waitForFunction(()=>document.getElementById('record-list').childElementCount===0&&document.getElementById('google-section').hidden);
  assert.equal(await page.locator('#record-status').innerText(),'');assert.deepEqual(errors,[]);
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
});
