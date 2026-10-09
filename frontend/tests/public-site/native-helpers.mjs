/** Exercise actual Node entrypoints, instrumenting original source identities. */
import {registerHooks} from 'node:module';
import assert from 'node:assert/strict';
import {readFileSync,mkdirSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createInstrumenter} from 'istanbul-lib-instrument';
const root=resolve(import.meta.dirname,'../..'),files=['proxy.js','vite.config.js','src/booking/browser.mjs','src/booking/payment-recovery.mjs'].map(file=>resolve(root,file));
const instrumenter=createInstrumenter({esModules:true,coverageVariable:'__sarsaCoverage__',coverageGlobalScope:'globalThis',coverageGlobalScopeFunc:false});
const hook=registerHooks({load(url,context,next){
 // Browser adapters use Vite's supported JSON-module import syntax.
 if(url.endsWith('.json')&&!context.importAttributes?.type)context={...context,importAttributes:{...context.importAttributes,type:'json'}};
 const result=next(url,context);if(url.startsWith('file:')){const path=fileURLToPath(url);if(files.includes(path))return {...result,source:instrumenter.instrumentSync(readFileSync(path,'utf8'),path)};}return result;
}});
let checks=0;
try{
 const originalFetch=globalThis.fetch;try{globalThis.fetch=()=>{throw Error('Native binding import must not contact a provider');};const {bookingBrowser}=await import(pathToFileURL(files[2]));const {paymentRecovery}=await import(pathToFileURL(files[3]));assert.equal(paymentRecovery,bookingBrowser.recovery);checks++;assert.equal(typeof bookingBrowser.product.subscribe,'function');checks++;}finally{globalThis.fetch=originalFetch;}
 const {default:routing}=await import(pathToFileURL(files[0]));assert.equal(typeof routing,'function');checks++;
 const previous={wsl:process.env.WSL_DISTRO_NAME,poll:process.env.SARSA_DEV_POLL};
 try{for(const [index,wsl,poll,expected] of [[0,undefined,undefined,false],[1,'Ubuntu',undefined,true],[2,undefined,'1',true]]){
  if(wsl===undefined)delete process.env.WSL_DISTRO_NAME;else process.env.WSL_DISTRO_NAME=wsl;
  if(poll===undefined)delete process.env.SARSA_DEV_POLL;else process.env.SARSA_DEV_POLL=poll;
  const {default:config}=await import(pathToFileURL(files[1]).href+'?fixture='+index);assert.equal(config.server.watch.usePolling,expected);checks++;
  if(index!==0)continue;let callback,writes=0,body;
  config.server.proxy['/api'].configure({on:(event,fn)=>{assert.equal(event,'error');callback=fn;}});
  callback({code:'ECONNREFUSED'},null,{headersSent:false,writeHead:(code,headers)=>{assert.equal(code,503);assert.equal(headers['Content-Type'],'application/json');writes++;},end:value=>body=value});assert.match(JSON.parse(body).error,/initializing/);checks++;
  callback({code:'ECONNREFUSED'},null,{headersSent:true,writeHead:()=>writes++});assert.equal(writes,1);checks++;
  callback({code:'ECONNREFUSED'},null,{});assert.equal(writes,1);checks++;
  const original=console.error;let logged;try{console.error=(...value)=>logged=value;callback({code:'EOTHER',message:'Synthetic failure'},null,{});}finally{console.error=original;}assert.deepEqual(logged,['[vite] proxy error:','Synthetic failure']);checks++;
 }}finally{for(const [key,value] of [['WSL_DISTRO_NAME',previous.wsl],['SARSA_DEV_POLL',previous.poll]])if(value===undefined)delete process.env[key];else process.env[key]=value;}
 const output=resolve(process.env.SARSA_EVIDENCE_DIR||resolve(root,'coverage/public-site'));mkdirSync(output,{recursive:true});writeFileSync(resolve(output,'native-coverage.json'),JSON.stringify(globalThis.__sarsaCoverage__));
 console.log(JSON.stringify({checks,files:Object.keys(globalThis.__sarsaCoverage__).length}));
}finally{hook.deregister();}
