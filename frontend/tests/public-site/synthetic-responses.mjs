/** TEST ONLY. Same production contracts; no network, credentials or provider SDK. */
import {readFileSync} from 'node:fs';
import {checkedDisplay} from '../../../appointment-system/browser/product-state.mjs';
import {checkedPolicy,checkedAvailability,checkedChallenge,checkedGrant,checkedCheckout} from '../../../appointment-system/browser/booking/protocol.mjs';
import {checkedReceipt as checkedEnquiryReceipt} from '../../../appointment-system/browser/enquiry/protocol.mjs';
export const business=JSON.parse(readFileSync(new URL('../../../appointment-settings/business-settings.json',import.meta.url)));
const epoch='11111111-2222-4333-8444-555555555555',hash='b'.repeat(64);
export function syntheticResponses({otp=false,mode='on',clock=Date.now,verificationFault=null,receiptState='confirmed'}={}){
 const policy=structuredClone(business),saved=new Map(),enquiries=new Map();let challenge=null;policy.booking_verification.email=otp;policy.required_contacts=otp?['email','phone']:['phone'];
 function respond(url,method='GET',body={}){
  const now=clock(),iso=new Date(now).toISOString(),path=url.pathname;
  const result=value=>({status:200,value});
  const failure=(code,status=503)=>({status,value:{code}});
  const read=['/api/service-state','/api/booking-policy','/api/availability','/api/contact/policy'];
  if((read.includes(path)&&method!=='GET')||(!read.includes(path)&&method!=='POST'))return failure('synthetic_method_not_allowed',405);
  if(path==='/api/service-state')return mode==='unknown'?failure('synthetic_unknown'):result(checkedDisplay({enabled:mode==='on',activation_epoch:epoch}));
  // Return the wire shape, not the controller's augmented checkedDisplay fields.
  if(path==='/api/booking-policy')return result(checkedPolicy({policy,quote_version:'a'.repeat(64),booking_verification_policy_hash:hash,server_now:iso,schedule_browsing_open:true,receipt_access:{version:1,key_id:'current'}}));
  if(path==='/api/availability'){
   const service=policy.services.find(s=>s.id===url.searchParams.get('service_id')),day=url.searchParams.get('day'),questions=Number(url.searchParams.get('questions')||1);
   if(!service||!/^\d{4}-\d{2}-\d{2}$/.test(day)||!Number.isInteger(questions)||questions<1||questions>service.pricing.maximum_questions)return failure('synthetic_invalid_request',422);
   const starts=day+'T06:00:00Z',value={date:day,server_now:iso,service:{...service,amount_paise:service.pricing.amount_paise*(service.pricing.kind==='per_question'?questions:1),questions,currency:'INR',timezone:policy.timezone,quote_version:'a'.repeat(64)},slots:Date.parse(starts)>now?[{starts_at:starts,ends_at:new Date(Date.parse(starts)+service.duration_minutes*60000).toISOString()}]:[]};
   return result(checkedAvailability(value,{service:service.id,day,questions,policy:{policy,quote_version:'a'.repeat(64)}}));
  }
  if(path==='/api/checkout-context')return result({ready:true,renewed:false});
  if(/^\/api\/booking-verification\/(start|verify|resend)$/.test(path)){
   if(path.endsWith('/verify')){
    if(!challenge||challenge.email!==body.email||body.challenge_id!==epoch||body.generation!==challenge.generation)return failure('verification_required',409);
    if(now>=challenge.expires||verificationFault==='expired')return failure('verification_expired',422);
    if(body.code!=='123456')return failure('verification_incorrect',422);
    return result(checkedGrant({code:'ok',state:'verified',booking_verification_policy_hash:verificationFault==='mismatched-policy'?'c'.repeat(64):hash,expires_at:new Date(now+300000).toISOString(),verification_grant:'bv1.current.'+'A'.repeat(43)}));
   }
   challenge={email:body.email,generation:path.endsWith('/resend')?Math.min(3,(challenge?.generation||0)+1):1,expires:now+300000};
   return result(checkedChallenge({code:'ok',state:'awaiting_verification',challenge_id:epoch,generation:challenge.generation,booking_verification_policy_hash:hash,expires_at:new Date(challenge.expires).toISOString()}));
  }
  if(path==='/api/contact/policy')return result({version:1,receipt_key_id:'current'});
  if(/^\/api\/contact\/(start|status|verify|resend)$/.test(path)){
   const id=body.request_id;
   if(!/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(id||''))return failure('synthetic_invalid_request',422);
   if(path.endsWith('/start')&&!enquiries.has(id))enquiries.set(id,{code:'ok',request_id:id,state:'awaiting_verification',generation:1,sends_remaining:2,verification_delivery:'queued',code_expires_at:new Date(now+300000).toISOString(),resend_after:new Date(now+60000).toISOString()});
   const receipt=enquiries.get(id);if(!receipt)return failure('synthetic_receipt_not_found',404);
   if(receipt.state==='awaiting_verification'&&now>=Date.parse(receipt.code_expires_at))receipt.state='expired';
   if(path.endsWith('/verify')&&receipt.state!=='received'){
    if(receipt.state!=='awaiting_verification')return failure('verification_expired',422);
    if(body.generation!==receipt.generation)return failure('verification_required',409);
    if(body.code!=='123456')return failure('verification_incorrect',422);
    receipt.state='received';
   }
   if(path.endsWith('/resend')&&receipt.state!=='received'){
    if(now<Date.parse(receipt.resend_after)||receipt.generation>=3)return failure('synthetic_resend_unavailable',409);
    receipt.generation++;receipt.sends_remaining=3-receipt.generation;receipt.state='awaiting_verification';receipt.code_expires_at=new Date(now+300000).toISOString();receipt.resend_after=new Date(now+60000).toISOString();
   }
   return result(checkedEnquiryReceipt({...receipt,server_now:iso},id));
  }
  if(/^\/api\/checkout(?:\/(status|resume|verify-payment|email-details))?$/.test(path)){
   const id=body.request_id;
   if(!/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(id||''))return failure('synthetic_invalid_request',422);
   if(path==='/api/checkout'){
    const service=policy.services.find(s=>s.id===body.service_id);if(!service)return failure('synthetic_invalid_request',422);
    const amount=service.pricing.amount_paise*(service.pricing.kind==='per_question'?body.questions:1);
    saved.set(id,{request_id:id,appointment_state:receiptState,order_state:'ready',payment_state:receiptState==='confirmed'?'captured':'unobserved',service_name:service.name,currency:'INR',timezone:policy.timezone,amount_paise:amount,captured_paise:receiptState==='confirmed'?amount:0,refunded_paise:0,starts_at:body.starts_at,ends_at:new Date(Date.parse(body.starts_at)+service.duration_minutes*60000).toISOString(),server_now:iso,hold_expires_at:new Date(now+900000).toISOString(),next_actions:['check_status'],meeting_mode:'google_meet',meeting_state:'not_created',meet_url:null,booking_revision:1,email_copy:{state:'not_requested',operation_id:null,booking_revision:null,target_hint:null,has_booking_email:!!body.email,can_request:true,remaining_requests:3,blocked_reason:null,next_request_at:null}});
   }
   const receipt=saved.get(id);if(!receipt)return failure('synthetic_receipt_not_found',404);
   receipt.server_now=iso;
   if(path.endsWith('/email-details')){
    if(receipt.appointment_state!=='confirmed'||body.expected_revision!==receipt.booking_revision||!/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(body.operation_id||''))return failure('copy_unavailable',409);
    receipt.email_copy={...receipt.email_copy,state:'provider_accepted',operation_id:body.operation_id,booking_revision:1,target_hint:'r***@example.invalid',can_request:false,blocked_reason:'cooldown',remaining_requests:2,next_request_at:new Date(now+60000).toISOString()};
    checkedCheckout({receipt,checkout:null},id);
    return result({code:'receipt_copy_accepted',request_id:id,operation_id:body.operation_id,booking_revision:1,email_copy:structuredClone(receipt.email_copy)});
   }
   const checked=checkedCheckout({receipt:structuredClone(receipt),checkout:null},id);
   return result(path.endsWith('/status')?checked.receipt:checked);
  }
  return failure('synthetic_unavailable');
 }
 return {policy,respond:(url,method,body)=>{
  const result=respond(url,method,body);
  if(url.pathname==='/api/service-state'&&result.status===200)result.value={enabled:result.value.enabled,activation_epoch:result.value.activation_epoch};
  return result;
 }};
}
