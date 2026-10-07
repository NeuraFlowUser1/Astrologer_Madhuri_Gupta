/** Official receiving-site peers, actual common controls and synthetic local data. */
import {test,before,after} from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve,dirname} from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const available=!!(process.env.BOOKING_CHROME_EXECUTABLE&&process.env.BOOKING_BROWSER_NODE_MODULES);
let browser,server,origin;
before(async()=>{
 if(!available)return;
 const dependencies=process.env.BOOKING_BROWSER_NODE_MODULES,require=createRequire(resolve(dependencies,'fixture.cjs'));
 const {build}=await import(pathToFileURL(require.resolve('vite')).href),entry=resolve(dirname(dependencies),'__abs_date_fixture__.mjs');
 const built=await build({root:dirname(dependencies),configFile:false,logLevel:'error',define:{'process.env.NODE_ENV':'"production"'},
  plugins:[{name:'synthetic-date-vendor',resolveId:id=>id===entry?'\0date-vendor':undefined,
   load:id=>id==='\0date-vendor'?"export * as React from 'react'; export {createRoot} from 'react-dom/client'; export * as Aria from 'react-aria-components'; export {parseDate,parseTime,Time} from '@internationalized/date';":undefined}],
  build:{write:false,minify:false,lib:{entry,formats:['es'],fileName:'vendor'},rollupOptions:{output:{inlineDynamicImports:true}}}});
 const vendor=(Array.isArray(built)?built[0]:built).output.find(item=>item.type==='chunk'&&item.isEntry).code;
 const document=`<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Local control fixture</title>
 <link rel="stylesheet" href="/browser/booking/date-time-fields.css"><style>body{margin:0;position:relative}main{max-width:340px;margin:260px auto 700px;padding:12px}.abs-date-picker{margin:24px 0}</style></head>
 <body><main id="root"></main><script type="module">
 import {React,createRoot,Aria,parseDate,parseTime,Time} from '/vendor.mjs';
 import {createDateTimeFields} from '/browser/booking/date-time-fields.mjs';
 const {DateField,TimeField}=createDateTimeFields(React,{...Aria,parseDate,parseTime,Time});
 const root=createRoot(document.getElementById('root'));let values={birth:'',time:'',appointment:''},options={available:true,disabled:false,required:false,error:'',description:''};
 const change=(name,value)=>{values={...values,[name]:value};render();};
 function View(){return React.createElement(React.Fragment,null,
  React.createElement(DateField,{label:'Birth date',name:'birth',value:values.birth,onChange:value=>change('birth',value),yearJump:true,max:'2026-10-07',...options}),
  React.createElement(TimeField,{label:'Birth time',name:'birthTime',value:values.time,onChange:value=>change('time',value),...options}),
  React.createElement(DateField,{label:'Appointment date',name:'appointmentDate',value:values.appointment,onChange:value=>change('appointment',value),min:'2026-10-08',max:'2026-10-18',required:true,available:options.available}),
  React.createElement('pre',{id:'values'},JSON.stringify(values)));}
 function render(){root.render(React.createElement(View));}
 window.fixture={values:()=>values,options:value=>{options={...options,...value};render();},set:value=>{values={...values,...value};render();},unmount:()=>root.unmount()};render();
 </script></body></html>`;
 server=createServer(async(req,res)=>{
  try{
   const path=new URL(req.url,'http://fixture.invalid').pathname;
   if(path==='/'){res.setHeader('content-type','text/html');return res.end(document);}
   if(path==='/vendor.mjs'){res.setHeader('content-type','text/javascript');return res.end(vendor);}
   if(['/browser/booking/date-time-fields.mjs','/browser/booking/date-time-fields.css'].includes(path)){
    res.setHeader('content-type',path.endsWith('.css')?'text/css':'text/javascript');return res.end(await readFile(resolve(root,path.slice(1)),'utf8'));
   }
   res.writeHead(404);res.end();
  }catch{res.destroy();}
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));origin='http://127.0.0.1:'+server.address().port;
 const {chromium}=await import(pathToFileURL(resolve(dependencies,'playwright-core/index.mjs')).href);
 browser=await chromium.launch({headless:true,executablePath:process.env.BOOKING_CHROME_EXECUTABLE,args:['--no-sandbox']});
});
after(async()=>{if(browser)await browser.close();if(server)await new Promise(resolve=>server.close(resolve));});
async function pageFor(run){
 const context=await browser.newContext({viewport:{width:390,height:844}}),page=await context.newPage(),errors=[];
 page.on('pageerror',error=>errors.push(error.message));await context.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
 try{await page.goto(origin);await page.locator('.abs-date-group').first().waitFor();await run(page);assert.deepEqual(errors,[]);}
 finally{await context.close();}
}
const field=(page,label)=>page.locator('.abs-date-picker').filter({has:page.getByText(label,{exact:true})});
test('birth calendar opens from the field, jumps directly, selects a leap day and clears without reopening',{skip:!available},()=>pageFor(async page=>{
 await field(page,'Birth date').locator('.abs-date-group').click();await page.getByLabel('Year',{exact:true}).fill('2000');
 await page.getByLabel('Month',{exact:true}).selectOption('2');
 await page.locator('.abs-calendar-cell:not([data-outside-month])').filter({hasText:/^29$/}).click();
 await page.waitForFunction(()=>fixture.values().birth==='2000-02-29');assert.equal(await page.locator('.abs-booking-picker').count(),0);
 const calendarButton=field(page,'Birth date').locator('.abs-date-group button');assert.ok(await calendarButton.getAttribute('aria-label'));
 await calendarButton.click();await page.getByRole('button',{name:'Clear date',exact:true}).click();
 await page.waitForFunction(()=>fixture.values().birth==='');assert.equal(await page.locator('.abs-booking-picker').count(),0);
 await page.evaluate(()=>fixture.unmount());assert.equal(await page.locator('.abs-picker-portal').count(),0);
}));
test('calendar year edits, schedule limits, keyboard Escape and unavailable state preserve valid data',{skip:!available},()=>pageFor(async page=>{
 await field(page,'Birth date').locator('.abs-date-group').click();const year=page.getByLabel('Year',{exact:true});
 await year.fill('1');await page.getByLabel('Month',{exact:true}).selectOption('1');assert.equal(await year.inputValue(),'1');
 await year.fill('');await year.blur();assert.equal(await year.inputValue(),'1');await year.fill('9999');await year.blur();assert.equal(await year.inputValue(),'1');
 await year.press('Escape');await page.locator('.abs-booking-picker').waitFor({state:'hidden'});
 await field(page,'Appointment date').locator('.abs-date-group').click();
 assert.ok(await page.locator('.abs-calendar-cell[data-disabled]').count()>0);
 assert.equal(await page.locator('.abs-calendar-cell:not([data-outside-month])').filter({hasText:/^7$/}).getAttribute('data-disabled'),'true');
 await page.locator('.abs-calendar-cell:not([data-outside-month])').filter({hasText:/^8$/}).click();
 await page.waitForFunction(()=>fixture.values().appointment==='2026-10-08');
 await page.evaluate(()=>fixture.options({available:false}));await page.waitForFunction(()=>[...document.querySelectorAll('.abs-date-picker button')].every(n=>n.disabled));
 assert.equal(await page.evaluate(()=>fixture.values().appointment),'2026-10-08');
 await page.evaluate(()=>fixture.options({available:true,error:'Check this date',description:'Optional preparation'}));
 await field(page,'Birth date').getByText('Check this date',{exact:true}).waitFor();assert.equal(await page.getByText('Optional preparation',{exact:true}).count(),2);
}));
test('time choices preserve all minutes, AM and PM boundaries, cancellation and optional clear',{skip:!available},()=>pageFor(async page=>{
 await page.getByRole('button',{name:'Choose Birth time',exact:true}).click();
 assert.equal(await page.getByLabel('Minute',{exact:true}).locator('option').count(),60);
 await page.getByLabel('Hour',{exact:true}).selectOption('12');await page.getByLabel('Minute',{exact:true}).selectOption('59');await page.getByLabel('AM / PM',{exact:true}).selectOption('AM');
 await page.getByRole('button',{name:'Apply',exact:true}).click();await page.waitForFunction(()=>fixture.values().time==='00:59');
 await field(page,'Birth time').locator('.abs-date-group').click();await page.getByLabel('AM / PM',{exact:true}).selectOption('PM');
 await page.getByRole('button',{name:'Cancel',exact:true}).click();assert.equal(await page.evaluate(()=>fixture.values().time),'00:59');
 await field(page,'Birth time').locator('.abs-date-group').click();await page.getByLabel('Hour',{exact:true}).selectOption('11');await page.getByLabel('AM / PM',{exact:true}).selectOption('PM');
 await page.getByRole('button',{name:'Apply',exact:true}).click();await page.waitForFunction(()=>fixture.values().time==='23:59');
 await field(page,'Birth time').locator('.abs-date-group').click();await page.getByRole('button',{name:'Clear',exact:true}).click();await page.waitForFunction(()=>fixture.values().time==='');
}));
test('picker positioning remains inside small screens with a positioned body and closes when controls are disabled',{skip:!available},()=>pageFor(async page=>{
 for(const [width,height] of [[320,740],[390,844],[768,1024],[1440,900]]){
  await page.setViewportSize({width,height});await field(page,'Birth date').locator('.abs-date-group').click();
  await page.waitForFunction(()=>{const n=document.querySelector('.abs-booking-picker');if(!n)return false;const r=n.getBoundingClientRect();return r.top>=11&&r.left>=11&&r.bottom<=innerHeight-11&&r.right<=innerWidth-11;});
  await page.keyboard.press('Escape');await page.locator('.abs-booking-picker').waitFor({state:'hidden'});
 }
 await field(page,'Birth time').locator('.abs-date-group').click();await page.evaluate(()=>fixture.options({disabled:true}));
 await page.locator('.abs-booking-picker').waitFor({state:'hidden'});
 await page.evaluate(()=>fixture.options({disabled:false,required:true}));await page.getByRole('button',{name:'Choose Birth time',exact:true}).click();
 assert.equal(await page.getByRole('button',{name:'Clear',exact:true}).count(),0);await page.keyboard.press('Escape');
}));

test('every populated date and time segment opens the chooser without dismissing it on focus transfer',{skip:!available},()=>pageFor(async page=>{
 await page.evaluate(()=>fixture.set({birth:'2000-02-29',time:'00:59',appointment:'2026-10-08'}));
 for(const [width,height] of [[390,844],[1440,900]]){
  await page.setViewportSize({width,height});await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  for(const label of ['Birth date','Appointment date','Birth time']){
   const segments=field(page,label).getByRole('spinbutton');
   for(const segment of await segments.all()){
    await segment.click();await page.locator('.abs-booking-picker').waitFor({state:'visible'});
    await page.waitForTimeout(100);assert.equal(await page.locator('.abs-booking-picker').isVisible(),true);
    assert.deepEqual(await page.evaluate(()=>fixture.values()),{birth:'2000-02-29',time:'00:59',appointment:'2026-10-08'});
    await page.keyboard.press('Escape');await page.locator('.abs-booking-picker').waitFor({state:'hidden'});
   }
  }
 }
}));
