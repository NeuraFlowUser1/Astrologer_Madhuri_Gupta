import {createBookingAPI} from './protocol.mjs';
import {createReceiptStore} from './credentials.mjs';
import {createPaymentRecovery} from './payment-recovery.mjs';
import {createRazorpay} from './razorpay.mjs';
import {createBookingController} from './controller.mjs';
import {RequestError} from '../transport.mjs';
import {createReceiptRecovery} from './receipt-recovery.mjs';
import {admissionAllowed,displayAllowed} from '../product-state.mjs';

export function createBookingBrowser(profile,{product,storage=()=>window.sessionStorage,fetcher=globalThis.fetch}={}){
 if(!profile || Object.keys(profile).sort().join(',')!=='environment,installation_id,legacy_callbacks,legacy_receipts,payment,version'
  || profile.version!==1 || typeof product?.getSnapshot!=='function' || typeof product?.subscribe!=='function')throw new RequestError('invalid_configuration');
 const api=createBookingAPI({fetcher}),receipts=createReceiptStore(profile);
 const recovery=createPaymentRecovery({...profile,receipts,storage,api,enabled:()=>admissionAllowed(product.getSnapshot()),subscribeEnabled:product.subscribe});
 const gateway=createRazorpay(profile.payment),payment={...gateway,rememberAndSubmit:recovery.rememberAndSubmit};
 return Object.freeze({api,receipts,recovery,product,receiptRecovery:()=>createReceiptRecovery({receipts,storage,product,fetcher}),
  controller:initialService=>createBookingController({api,receipts,storage,payment,product,initialService})});
}

/** The project supplies its own React. All booking decisions remain in the coordinator. */
export function createUseBooking(React,browser){
 return function useBooking(initialService){
  const ref=React.useRef(null);if(!ref.current)ref.current=browser.controller(initialService);
  const controller=ref.current;
  const state=React.useSyncExternalStore(controller.subscribe,controller.getSnapshot,controller.getSnapshot);
  const display=React.useSyncExternalStore(browser.product.subscribe,browser.product.getSnapshot,browser.product.getSnapshot);
  React.useEffect(()=>controller.start(),[controller]);
  React.useEffect(()=>{if(initialService)controller.edit('service',initialService);},[controller,initialService]);
  const dispatch=React.useCallback(action=>{
   if(action.type==='edit')controller.edit(action.name,action.value);
   else if(action.type==='details')controller.details(action.name,action.value);
   else if(action.type==='ack')controller.acknowledge(action.value);
   else if(action.type==='error')controller.report(action.message);
  },[controller]);
  return {state,dispatch,available:admissionAllowed(display),viewAvailable:displayAllowed(display),start:controller.checkout,resume:controller.resume,restart:controller.restart,check:controller.check,
   retryOriginal:controller.retryOriginal,canRetryOriginal:controller.canRetryOriginal(),loadPolicy:controller.loadPolicy,
   startVerification:controller.startVerification,resendVerification:controller.resendVerification,verifyCode:controller.verifyCode,
   updateReceipt:controller.updateReceipt};
 };
}
