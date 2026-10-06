import {createTransport,RequestError} from '../transport.mjs';

const instant=value=>typeof value==='string' && /(?:Z|[+-]\d\d:\d\d)$/.test(value) && Number.isFinite(Date.parse(value));
export function checkedReceipt(value,id){
 if(value?.code!=='ok' || value.request_id!==id || !['awaiting_verification','expired','locked','received'].includes(value.state)
  || !Number.isInteger(value.generation) || value.generation<1 || value.generation>3 || value.sends_remaining!==3-value.generation
  || !['queued','accepted','delivered','delayed','failed','unavailable'].includes(value.verification_delivery)
  || !['server_now','code_expires_at','resend_after'].every(key=>instant(value[key])))throw new RequestError('invalid_response');
 // Copy only the public contract; never retain accidental response fields.
 return Object.freeze(Object.fromEntries(['code','request_id','state','generation','sends_remaining','verification_delivery',
  'server_now','code_expires_at','resend_after'].map(key=>[key,value[key]])));
}
export function createEnquiryAPI({fetcher=globalThis.fetch}={}){
 const actions=['start','status','verify','resend'];
 const request=createTransport({fetcher,timeout:30000,maximum:8192,
  allowed:path=>path==='/api/contact/policy' || actions.some(action=>path==='/api/contact/'+action)});
 return Object.freeze({
  async policy(signal){const value=await request('/api/contact/policy',{signal});
   if(value.version!==1 || !/^[a-z0-9][a-z0-9_-]{0,31}$/.test(value.receipt_key_id || ''))throw new RequestError('invalid_response');
   return Object.freeze({version:1,receipt_key_id:value.receipt_key_id});},
  async send(action,access,fields={},signal){
   if(!actions.includes(action) || !access?.request_id || !access?.secret)throw new RequestError('invalid_request');
   return checkedReceipt(await request('/api/contact/'+action,{signal,headers:{'X-Enquiry-Receipt':access.secret},
    body:{...fields,request_id:access.request_id}}),access.request_id);
  },
 });
}
