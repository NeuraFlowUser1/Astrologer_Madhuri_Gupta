import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createReceiptRecovery} from '../browser/booking/receipt-recovery.mjs';
import {createReceiptStore} from '../browser/booking/credentials.mjs';
import {installation_id,epoch,policy,receipt} from './booking-browser-fixture.mjs';

const reference='ea79bf9a-6aac-415c-becf-d6d49af3946a';
const other='1f035886-af91-4b81-8181-ef33f67a5186';
const json=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'content-type':'application/json'}});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
async function idle(controller){for(let n=0;n<50 && controller.getSnapshot().busy;n++)await tick();assert.equal(controller.getSnapshot().busy,false);}
function fixture({legacy=false}={}){
 const values=new Map(),storage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};
 const receipts=createReceiptStore({installation_id,environment:'test',legacy_receipts:[{key:'fixture:old',format:'id-hex64'}]});
 if(legacy)values.set('fixture:old',JSON.stringify({id:reference,secret:'a'.repeat(64)}));
 let snapshot={enabled:true,activation_epoch:epoch};const listeners=new Set(),calls=[];
 const product={getSnapshot:()=>snapshot,subscribe:listener=>{listeners.add(listener);return()=>listeners.delete(listener);}};
 const result={values,storage,receipts,calls,product,installed:null,override:null};
 result.change=value=>{snapshot={...snapshot,...value};for(const listener of listeners)listener();};
 result.fetcher=async(path,options)=>{
  const body=options.body?JSON.parse(options.body):null;calls.push({path,body,headers:options.headers});
  if(result.override){const value=await result.override(path,body,options);if(value!==undefined)return value;}
  if(path==='/api/booking-policy')return json(policy());
  if(path==='/api/checkout/status')return result.installed===options.headers['X-Booking-Receipt']?
   json({...receipt(body.request_id),appointment_state:'confirmed',payment_state:'captured',captured_paise:210000}):json({code:'access_unavailable'},403);
  assert.equal(path,'/api/checkout/recover-receipt');
  assert.equal(receipts.readRecovery(storage).secret,body.secret,'Replacement must be saved before the request');
  if(body.code!=='12345678')return json({code:'access_unavailable'},403);
  result.installed=body.secret;return json({code:'receipt_restored'});
 };
 result.make=()=>createReceiptRecovery({receipts,storage:()=>storage,product,fetcher:result.fetcher});
 return result;
}

test('verified replacement retires only the same booking historical secret and stays usable after remount',async()=>{
 const f=fixture({legacy:true}),c=f.make();c.start();await c.restore(reference,'12345678');
 assert.equal(c.getSnapshot().restored,true);assert.equal(f.receipts.readReceipt(f.storage).secret,f.installed);
 assert.equal(f.receipts.readRecovery(f.storage),null);assert.equal(f.values.has('fixture:old'),false);
 const count=f.calls.length;await c.restore(reference,'12345678');assert.equal(f.calls.length,count);
 c.stop();c.start();await tick();assert.equal(c.getSnapshot().restored,true);assert.equal(f.calls.length,count);c.stop();
});

test('lost redemption response survives reload and confirms saved access without redeeming twice',async()=>{
 const f=fixture();f.override=(path,body)=>{if(path.endsWith('/recover-receipt')){f.installed=body.secret;throw Error('connection lost');}};
 let c=f.make();c.start();await c.restore(reference,'12345678');assert.equal(c.getSnapshot().restored,false);
 const staged=f.receipts.readRecovery(f.storage);assert.ok(staged);assert.equal(f.receipts.readReceipt(f.storage),null);c.stop();
 f.override=null;c=f.make();c.start();await idle(c);
 assert.equal(c.getSnapshot().restored,true);assert.equal(f.receipts.readReceipt(f.storage).secret,staged.secret);
 assert.equal(f.calls.filter(call=>call.path.endsWith('/recover-receipt')).length,1);c.stop();
});

test('wrong code keeps the staged credential and a corrected code uses that exact credential',async()=>{
 const f=fixture(),c=f.make();c.start();await c.restore(reference,'00000000');
 const staged=f.receipts.readRecovery(f.storage);assert.ok(staged);assert.equal(f.receipts.readReceipt(f.storage),null);
 assert.equal(c.getSnapshot().restored,false);await c.restore(reference,'12345678');assert.equal(c.getSnapshot().restored,true);
 assert.equal(f.installed,staged.secret);assert.equal(JSON.stringify([...f.values]).includes('12345678'),false);c.stop();
});

test('a saved different booking cannot be overwritten during recovery',async()=>{
 const f=fixture(),prior=f.receipts.prepareReceipt(f.storage,policy()),c=f.make();c.start();
 await c.restore(reference,'12345678');assert.equal(c.getSnapshot().restored,false);
 assert.deepEqual(f.receipts.readReceipt(f.storage),prior);assert.equal(f.calls.some(call=>call.path.endsWith('/recover-receipt')),false);c.stop();
});

test('unreadable storage and unsaved replacement never send a redemption request',async()=>{
 for(const corrupt of [false,true]){
  const f=fixture();if(corrupt)f.values.set(f.receipts.storageKey,']');
  else f.storage.setItem=()=>{throw Error('storage denied');};
  const c=f.make();c.start();await c.restore(reference,'12345678');
  assert.equal(c.getSnapshot().restored,false);assert.equal(f.calls.some(call=>call.path.endsWith('/recover-receipt')),false);c.stop();
 }
});

test('uncertain status on reload retains the credential and never retries redemption automatically',async()=>{
 const f=fixture();f.receipts.prepareRecovery(f.storage,reference,policy());
 f.override=path=>path.endsWith('/status')?json({code:'temporarily_unavailable'},503):undefined;
 const c=f.make();c.start();await idle(c);assert.ok(f.receipts.readRecovery(f.storage));
 await c.restore(reference,'12345678');assert.equal(f.calls.some(call=>call.path.endsWith('/recover-receipt')),false);c.stop();
});

test('switching off ignores late completion and returning on recovers the saved outcome',async()=>{
 const f=fixture();let release,entered;const wait=new Promise(resolve=>{entered=resolve;});
 f.override=async(path,body)=>{if(path.endsWith('/recover-receipt')){f.installed=body.secret;entered();await new Promise(resolve=>{release=resolve;});return json({code:'receipt_restored'});}};
 const c=f.make();c.start();const pending=c.restore(reference,'12345678');await wait;
 f.change({enabled:false});release();await pending;assert.equal(c.getSnapshot().restored,false);
 assert.equal(f.receipts.readReceipt(f.storage),null);assert.ok(f.receipts.readRecovery(f.storage));
 f.override=null;f.change({enabled:true,activation_epoch:other});await idle(c);
 assert.equal(c.getSnapshot().restored,true);assert.equal(f.calls.filter(call=>call.path.endsWith('/recover-receipt')).length,1);c.stop();
});

test('failed local promotion retains the staged reference and can finish on reload',async()=>{
 const f=fixture(),set=f.storage.setItem;f.storage.setItem=(key,value)=>{if(key===f.receipts.storageKey)throw Error('disk full');set(key,value);};
 let c=f.make();c.start();await c.restore(reference,'12345678');assert.equal(c.getSnapshot().restored,false);
 assert.ok(f.receipts.readRecovery(f.storage));c.stop();f.storage.setItem=set;
 c=f.make();c.start();await idle(c);assert.equal(c.getSnapshot().restored,true);c.stop();
});

test('invalid input and disabled product make no requests',async()=>{
 const f=fixture(),c=f.make();c.start();await c.restore('bad','12345678');await c.restore(reference,'12');
 assert.equal(f.calls.length,0);f.change({enabled:false});await c.restore(reference,'12345678');
 assert.equal(f.calls.length,0);c.stop();
});

test('recovery input types, conflicting staged reference and unreadable storage never redeem a code',async()=>{
 const f=fixture(),c=f.make();c.start();let notices=0;const unsubscribe=c.subscribe(()=>notices++);
 await c.restore(null,'12345678');await c.restore(reference,null);await c.check();assert.equal(f.calls.length,0);
 f.receipts.prepareRecovery(f.storage,reference,policy());c.stop();const staged=f.make();staged.start();await idle(staged);
 await staged.restore(other,'12345678');assert.equal(f.calls.some(call=>call.path.endsWith('/recover-receipt')),false);
 assert.equal(f.receipts.readRecovery(f.storage).request_id,reference);staged.stop();assert.ok(notices>0);unsubscribe();
 f.storage.getItem=()=>{throw Error('storage denied');};const blocked=f.make();blocked.start();assert.equal(blocked.getSnapshot().blocked,true);
 const count=f.calls.length;await blocked.restore(reference,'12345678');assert.equal(f.calls.length,count);blocked.stop();
});

test('wrong success code or wrong booking status cannot promote recovery access',async()=>{
 for(const mode of ['reply','status']){
  const f=fixture();f.override=(path,body)=>{
   if(mode==='reply'&&path.endsWith('/recover-receipt'))return json({code:'unexpected'});
   if(mode==='status'&&path.endsWith('/status'))return json(receipt(other));
  };
  const c=f.make();c.start();await c.restore(reference,'12345678');assert.equal(c.getSnapshot().restored,false);
  assert.equal(f.receipts.readReceipt(f.storage),null);assert.ok(f.receipts.readRecovery(f.storage));c.stop();
 }
});

test('off during policy or saved-status lookup ignores late replies and cannot create replacement access',async()=>{
 for(const phase of ['policy','status']){
  const f=fixture();if(phase==='status')f.receipts.prepareRecovery(f.storage,reference,policy());
  let release,enter;const entered=new Promise(resolve=>{enter=resolve;});
  f.override=async(path,body)=>{
   if((phase==='policy'&&path==='/api/booking-policy')||(phase==='status'&&path.endsWith('/status'))){
    enter();await new Promise(resolve=>{release=resolve;});return json(phase==='policy'?policy():receipt(reference));
   }
  };
  const c=f.make();c.start();const waiting=phase==='policy'?c.restore(reference,'12345678'):null;await entered;
  await c.restore(reference,'12345678');f.change({enabled:false});release();if(waiting)await waiting;await idle(c);
  assert.equal(c.getSnapshot().restored,false);assert.equal(f.receipts.readReceipt(f.storage),null);assert.equal(f.calls.some(call=>call.path.endsWith('/recover-receipt')),false);c.stop();
 }
});

test('successful staged access is checked once and unrelated product updates do not restart it',async()=>{
 const f=fixture();const staged=f.receipts.prepareRecovery(f.storage,reference,policy());f.installed=staged.secret;
 const c=f.make();const stop=c.start();assert.equal(c.start(),stop);await idle(c);assert.equal(c.getSnapshot().restored,true);
 const count=f.calls.length;f.change({enabled:true});await tick();assert.equal(f.calls.length,count);stop();
});
