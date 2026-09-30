/** Enquiry-only same-origin transport. No sample codes, email cache or booking authority. */
export const STORAGE_KEY='sarsa:004:enquiry-receipt:v1';
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const instant=v=>typeof v==='string' && /(?:Z|[+-]\d\d:\d\d)$/.test(v) && Number.isFinite(Date.parse(v));
export class ContactError extends Error {
 constructor(code='temporarily_unavailable',retryAfter=0){super(code);this.code=code;this.retryAfter=retryAfter;}
}
export function checkedReceipt(value,id){
 if(value?.code!=='ok'||value.request_id!==id||!uuid.test(id)
  || !['awaiting_verification','expired','locked','received'].includes(value.state)
  || !Number.isInteger(value.generation)||value.generation<1||value.generation>3
  || value.sends_remaining!==3-value.generation
  || !['queued','accepted','delivered','delayed','failed','unavailable'].includes(value.verification_delivery)
  || !['server_now','code_expires_at','resend_after'].every(k=>instant(value[k])))throw new ContactError('invalid_response');
 return value;
}
export function browserStorage(){
 try{return globalThis.sessionStorage;}catch{throw new ContactError('storage_unavailable');}
}
function validateAccess(value){
  if(value?.version!==1||!uuid.test(value.request_id)||!/^[-_A-Za-z0-9]{43}$/.test(value.secret)
    ||Object.keys(value).some(k=>!['version','request_id','secret','resend_id','resend_generation'].includes(k))
    ||((value.resend_id===undefined)!==(value.resend_generation===undefined))
    ||(value.resend_id!==undefined&&(!uuid.test(value.resend_id)||!Number.isInteger(value.resend_generation)||value.resend_generation<1||value.resend_generation>2)))throw Error();
}
export function readAccess(storage){
 try {
  const raw=storage.getItem(STORAGE_KEY);if(raw===null)return null;
  const value=JSON.parse(raw);
  validateAccess(value);
  return value;
 }catch{throw new ContactError('receipt_unavailable');}
}
export function saveAccess(storage,value){
 try{
  validateAccess(value);
  storage.setItem(STORAGE_KEY,JSON.stringify(value));
  if(JSON.stringify(readAccess(storage))!==JSON.stringify(value))throw Error();
  return value;
 }catch{throw new ContactError('storage_unavailable');}
}
export function createAccess(storage,source=globalThis.crypto){
 const bytes=source.getRandomValues(new Uint8Array(32));
 return saveAccess(storage,{version:1,request_id:source.randomUUID(),secret:btoa(String.fromCharCode(...bytes)).replaceAll('+','-').replaceAll('/','_').replaceAll('=','')});
}
export function clearAccess(storage,value){
 const saved=readAccess(storage);
 if(saved?.request_id!==value?.request_id)throw new ContactError('receipt_unavailable');
 storage.removeItem(STORAGE_KEY);
 if(storage.getItem(STORAGE_KEY)!==null)throw new ContactError('storage_unavailable');
}
export async function contactApi(action,access,fields={},signal){
 if(!['start','status','resend','verify'].includes(action)||!access?.request_id||!access?.secret)throw new ContactError('invalid_request');
 const controller=new AbortController(),abort=()=>controller.abort();
 if(signal?.aborted)abort();signal?.addEventListener('abort',abort,{once:true});
 const timer=setTimeout(abort,30000);
 try{
  const response=await fetch('/api/contact/'+action,{method:'POST',credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal,
   headers:{'Content-Type':'application/json',Accept:'application/json','X-Enquiry-Receipt':access.secret},
   body:JSON.stringify({...fields,request_id:access.request_id})});
  if(!response.headers.get('content-type')?.includes('application/json')||!response.body)throw new ContactError();
  const reader=response.body.getReader();let size=0,text='';const decoder=new TextDecoder('utf-8',{fatal:true});
  try{while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>8192)throw new ContactError('invalid_response');text+=decoder.decode(value,{stream:true});}text+=decoder.decode();}
  finally{await reader.cancel().catch(()=>{});}
  const data=JSON.parse(text);
  if(!response.ok)throw new ContactError(typeof data?.code==='string'?data.code:'temporarily_unavailable',Math.min(3600,Math.max(0,Number(response.headers.get('retry-after'))||0)));
  return checkedReceipt(data,access.request_id);
 }catch(error){if(error instanceof ContactError)throw error;throw new ContactError();}
 finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
}
const errors={
 contact_unavailable:'The enquiry form is temporarily unavailable. Your details have not been confirmed as received.',
 booking_unavailable:'The enquiry service is temporarily unavailable. Please try again shortly.',
 invalid_request:'Please check your details, including the country code if you entered a phone number.',
 verification_incorrect:'That code did not match. Please check the latest code and try again.',
 verification_changed:'A newer code was requested. Check the enquiry status, then use the latest code.',
 verification_expired:'That code has expired. Request a new one if another attempt is available.',
 verification_limit:'This code or request has reached its limit. Check the enquiry status before continuing.',
 please_wait:'Please wait before trying again. Your enquiry has not been reset.',
 access_unavailable:'We could not open this saved enquiry. Keep this page and check again, or email the practice for help.',
 request_conflict:'This request does not match the saved enquiry. Check its status before continuing.',
 receipt_unavailable:'This browser could not read your saved enquiry. Please email the practice for help.',
 storage_unavailable:'Allow this site to use browser storage before continuing. Only a private enquiry reference is stored.',
 invalid_response:'We could not safely read the response. Check the enquiry status before trying again.',
};
export const messageFor=error=>errors[error?.code]||'The connection was interrupted. Your enquiry may have been saved. Check its status or retry the same request.';
