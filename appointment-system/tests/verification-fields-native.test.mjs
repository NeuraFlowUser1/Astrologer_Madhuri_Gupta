/** Actual project React and Chrome; test-only flow state, no provider or payment. */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {dirname,resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';

const dependencies=process.env.BOOKING_BROWSER_NODE_MODULES;
const available=Boolean(dependencies&&process.env.BOOKING_CHROME_EXECUTABLE);
const master=fileURLToPath(new URL('../',import.meta.url));

test('actual email-code fields reset stale input, respect expiry and expose only permitted actions',
 {skip:!available,timeout:120000},async()=>{
 const {createServer}=await import(pathToFileURL(resolve(dependencies,'vite/dist/node/index.js')).href);
 const {chromium}=await import(pathToFileURL(resolve(dependencies,'playwright-core/index.mjs')).href);
 const cache=await mkdtemp(resolve(tmpdir(),'abs-verification-react-'));
 const entry=`
  import React from 'react';
  import {createRoot} from 'react-dom/client';
  import {createVerificationFields} from ${JSON.stringify('/@fs/'+resolve(master,'browser/booking/verification-fields.mjs'))};
  const Fields=createVerificationFields(React),root=createRoot(document.getElementById('root'));
  window.proofCalls=[];
  const base={policy:{policy:{booking_verification:{email:true}}},credential:null,verification:null,challenge:null,
   details:{email:'synthetic@example.test'},busy:false,retryAt:0,serverOffset:0};
  window.proofState=base;
  window.renderProof=change=>{
   window.proofState={...base,...change};
   root.render(React.createElement(Fields,{flow:{state:window.proofState,
    startVerification:()=>window.proofCalls.push(['start']),resendVerification:()=>window.proofCalls.push(['resend']),
    verifyCode:code=>window.proofCalls.push(['verify',code])}}));
  };
  window.renderProof({});
 `;
 let server,browser;
 try{
  server=await createServer({root:dirname(dependencies),configFile:false,cacheDir:cache,logLevel:'error',
   server:{host:'127.0.0.1',port:0,fs:{allow:[master,dirname(dependencies)]}},
   plugins:[{name:'local-verification-proof',resolveId:id=>id==='/proof-entry.mjs'?'\0abs-verification-proof':null,
    load:id=>id==='\0abs-verification-proof'?entry:null,
    configureServer(server){server.middlewares.use((req,res,next)=>{
     if(req.url!=='/')return next();res.setHeader('content-type','text/html');
     res.end('<!doctype html><html><body><div id="root"></div><script type="module" src="/proof-entry.mjs"></script></body></html>');
    });}}]});
  await server.listen();const origin='http://127.0.0.1:'+server.httpServer.address().port;
  browser=await chromium.launch({headless:true,executablePath:process.env.BOOKING_CHROME_EXECUTABLE,args:['--no-sandbox']});
  const context=await browser.newContext();
  await context.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
  const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.clock.install({time:new Date()});
  await page.goto(origin);const send=page.getByRole('button',{name:'Send email code',exact:true});
  await send.waitFor();await send.click();
  assert.deepEqual(await page.evaluate(()=>window.proofCalls),[['start']]);
  await page.evaluate(()=>window.renderProof({details:{email:''}}));
  await page.waitForFunction(()=>document.querySelector('button')?.disabled===true);
  const challenge={challenge_id:'synthetic-challenge',generation:1,expires_at:new Date(Date.now()+60000).toISOString()};
  await page.evaluate(challenge=>window.renderProof({challenge}),challenge);
  const input=page.getByLabel('Email verification code'),verify=page.getByRole('button',{name:'Verify code',exact:true});
  await input.waitFor();assert.equal(await verify.isDisabled(),true);
  await input.fill('a12b34');assert.equal(await input.inputValue(),'1234');
  assert.equal(await verify.isDisabled(),true);await input.fill('123456');await verify.click();
  await page.getByRole('button',{name:'Send another code',exact:true}).click();
  assert.deepEqual(await page.evaluate(()=>window.proofCalls),[['start'],['verify','123456'],['resend']]);
  await page.evaluate(challenge=>window.renderProof({challenge:{...challenge,generation:2}}),challenge);
  await page.waitForFunction(()=>document.querySelector('input')?.value==='');
  await input.fill('654321');
  await page.evaluate(challenge=>window.renderProof({challenge:{...challenge,generation:2},details:{email:'changed@example.test'}}),challenge);
  await page.waitForFunction(()=>document.querySelector('input')?.value==='');
  await page.evaluate(challenge=>window.renderProof({challenge:{...challenge,generation:3}}),challenge);
  await page.waitForFunction(()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Send another code')?.disabled===true);
  await page.evaluate(challenge=>window.renderProof({challenge,busy:true}),challenge);
  await page.waitForFunction(()=>document.querySelector('input')?.disabled===true);
  assert.equal(await verify.isDisabled(),true);
  await page.evaluate(()=>window.renderProof({retryAt:Date.now()+60000}));
  await send.waitFor();assert.equal(await send.isDisabled(),true);
  await page.clock.runFor(60020);
  await page.waitForFunction(()=>document.querySelector('button')?.disabled===false);
  // Server-clock offset must not extend a code's actual remaining lifetime.
  await page.evaluate(challenge=>window.renderProof({challenge:{...challenge,expires_at:new Date(Date.now()+10000).toISOString()},serverOffset:11000}),challenge);
  await page.getByRole('button',{name:'Request a new code',exact:true}).waitFor();
  assert.equal(await input.count(),0);
  await page.evaluate(()=>window.renderProof({verification:{expires_at:new Date(Date.now()+60000).toISOString()}}));
  await page.getByRole('status').waitFor();assert.equal(await send.count(),0);
  await page.clock.runFor(60020);
  await send.waitFor();
  for(const change of [{credential:{request_id:'synthetic'}},{policy:{policy:{booking_verification:{email:false}}}}]){
   await page.evaluate(change=>window.renderProof(change),change);
   await page.waitForFunction(()=>document.getElementById('root').childElementCount===0);
  }
  assert.deepEqual(errors,[]);await context.close();
 }finally{
  if(browser)await browser.close();if(server)await server.close();await rm(cache,{recursive:true,force:true});
 }
});
