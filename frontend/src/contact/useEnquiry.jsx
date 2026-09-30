import {useEffect,useRef,useState} from 'react';
import {contactApi,createAccess,readAccess,saveAccess,clearAccess,messageFor,browserStorage} from './protocol.mjs';

export function useEnquiry(){
 const [receipt,setReceipt]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[started,setStarted]=useState(false),[retry,setRetry]=useState(null);
 const [clock,setClock]=useState(0),[blocked,setBlocked]=useState(false);
 const access=useRef(null),pending=useRef(null),locked=useRef(false),serial=useRef(0),abort=useRef(null),anchor=useRef(null),cooldown=useRef(0);
 const mounted=useRef(false);
 const accept=data=>{anchor.current={server:Date.parse(data.server_now),at:performance.now()};setReceipt(data);setClock(0);setError('');setStarted(true);setRetry(null);};
 async function send(action,fields={}){
  if(locked.current||!access.current||performance.now()<cooldown.current)return;
  locked.current=true;setBusy(true);setError('');const ticket=++serial.current;
  const controller=new AbortController();abort.current=controller;
  try{
   const data=await contactApi(action,access.current,fields,controller.signal);
   if(ticket!==serial.current||!mounted.current)return;
   if(access.current.resend_id&&(data.generation>access.current.resend_generation||data.state==='received')){const next={...access.current};delete next.resend_id;delete next.resend_generation;access.current=saveAccess(browserStorage(),next);}
   pending.current=null;accept(data);
  }catch(failure){
   if(ticket!==serial.current||!mounted.current)return;
   cooldown.current=performance.now()+(failure.retryAfter||0)*1000;
   setError(messageFor(failure));
   if(action==='start'&&failure.code==='invalid_request'){
    try{clearAccess(browserStorage(),access.current);access.current=null;pending.current=null;setStarted(false);setRetry(null);}
    catch{setBlocked(true);}
   }else if(action==='verify'){
    // Never persist or retain a verification code for automatic retries.
    pending.current=null;setRetry('status');
   }else if(action!=='status')setRetry(action);
  }finally{if(ticket===serial.current&&mounted.current){locked.current=false;setBusy(false);}}
 }
 useEffect(()=>{
  mounted.current=true;
  try{access.current=readAccess(browserStorage());if(access.current){setStarted(true);send('status');}}
  catch(failure){setError(messageFor(failure));setBlocked(true);}
  const tick=setInterval(()=>setClock(v=>v+1),1000);
  return()=>{mounted.current=false;++serial.current;abort.current?.abort();locked.current=false;clearInterval(tick);};
 },[]);
 // A bounded read-only delivery check; never starts or verifies a request.
 useEffect(()=>{
  if(!receipt||receipt.state!=='awaiting_verification')return;
  let attempts=0;const timer=setInterval(()=>{if(document.hidden||locked.current)return;if(++attempts>6){clearInterval(timer);return;}send('status');},10000);
  return()=>clearInterval(timer);
 },[receipt?.request_id,receipt?.state,receipt?.generation]);
 const now=anchor.current?anchor.current.server+(performance.now()-anchor.current.at):Date.now();
 void clock;
 return {receipt,busy,error,started,blocked,retry,
  waiting:Math.max(0,Math.ceil((cooldown.current-performance.now())/1000)),
  resendWait:receipt?Math.max(0,Math.ceil((Date.parse(receipt.resend_after)-now)/1000)):0,
  expired:receipt?Date.parse(receipt.code_expires_at)<=now:false,
  async start(payload){if(locked.current||started||blocked)return;try{access.current=createAccess(browserStorage());pending.current={action:'start',fields:structuredClone(payload)};setStarted(true);await send('start',pending.current.fields);}catch(failure){setError(messageFor(failure));}},
  check(){return send('status');},
  verify(code){if(receipt)return send('verify',{generation:receipt.generation,code});},
  async resend(){if(locked.current||!receipt||receipt.sends_remaining<=0||now<Date.parse(receipt.resend_after))return;
   try{if(!access.current.resend_id)access.current=saveAccess(browserStorage(),{...access.current,resend_id:crypto.randomUUID(),resend_generation:receipt.generation});pending.current={action:'resend',fields:{operation_id:access.current.resend_id}};await send('resend',pending.current.fields);}catch(failure){setError(messageFor(failure));}},
  retryRequest(){if(pending.current)return send(pending.current.action,pending.current.fields);if(access.current?.resend_id)return send('resend',{operation_id:access.current.resend_id});return send('status');},
  restart(){if(locked.current||receipt?.state!=='received')return;try{clearAccess(browserStorage(),access.current);access.current=null;pending.current=null;setReceipt(null);setStarted(false);setError('');setRetry(null);}catch(failure){setError(messageFor(failure));}},
 };
}
