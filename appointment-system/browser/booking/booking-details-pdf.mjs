import {admissionAllowed} from '../product-state.mjs';
import {pdfFacts,prepareVerifiedPDF} from './receipt-pdf.mjs';

/** PDF-only owner. Lookup cannot acquire email, payment or receipt credentials. */
export function createBookingDetailsPDF({controller,product,brand,loadPDF,urls=globalThis.URL}){
 let alive=false,sequence=0,abort=null,url=null,expiry=null,prepared=null,cleanup=null;
 let state=Object.freeze({busy:false,pdfURL:null,filename:null,error:'',message:''});
 const listeners=new Set(),emit=change=>{state=Object.freeze({...state,...change});for(const listener of listeners)listener();};
 const allowed=()=>alive && admissionAllowed(product.getSnapshot()) && !controller.getSnapshot().stale
  && controller.getSnapshot().receipt?.appointment_state==='confirmed';
 const mark=()=>({sequence,id:controller.getSnapshot().receipt?.request_id,epoch:product.getSnapshot().activation_epoch});
 const same=m=>alive && m.sequence===sequence && m.id===controller.getSnapshot().receipt?.request_id
  && m.epoch===product.getSnapshot().activation_epoch;
 function revoke(){if(url)urls.revokeObjectURL(url);url=null;clearTimeout(expiry);expiry=null;emit({pdfURL:null,filename:null});}
 function observe(){
  if(!allowed() || prepared && prepared.facts!==pdfFacts(controller.getSnapshot().receipt||{})){
   sequence++;abort?.abort();abort=null;prepared=null;revoke();emit({busy:false});
  }
 }
 async function pdf(){
  if(!allowed() || state.busy)return;
  const m=mark(),write=abort=new AbortController();emit({busy:true,error:'',message:''});
  try{
   const {file,facts}=await prepareVerifiedPDF({read:()=>controller.refresh({signal:write.signal}),
    current:()=>controller.getSnapshot().receipt,valid:()=>same(m)&&allowed(),prepared,brand,loadPDF});
   if(!same(m)||!allowed())return;
   revoke();prepared={...file,facts};url=urls.createObjectURL(new Blob([file.bytes],{type:'application/pdf'}));
   emit({pdfURL:url,filename:file.filename,message:'Your PDF is ready. Use Download PDF or Open PDF.'});
   expiry=setTimeout(revoke,5000);
  }catch(error){
   if(same(m)){prepared=null;revoke();emit({error:error.message==='receipt_changed'?
    'Your appointment changed. Refresh its details before downloading again.':error.message==='pdf_font_unavailable'?
    'The PDF cannot display these details correctly. Please use the details on this page.':
    'We could not prepare the PDF. Refresh your booking and try again.'});}
  }finally{if(abort===write){abort=null;emit({busy:false});}}
 }
 function start(){
  if(alive)return cleanup;alive=true;
  const stopDetails=controller.subscribe(observe),stopProduct=product.subscribe(observe);
  cleanup=()=>{alive=false;sequence++;abort?.abort();abort=null;prepared=null;stopDetails();stopProduct();revoke();cleanup=null;};return cleanup;
 }
 return Object.freeze({getSnapshot:()=>state,subscribe:listener=>{listeners.add(listener);return()=>listeners.delete(listener);},start,pdf,
  canOpen:()=>allowed() && !!url && prepared?.facts===pdfFacts(controller.getSnapshot().receipt||{})});
}
