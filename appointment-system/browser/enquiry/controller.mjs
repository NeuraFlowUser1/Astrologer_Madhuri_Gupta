import {RequestError} from '../transport.mjs';
import {messageFor} from './messages.mjs';

/** Enquiries remain independent of booking mode, payments and booking verification. */
export function createEnquiryController({api,receipts,storage,cryptoSource=globalThis.crypto,
 clock=Date.now,monotonic=()=>performance.now(),documentObject=globalThis.document,
 interval=globalThis.setInterval,clearInterval=globalThis.clearInterval}){
 let access=null,blocked=false,error='';
 try{access=receipts.read(storage());}catch(e){blocked=true;error=messageFor(e);}
 let state=Object.freeze({receipt:null,busy:false,error,started:!!access,blocked,retry:null,waiting:0,resendWait:0,expired:false});
 let alive=false,generation=0,busy=false,request,timer,anchor=null,cooldown=0,pending=null,polls=0,lastPoll=0;
 const listeners=new Set(),notify=change=>{state=Object.freeze({...state,...change});for(const listener of listeners)listener();};
 const current=mark=>alive && generation===mark;
 const now=()=>anchor?anchor.server+monotonic()-anchor.at:clock();
 function timers(){
  const waiting=Math.max(0,Math.ceil((cooldown-monotonic())/1000));
  const resendWait=state.receipt?Math.max(0,Math.ceil((Date.parse(state.receipt.resend_after)-now())/1000)):0;
  const expired=!!state.receipt && Date.parse(state.receipt.code_expires_at)<=now();
  if(waiting!==state.waiting || resendWait!==state.resendWait || expired!==state.expired)notify({waiting,resendWait,expired});
 }
 function accept(data){
  if(access.resend_id && (data.generation>access.resend_generation || data.state==='received')){
   const value={...access};delete value.resend_id;delete value.resend_generation;access=receipts.save(storage(),value);
  }
  if(state.receipt?.generation!==data.generation){polls=0;lastPoll=monotonic();}
  anchor={server:Date.parse(data.server_now),at:monotonic()};pending=null;
  notify({receipt:data,started:true,error:'',retry:access.resend_id?'resend':null});timers();
 }
 async function send(action,fields,mark,signal){
  const firstStart=action==='start' && pending?.sends===0;
  if(action==='start' && pending)pending.sends++;
  try{
   const result=await api.send(action,access,fields,signal);if(current(mark))accept(result);
  }catch(e){
   if(!current(mark))return;
   // Only an initial, definite validation rejection can release a new reference.
   // A later retry may follow a lost successful response; preserve that reference.
   if(firstStart && e instanceof RequestError && e.status===422 && e.code==='invalid_request'){
    receipts.clear(storage(),access);access=null;pending=null;notify({started:false,receipt:null,retry:null});
   }else notify({retry:action==='verify'?'status':pending?'start':access?.resend_id?'resend':'status'});
   throw e;
  }
 }
 async function operation(work){
  if(!alive || busy || state.blocked || monotonic()<cooldown)return;
  busy=true;const mark=generation,abort=request=new AbortController();notify({busy:true,error:''});
  try{return await work(mark,abort.signal);}catch(e){if(current(mark)){
   cooldown=monotonic()+Math.max(0,Math.min(3600,e.retryAfter||0))*1000;
   notify({error:messageFor(e)});timers();
  }}finally{if(current(mark)){busy=false;request=null;notify({busy:false});}}
 }
 const check=()=>operation((mark,signal)=>access?send('status',{},mark,signal):undefined);
 const submit=payload=>operation(async(mark,signal)=>{
  if(access || state.started)return;
  const fields=structuredClone(payload),policy=await api.policy(signal);if(!current(mark))return;
  access=receipts.create(storage(),policy,cryptoSource);pending={fields,sends:0};notify({started:true});
  await send('start',fields,mark,signal);
 });
 const verify=code=>operation(async(mark,signal)=>{
  if(!access || !state.receipt || state.receipt.state!=='awaiting_verification' || now()>=Date.parse(state.receipt.code_expires_at))return;
  if(typeof code!=='string' || !/^[0-9]{6}$/.test(code))throw new RequestError('invalid_request');
  // The code is passed only to this call. It is never persisted or retained for retry.
  await send('verify',{generation:state.receipt.generation,code},mark,signal);
 });
 const resend=()=>operation(async(mark,signal)=>{
  const receipt=state.receipt;if(!access || !receipt || receipt.state==='received' || receipt.sends_remaining<=0
    || now()<Date.parse(receipt.resend_after))return;
  if(!access.resend_id)access=receipts.save(storage(),{...access,resend_id:cryptoSource.randomUUID(),resend_generation:receipt.generation});
  await send('resend',{operation_id:access.resend_id},mark,signal);
 });
 const retryRequest=()=>operation(async(mark,signal)=>{
  if(!access)return;
  if(pending)await send('start',pending.fields,mark,signal);
  else if(access.resend_id)await send('resend',{operation_id:access.resend_id},mark,signal);
  else await send('status',{},mark,signal);
 });
 const restart=()=>operation(async(mark,signal)=>{
  if(!access || state.receipt?.state!=='received')return;
  await send('status',{},mark,signal);if(!current(mark) || state.receipt?.state!=='received')return;
  receipts.clear(storage(),access);access=null;pending=null;anchor=null;polls=0;
  notify({receipt:null,started:false,retry:null,waiting:0,resendWait:0,expired:false,error:''});
  return true;
 });
 function stop(){alive=false;generation++;request?.abort();request=null;busy=false;clearInterval(timer);}
 function start(){
  if(alive)return stop;alive=true;generation++;busy=false;notify({busy:false});if(access)void check();
  lastPoll=monotonic();timer=interval(()=>{
   timers();if(state.receipt?.state!=='awaiting_verification' || busy || documentObject?.hidden || polls>=6 || monotonic()-lastPoll<10000)return;
   lastPoll=monotonic();polls++;void check();
  },1000);return stop;
 }
 return Object.freeze({getSnapshot:()=>state,subscribe:listener=>{listeners.add(listener);return()=>listeners.delete(listener);},
  start,stop,submit,check,verify,resend,retryRequest,restart});
}
