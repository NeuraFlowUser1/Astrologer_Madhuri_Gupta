import {expect,test,vi,afterEach} from 'vitest';
import {randomUUID} from 'node:crypto';
import {createPaymentRecovery} from '../../../appointment-system/browser/booking/payment-recovery.mjs';
import {installation_id,receipt} from '../../../appointment-system/tests/booking-browser-fixture.mjs';
const project='004',key='synthetic-pending-callback',id=randomUUID(),credential={request_id:id,secret:'a'.repeat(64)};
const signed=(change={})=>({razorpay_order_id:'order_synthetic',razorpay_payment_id:'pay_synthetic',razorpay_signature:'a'.repeat(64),...change});
const row=(change={})=>({version:1,project,request_id:id,order_id:'order_synthetic',payment_id:'pay_synthetic',signature:'a'.repeat(64),created_at:0,...change});
// Test-only compatibility inputs exercise the contained replacement directly.
// The fake API returns a schema-valid receipt; no network or payment is made.
function fixture({stored,denied,read,submit,clock}={}){
 const values=new Map();if(stored!==undefined)values.set(key,stored);
 const store={getItem:name=>{if(denied==='get')throw Error('denied');return values.get(name)??null;},
  setItem:(name,next)=>{if(denied==='set')throw Error('denied');values.set(name,next);},
  removeItem:name=>{if(denied==='remove')throw Error('denied');values.delete(name);}};
 const transport=submit||vi.fn(async()=>({checked:true}));
 const api=createPaymentRecovery({installation_id,environment:'test',legacy_callbacks:[{key,project}],storage:()=>store,
  receipts:{readReceipt:read||(()=>credential)},enabled:()=>true,clock:clock||(()=>1000),
  api:async(path,{credential:owner,body})=>{
   expect(path).toBe('/api/checkout/verify-payment');
   expect(body.request_id).toBe(owner.request_id);
   await transport(owner,body);return {receipt:receipt(owner.request_id)};
  }});
 return {api,transport,stored:()=>values.get(api.storageKey)??values.get(key)??null,legacyStored:()=>values.get(key)};
}
test.each([null,{},'wrong',[],[row({project:'foreign'})],[row({signature:'bad'})],[row({created_at:900000})]])('invalid stored callback %j never submits for another owner',async value=>{const f=fixture({stored:JSON.stringify(value)});await f.api.recover();expect(f.transport).not.toHaveBeenCalled();});
test.each([{version:2},{request_id:'bad'},{order_id:'bad'},{payment_id:'bad'},{signature:'bad'},{created_at:-1},{created_at:'1'},{extra:'private'},{project:'foreign'}])('malformed %j evidence is ignored without claiming local payment',async change=>{const f=fixture({stored:JSON.stringify([row(change)])});await f.api.recover();expect(f.transport).not.toHaveBeenCalled();});
test.each(['get','set','remove'])('storage %s denial preserves exact hot-tab payment evidence',async denied=>{let failed=true;const transport=vi.fn(async()=>{if(failed)throw Error('uncertain provider outcome');return {checked:true};});const f=fixture({denied,submit:transport});await expect(f.api.rememberAndSubmit(credential,signed(),'order_synthetic')).rejects.toThrow('uncertain');failed=false;await f.api.recover();expect(transport).toHaveBeenCalledTimes(2);expect(transport.mock.calls[0][1]).toEqual(transport.mock.calls[1][1]);});
test('conflicting callback never overwrites earlier signed evidence and expected order is mandatory',()=>{const f=fixture();f.api.save(credential,signed(),'order_synthetic');expect(()=>f.api.save(credential,signed({razorpay_signature:'b'.repeat(64)}),'order_synthetic')).toThrow('conflict');expect(()=>f.api.save(credential,signed(),'order_foreign')).toThrow('invalid');expect(()=>f.api.save(credential,signed({razorpay_payment_id:'bad'}),'order_synthetic')).toThrow('invalid');expect(JSON.parse(f.stored())).toHaveLength(1);});
test('duplicate observations recover once while unreadable old evidence is preserved',async()=>{const f=fixture({stored:'broken'});f.api.save(credential,signed(),'order_synthetic');f.api.save(credential,signed(),'order_synthetic');await f.api.recover();expect(f.transport).toHaveBeenCalledOnce();expect(f.legacyStored()).toBe('broken');});
test('concurrent recovery shares one attempt and does not erase a different receipt callback',async()=>{let finish;const transport=vi.fn(()=>new Promise(resolve=>{finish=resolve;})),other=row({request_id:randomUUID(),payment_id:'pay_other'});const f=fixture({stored:JSON.stringify([other,row(),row()]),submit:transport});const first=f.api.recover(),second=f.api.recover();expect(first).toBe(second);expect(transport).toHaveBeenCalledOnce();finish({checked:true});await first;expect(JSON.parse(f.stored())).toEqual([other]);});
test('lost response is rate bounded and only the same payment is retried after the interval',async()=>{let now=1000,failed=true;const transport=vi.fn(async()=>{if(failed)throw Error('lost');});const f=fixture({stored:JSON.stringify([row()]),clock:()=>now,submit:transport});await expect(f.api.recover()).rejects.toThrow('lost');await f.api.recover();expect(transport).toHaveBeenCalledOnce();now+=60000;failed=false;await f.api.recover();expect(transport).toHaveBeenCalledTimes(2);});
test.each([null,'throw'])('unavailable %s receipt cannot expose or submit another payment',async mode=>{const f=fixture({stored:JSON.stringify([row()]),read:()=>{if(mode==='throw')throw Error('blocked');return null;}});await f.api.recover();expect(f.transport).not.toHaveBeenCalled();});
test('visibility listeners pause while hidden and detach on unmount',async()=>{const windowObject=new EventTarget(),documentObject=new EventTarget();documentObject.visibilityState='hidden';const f=fixture({stored:JSON.stringify([row()])});const stop=f.api.start(windowObject,documentObject);windowObject.dispatchEvent(new Event('focus'));expect(f.transport).not.toHaveBeenCalled();documentObject.visibilityState='visible';documentObject.dispatchEvent(new Event('visibilitychange'));await Promise.resolve();await Promise.resolve();expect(f.transport).toHaveBeenCalledOnce();stop();windowObject.dispatchEvent(new Event('pageshow'));expect(f.transport).toHaveBeenCalledOnce();});
test('oversized corrupt browser storage is ignored and never used as payment authority',async()=>{const f=fixture({stored:'x'.repeat(65537)});await f.api.recover();expect(f.transport).not.toHaveBeenCalled();});
