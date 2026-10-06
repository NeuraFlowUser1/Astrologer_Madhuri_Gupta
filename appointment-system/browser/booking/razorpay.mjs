import {RequestError} from '../transport.mjs';

export function createRazorpay({name,description,color,windowObject=globalThis.window,documentObject=globalThis.document,
 setTimer=globalThis.setTimeout,clearTimer=globalThis.clearTimeout}){
 if(typeof name!=='string' || !name || name.length>150 || typeof description!=='string' || description.length>200
  || !/^#[a-fA-F0-9]{6}$/.test(color))throw new RequestError('invalid_configuration');
 let loading;
 function load(){
  if(typeof windowObject.Razorpay==='function')return Promise.resolve();if(loading)return loading;
  const pending=new Promise((resolve,reject)=>{
   const script=documentObject.createElement('script');let settled=false,timer;
   const finish=success=>{if(settled)return;settled=true;clearTimer(timer);script.onload=null;script.onerror=null;
    if(success)resolve();else{script.remove();reject(new RequestError('payment_unavailable'));}};
   script.src='https://checkout.razorpay.com/v1/checkout.js';script.async=true;
   timer=setTimer(()=>finish(false),20000);script.onerror=()=>finish(false);script.onload=()=>finish(typeof windowObject.Razorpay==='function');
   try{documentObject.head.append(script);}catch{finish(false);}
  });loading=pending;
  const release=()=>{if(loading===pending)loading=undefined;};void pending.then(release,release);return pending;
 }
 function open(checkout,{onSuccess,onClose}){
  let finished=false,closed=false;
  let payment;try{payment=new windowObject.Razorpay({key:checkout.key_id,order_id:checkout.order_id,amount:checkout.amount_paise,
   currency:checkout.currency,name,description,theme:{color},handler(result){
    if(finished)return;finished=true;void onSuccess({razorpay_order_id:result.razorpay_order_id,
     razorpay_payment_id:result.razorpay_payment_id,razorpay_signature:result.razorpay_signature});
   },modal:{ondismiss(){if(!finished && !closed){closed=true;onClose();}}}});
   payment.open();}catch{throw new RequestError('payment_unavailable');}
  // Closing the UI must not discard a signed success delivered after navigation.
  return()=>{if(!closed){closed=true;payment.close();}};
 }
 return Object.freeze({load,open});
}
