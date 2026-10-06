import {createTransport,RequestError} from '../transport.mjs';
import {checkedReceipt} from './protocol.mjs';
import {messageFor} from './messages.mjs';

export function createReceiptRecovery({receipts,storage,product,fetcher=globalThis.fetch}){
 const request=createTransport({fetcher,maximum:32768,timeout:20000,
  allowed:path=>['/api/booking-policy','/api/checkout/status','/api/checkout/recover-receipt'].includes(path)});
 let staged=null,blocked=false,error='';
 try{staged=receipts.readRecovery(storage());}catch(e){blocked=true;error=messageFor(e);}
 let state=Object.freeze({reference:staged?.request_id||'',busy:false,restored:false,error,blocked});
 let alive=false,generation=0,write,unsubscribe,busy=false;const listeners=new Set();
 const notify=change=>{state=Object.freeze({...state,...change});for(const listener of listeners)listener();};
 const enabled=()=>alive && product.getSnapshot().enabled===true;
 const mark=()=>({generation,epoch:product.getSnapshot().activation_epoch});
 const current=value=>enabled() && value.generation===generation && value.epoch===product.getSnapshot().activation_epoch;
 async function operation(work){
  if(!enabled() || busy || blocked || state.restored)return;
  const saved=mark(),abort=write=new AbortController();busy=true;notify({busy:true,error:''});
  try{await work(saved,abort.signal);}catch(e){if(current(saved))notify({error:messageFor(e)});}
  finally{if(current(saved)){busy=false;write=null;notify({busy:false});}}
 }
 async function check(saved,signal,{expected=false}={}){
  if(!staged)return false;
  try{
   const reply=await request('/api/checkout/status',{body:{request_id:staged.request_id},headers:{'X-Booking-Receipt':staged.secret},signal});
   checkedReceipt(reply,staged.request_id);if(!current(saved))return false;
   const reference=staged.request_id;
   receipts.commitRecovery(storage(),staged);staged=null;notify({restored:true,reference});return true;
  }catch(e){
   if(!expected && e instanceof RequestError && e.status===403 && e.code==='access_unavailable')return false;
   throw e;
  }
 }
 const restore=(reference,code)=>operation(async(saved,signal)=>{
  if(typeof reference!=='string' || typeof code!=='string')throw new RequestError('invalid_request');
  reference=reference.trim().toLowerCase();code=code.trim();
  if(!/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/.test(reference) || !/^[0-9]{8}$/.test(code))throw new RequestError('invalid_request');
  if(staged && staged.request_id!==reference)throw new RequestError('receipt_conflict');
  if(staged && await check(saved,signal))return;if(!current(saved))return;
  if(!staged){
   const policy=await request('/api/booking-policy',{signal});if(!current(saved))return;
   staged=receipts.prepareRecovery(storage(),reference,policy);notify({reference});
  }
  const reply=await request('/api/checkout/recover-receipt',{body:{request_id:reference,code,secret:staged.secret},signal});
  if(reply.code!=='receipt_restored')throw new RequestError('invalid_response');
  if(current(saved))await check(saved,signal,{expected:true});
 });
 function stop(){alive=false;generation++;write?.abort();write=null;busy=false;unsubscribe?.();}
 function start(){
  if(alive)return stop;alive=true;generation++;busy=false;notify({busy:false});
  let active=product.getSnapshot().enabled===true,epoch=product.getSnapshot().activation_epoch;
  unsubscribe=product.subscribe(()=>{
   const p=product.getSnapshot();if(p.enabled===active && p.activation_epoch===epoch)return;
   active=p.enabled;epoch=p.activation_epoch;generation++;write?.abort();write=null;busy=false;notify({busy:false,restored:false});
   if(enabled() && staged)void operation((saved,signal)=>check(saved,signal));
  });
  if(enabled() && staged)void operation((saved,signal)=>check(saved,signal));return stop;
 }
 return Object.freeze({getSnapshot:()=>state,subscribe:listener=>{listeners.add(listener);return()=>listeners.delete(listener);},
  start,stop,restore,check:()=>operation((saved,signal)=>check(saved,signal))});
}

export function createUseReceiptRecovery(React,browser){
 return function useReceiptRecovery(){
  const ref=React.useRef(null);if(!ref.current)ref.current=browser.receiptRecovery();
  const controller=ref.current,state=React.useSyncExternalStore(controller.subscribe,controller.getSnapshot,controller.getSnapshot);
  React.useEffect(()=>controller.start(),[controller]);return {...state,restore:controller.restore,check:controller.check};
 };
}
