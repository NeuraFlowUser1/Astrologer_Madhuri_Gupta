import {checkedReceipt,checkedEmailCopy,requireValue,integer} from './protocol.mjs';
import {admissionAllowed} from '../product-state.mjs';
import {pdfFacts,buildAppointmentPDF} from './receipt-pdf.mjs';

const explanation={revision_changed:'Your appointment changed. Review its current details before trying again.',
 request_conflict:'This request differs from the saved request. Check your booking before trying again.',
 email_destination_conflict:'Use the email address already saved with this appointment.',booking_not_confirmed:'Email copies are available for confirmed appointments.',
 copy_pending:'Your earlier email copy is still being checked.',copy_limit:'The daily limit for email copies has been reached.',
 copy_cooldown:'Please wait before requesting another email copy.',email_destination_unavailable:'This address cannot receive the copy. Check the address or contact the practice.',
 copy_unavailable:'Email copies are temporarily unavailable. Your appointment remains saved.'};
const copyFacts=value=>JSON.stringify(Object.keys(value).sort().map(key=>[key,value[key]]));

/** Independent actions, with no draft storage, payment calls or additional status timer. */
export function createReceiptActions({api,product,getCredential,getReceipt,onReceipt,brand,loadPDF,
 cryptoSource=globalThis.crypto,urls=globalThis.URL,setTimer=setTimeout,clearTimer=clearTimeout}){
 let alive=false,sequence=0,operation=null,operationBase=null,observedOperation=null,emailError=false,url=null,expiry=null,prepared=null,pdfWrite=null,emailWrite=null,stopProduct;
 let state=Object.freeze({pdfBusy:false,emailBusy:false,emailUncertain:false,pdfURL:null,filename:null,message:'',error:''});
 const listeners=new Set(),notify=change=>{state=Object.freeze({...state,...change});for(const listener of listeners)listener();};
 const allowed=()=>alive && admissionAllowed(product.getSnapshot());
 function revoke(){if(url)urls.revokeObjectURL(url);url=null;clearTimer(expiry);expiry=null;notify({pdfURL:null,filename:null});}
 const mark=()=>({sequence,epoch:product.getSnapshot().activation_epoch,credential:getCredential()});
 const same=m=>alive && m.sequence===sequence && m.epoch===product.getSnapshot().activation_epoch
  && m.credential?.request_id===getCredential()?.request_id && m.credential?.secret===getCredential()?.secret;
 async function fresh(m,signal){
  if(!allowed() || !m.credential)throw Error('unavailable');
  const r=checkedReceipt(await api('/api/checkout/status',{body:{request_id:m.credential.request_id},credential:m.credential,signal}),m.credential.request_id);
  if(!same(m))throw Error('unavailable');const accepted=onReceipt(r);
  const latest=accepted||getReceipt();
  if(latest && (latest.booking_revision>r.booking_revision || latest.booking_revision===r.booking_revision
   && Date.parse(latest.server_now)>Date.parse(r.server_now)))throw Error('receipt_changed');
  return r;
 }
 function offer(file,facts){
  revoke();prepared={...file,facts};url=urls.createObjectURL(new Blob([file.bytes],{type:'application/pdf'}));
  notify({pdfURL:url,filename:file.filename,message:'Your PDF is ready. Use Download PDF or Open PDF.'});
  expiry=setTimer(()=>revoke(),5000);
 }
 async function pdf(){
  if(!allowed() || state.pdfBusy)return;const m=mark(),abort=pdfWrite=new AbortController();emailError=false;notify({pdfBusy:true,error:'',message:''});
  try{
   const before=await fresh(m,abort.signal),facts=pdfFacts(before);
   if(before.appointment_state!=='confirmed' || !before.booking_revision || !before.meeting_mode)throw Error('receipt_changed');
   const file=prepared?.facts===facts?prepared:await buildAppointmentPDF(before,{brand,load:loadPDF});
   const after=await fresh(m,abort.signal);
   if(facts!==pdfFacts(after)){prepared=null;revoke();throw Error('receipt_changed');}
   if(!same(m) || !allowed())throw Error('unavailable');
   if(facts!==pdfFacts(getReceipt()||{}))throw Error('receipt_changed');
   offer(file,facts);
  }catch(error){if(same(m) && !abort.signal.aborted){emailError=false;notify({error:error.message==='receipt_changed'?
   'Your appointment details changed. Review them and download again.':error.message==='pdf_font_unavailable'?
   'The PDF cannot display these details correctly. Please use the details shown on this page.':'The PDF could not be prepared. Please check your booking and try again.'});}}
  finally{if(pdfWrite===abort){pdfWrite=null;notify({pdfBusy:false});}}
 }
 async function email(address=''){
  if(!allowed() || state.emailBusy)return;const m=mark(),abort=emailWrite=new AbortController();emailError=false;notify({emailBusy:true,error:'',message:''});
  let posted=false,submitted=null,baseline=null,accepted=false;
  try{
   if(!operation){
    const r=await fresh(m,abort.signal);
    if(!allowed() || r.appointment_state!=='confirmed' || !r.booking_revision || !r.email_copy?.can_request)throw Error('copy_unavailable');
    const supplied=address.trim();
    if(!r.email_copy.has_booking_email && (!supplied || supplied.length>254 || !/^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(supplied)))throw Error('invalid_email');
    operation=Object.freeze({request_id:m.credential.request_id,operation_id:cryptoSource.randomUUID(),expected_revision:r.booking_revision,
     ...(!r.email_copy.has_booking_email?{email:supplied}:{})});
    operationBase=Object.freeze({request_id:r.request_id,booking_revision:r.booking_revision,
     has_booking_email:r.email_copy.has_booking_email,copy:copyFacts(r.email_copy)});
   }
   posted=true;submitted=operation;baseline=operationBase;
   const reply=await api('/api/checkout/email-details',{body:submitted,credential:m.credential,signal:abort.signal});
   const savedCopy=checkedEmailCopy(reply.email_copy);
   requireValue(reply.code==='receipt_copy_accepted' && reply.request_id===submitted.request_id && reply.operation_id===submitted.operation_id
    && integer(reply.booking_revision,1) && reply.booking_revision===submitted.expected_revision
    && savedCopy.operation_id===submitted.operation_id && savedCopy.booking_revision===reply.booking_revision
    && savedCopy.has_booking_email===baseline?.has_booking_email);
   if(!same(m))return;accepted=true;operation=null;notify({emailUncertain:false,message:'Your email-copy request is saved. Delivery status is shown below.'});
   // The checked acknowledgement owns this copy projection. Replace only the
   // unchanged pre-send projection; never overwrite a newer booking or copy.
   const current=getReceipt();
   if(current?.request_id===baseline.request_id && current.booking_revision===baseline.booking_revision
    && current.email_copy && copyFacts(current.email_copy)===baseline.copy)onReceipt({...current,email_copy:savedCopy});
   await fresh(m,abort.signal);
  }catch(error){
   if(!same(m) || abort.signal.aborted)return;
   const ambiguous=!error.status || error.code==='request_pending' || error.status>=500 && error.code!=='copy_unavailable';
   // A failed follow-up read cannot undo an acknowledged write or an owned
   // observation of that exact operation. Neither fact proves email delivery.
   if(accepted || ambiguous && submitted && observedOperation?.request_id===submitted.request_id
    && observedOperation.operation_id===submitted.operation_id && observedOperation.expected_revision===submitted.expected_revision){
    operation=null;notify({emailUncertain:false,message:'Your email-copy request is saved. Check booking status for the latest delivery update.'});return;
   }
   const uncertain=posted && operation && ambiguous;
   if(!uncertain)operation=null;
   emailError=true;
   notify({emailUncertain:!!uncertain,error:uncertain?
    'We could not confirm whether your request was saved. Use Retry the same email request; do not create another request.':
    error.message==='invalid_email'?'Please enter a valid email address.':explanation[error.code||error.message]||'The email copy could not be checked. Your appointment remains saved.'});
  }finally{if(emailWrite===abort){emailWrite=null;notify({emailBusy:false});}}
 }
 return Object.freeze({getSnapshot:()=>state,subscribe:listener=>{listeners.add(listener);return()=>listeners.delete(listener);},pdf,email,
  observe:r=>{if(prepared && pdfFacts(r)!==prepared.facts){prepared=null;revoke();}
   if(operation && r.request_id===operation.request_id && r.email_copy?.operation_id===operation.operation_id
    && r.email_copy.booking_revision===operation.expected_revision){
    observedOperation={request_id:operation.request_id,operation_id:operation.operation_id,expected_revision:operation.expected_revision};
    operation=null;const change={emailUncertain:false,message:'Your email-copy request is saved.'};
    if(emailError){emailError=false;change.error='';}notify(change);}},
  canOpen:()=>!!url && allowed() && prepared?.facts===pdfFacts(getReceipt()||{}),
  start:()=>{if(alive)return;alive=true;stopProduct=product.subscribe(()=>{if(!allowed())revoke();});},
  stop:()=>{alive=false;sequence++;pdfWrite?.abort();emailWrite?.abort();stopProduct?.();stopProduct=null;operation=null;operationBase=null;observedOperation=null;emailError=false;prepared=null;revoke();}
 });
}
