import {RequestError} from '../transport.mjs';
import {checkedReceipt} from './protocol.mjs';

/** Opaque signed references only. This never opens checkout or claims payment success. */
export function createPaymentRecovery({installation_id,environment,legacy_callbacks=[],receipts,storage,api,enabled,subscribeEnabled,clock=Date.now}){
 if(!/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(installation_id) || !['production','development','test'].includes(environment)
  || typeof enabled!=='function' || subscribeEnabled!==undefined && typeof subscribeEnabled!=='function'
  || !Array.isArray(legacy_callbacks) || legacy_callbacks.length>4)throw new RequestError('invalid_configuration');
 const key=`appointment:${installation_id}:${environment}:signed-payment:v2`,readers=[{key,current:true}];
 for(const row of legacy_callbacks){
  if(!row || Object.keys(row).sort().join(',')!=='key,project' || typeof row.key!=='string' || !/^[A-Za-z0-9:_-]{1,120}$/.test(row.key)
   || typeof row.project!=='string' || !/^[A-Za-z0-9:_-]{1,120}$/.test(row.project) || readers.some(value=>value.key===row.key))throw new RequestError('invalid_configuration');
  readers.push({...row,current:false});
 }
 let memory=[],lastAttempt=-Infinity,recovering;
 const submissions=new Map(),identity=row=>row.request_id+':'+row.payment_id;
 function valid(row,reader){
  const fields=reader.current?'created_at,environment,installation_id,order_id,payment_id,request_id,signature,version'
   :'created_at,order_id,payment_id,project,request_id,signature,version';
  return row && Object.keys(row).sort().join(',')===fields
   && (reader.current?(row.version===2 && row.installation_id===installation_id && row.environment===environment):(row.version===1 && row.project===reader.project))
   && /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i.test(row.request_id)
   && /^order_[A-Za-z0-9]{1,64}$/.test(row.order_id) && /^pay_[A-Za-z0-9]{1,64}$/.test(row.payment_id)
   && /^[a-f0-9]{64}$/.test(row.signature) && Number.isSafeInteger(row.created_at) && row.created_at>=0 && row.created_at<=clock()+60000;
 }
 function read(reader){
  try{const raw=storage().getItem(reader.key);if(raw===null)return [];
   if(typeof raw!=='string' || raw.length>65536)return null;const rows=JSON.parse(raw);return Array.isArray(rows)&&rows.length<=128?rows:null;
  }catch{return null;}
 }
 function rows(){
  const all=[...memory,...readers.flatMap(reader=>(read(reader)||[]).filter(row=>valid(row,reader)))],unique=new Map();
  for(const row of all){const prior=unique.get(identity(row));
   if(prior && (prior.signature!==row.signature || prior.order_id!==row.order_id))throw new RequestError('payment_reference_conflict');
   unique.set(identity(row),row);
  }return [...unique.values()];
 }
 function save(credential,signed,expectedOrder){
  const row={version:2,installation_id,environment,request_id:credential.request_id,order_id:signed.razorpay_order_id,
   payment_id:signed.razorpay_payment_id,signature:signed.razorpay_signature,created_at:clock()};
  if(!valid(row,readers[0]) || row.order_id!==expectedOrder)throw new RequestError('payment_reference_invalid');
  const old=rows().find(value=>identity(value)===identity(row));
  if(old && (old.signature!==row.signature || old.order_id!==row.order_id))throw new RequestError('payment_reference_conflict');
  if(old)return old;
  if(memory.length>=128)throw new RequestError('payment_reference_limit');
  memory.push(row);
  // Never overwrite unreadable or oversized saved evidence to make room.
  const saved=read(readers[0]);if(saved===null)return row;
  const combined=[...saved,...memory.filter(value=>!saved.some(existing=>existing && identity(existing)===identity(value)))];
  const encoded=JSON.stringify(combined);
  if(combined.length<=128 && encoded.length<=65536)try{storage().setItem(key,encoded);}catch{/* Exact callback stays in memory. */}
  return row;
 }
 function acknowledge(row){
  memory=memory.filter(value=>identity(value)!==identity(row));
  for(const reader of readers){const saved=read(reader);if(saved===null)continue;
   const kept=saved.filter(value=>!valid(value,reader) || identity(value)!==identity(row));
   if(kept.length===saved.length)continue;
   try{if(kept.length)storage().setItem(reader.key,JSON.stringify(kept));else storage().removeItem(reader.key);}catch{/* Replay remains safe. */}
  }
 }
 function send(row,credential){
  if(!enabled())return Promise.reject(new RequestError('booking_disabled'));
  if(credential.request_id!==row.request_id)return Promise.reject(new RequestError('payment_reference_conflict'));
  const id=identity(row);if(submissions.has(id))return submissions.get(id);
  const pending=(async()=>{
   const result=await api('/api/checkout/verify-payment',{credential,body:{request_id:row.request_id,
    razorpay_order_id:row.order_id,razorpay_payment_id:row.payment_id,razorpay_signature:row.signature}});
   checkedReceipt(result.receipt,credential.request_id);acknowledge(row);return result;
  })().finally(()=>submissions.delete(id));submissions.set(id,pending);return pending;
 }
 function recover(){
  if(recovering)return recovering;if(!enabled() || clock()-lastAttempt<60000)return Promise.resolve();
  let credential,pending;try{credential=receipts.readReceipt(storage());pending=rows().filter(row=>row.request_id===credential?.request_id);}catch{return Promise.resolve();}
  if(!pending.length)return Promise.resolve();lastAttempt=clock();
  recovering=(async()=>{for(const row of pending)await send(row,credential);})().finally(()=>{recovering=null;});return recovering;
 }
 function start(windowObject=window,documentObject=document){
  const check=()=>{if(documentObject.visibilityState==='visible')void recover().catch(()=>{});};
  windowObject.addEventListener('pageshow',check);windowObject.addEventListener('focus',check);documentObject.addEventListener('visibilitychange',check);check();
  const unsubscribe=subscribeEnabled?.(check);
  return()=>{unsubscribe?.();windowObject.removeEventListener('pageshow',check);windowObject.removeEventListener('focus',check);documentObject.removeEventListener('visibilitychange',check);};
 }
 return Object.freeze({save,recover,start,rememberAndSubmit:(credential,signed,order)=>send(save(credential,signed,order),credential),storageKey:key});
}
