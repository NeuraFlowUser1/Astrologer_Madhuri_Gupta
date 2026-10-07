import {localDate} from '../display-formatting.mjs';
export {localDate,money,appointmentLabel,timeLabel,dateRange} from '../display-formatting.mjs';
import {createTransport,RequestError} from '../transport.mjs';
export {RequestError as BookingError};
export const requireValue=valid=>{if(!valid)throw new RequestError('invalid_response');};
export const integer=(value,min=0,max=2147483647)=>Number.isSafeInteger(value) && value>=min && value<=max;
const text=(value,max=200)=>typeof value==='string' && value.length>0 && value.length<=max;
export const instant=value=>typeof value==='string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)$/.test(value) && Number.isFinite(Date.parse(value));
export const date=value=>typeof value==='string' && /^\d{4}-\d\d-\d\d$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0,10)===value;
const zone=value=>{try{return text(value,100) && !!new Intl.DateTimeFormat('en',{timeZone:value});}catch{return false;}};
const unique=values=>new Set(values).size===values.length;
const preparation=['birth_date','birth_time','birth_place','notes'];

/** Check only the public values consumed here. SQL remains the quotation/schedule authority. */
export function checkedPolicy(data){
 const p=data?.policy;
 requireValue(p?.version===1 && zone(p.timezone) && /^[a-f0-9]{64}$/.test(data.quote_version)
  && /^[a-f0-9]{64}$/.test(data.booking_verification_policy_hash)
  && instant(data.server_now) && typeof data.schedule_browsing_open==='boolean'
  && integer(p.horizon_days,1,365) && Array.isArray(p.services) && p.services.length>0 && p.services.length<=100
  && unique(p.services.map(service=>service?.id)) && typeof p.booking_verification?.email==='boolean'
  && p.booking_verification.sms===false && ['google_meet','internal'].includes(p.meeting)
  && Array.isArray(p.required_contacts) && unique(p.required_contacts) && p.required_contacts.includes('email')===p.booking_verification.email
  && p.required_contacts.every(value=>['email','phone'].includes(value))
  && data.receipt_access?.version===1 && /^[a-z0-9][a-z0-9_-]{0,31}$/.test(data.receipt_access.key_id));
 for(const s of p.services)requireValue(s && /^[a-z0-9][a-z0-9-]{0,79}$/.test(s.id) && text(s.name,150)
  && typeof s.enabled==='boolean' && integer(s.duration_minutes,5,480) && s.duration_minutes%5===0
  && Array.isArray(s.required_preparation) && unique(s.required_preparation) && s.required_preparation.every(value=>preparation.includes(value))
  && ['fixed','per_question'].includes(s.pricing?.kind) && integer(s.pricing.amount_paise,1)
  && integer(s.pricing.maximum_questions,1,10) && (s.pricing.kind!=='fixed' || s.pricing.maximum_questions===1));
 return data;
}

export function checkedAvailability(data,{service,day,questions,policy}){
 const offered=data?.service,selected=policy.policy.services.find(row=>row.id===service && row.enabled);
 requireValue(!!selected && date(day) && data?.date===day && offered?.id===service
  && offered.quote_version===policy.quote_version && offered.timezone===policy.policy.timezone
  && integer(questions,1,selected.pricing.maximum_questions) && offered.questions===questions
  && offered.currency==='INR' && integer(offered.amount_paise,1) && offered.duration_minutes===selected.duration_minutes
  && instant(data.server_now) && Array.isArray(data.slots) && data.slots.length<=288
  && unique(data.slots.map(slot=>slot?.starts_at)));
 for(const slot of data.slots)requireValue(instant(slot?.starts_at) && instant(slot.ends_at)
  && Date.parse(slot.starts_at)>Date.parse(data.server_now)
  && localDate(slot.starts_at,offered.timezone)===day
  && Date.parse(slot.ends_at)-Date.parse(slot.starts_at)===selected.duration_minutes*60000);
 return data;
}

export function checkedReceipt(data,id){
 requireValue(data?.request_id===id && ['held','expired','confirmed','cancelled','payment_review'].includes(data.appointment_state)
  && ['not_attempted','creating','creation_unknown','ready','failed'].includes(data.order_state)
  && ['unobserved','pending','captured','failed_observed','refunded','partially_refunded','needs_attention'].includes(data.payment_state)
  && text(data.service_name,150) && data.currency==='INR' && zone(data.timezone)
  && integer(data.amount_paise,1) && integer(data.captured_paise) && integer(data.refunded_paise)
  && data.refunded_paise<=data.captured_paise && instant(data.starts_at) && instant(data.ends_at)
  && Date.parse(data.ends_at)>Date.parse(data.starts_at) && instant(data.server_now) && instant(data.hold_expires_at)
  && Array.isArray(data.next_actions) && unique(data.next_actions)
  && data.next_actions.every(action=>['check_status','check_payment','resume_payment','contact_support','choose_new_time'].includes(action))
  && ['not_created','preparing','ready','needs_attention','cancelled'].includes(data.meeting_state));
 if(data.booking_revision!==undefined)requireValue(integer(data.booking_revision,1));
 if(data.meeting_mode!==undefined)requireValue(['google_meet','internal'].includes(data.meeting_mode));
 if(data.email_copy!==undefined && data.email_copy!==null)checkedEmailCopy(data.email_copy);
 if(data.appointment_state==='confirmed' && data.meeting_mode==='google_meet' && data.meeting_state==='ready' && data.meet_url===null)
  return {...data,meeting_state:'needs_attention'};
 if(!(data.meet_url===null || (data.appointment_state==='confirmed' && data.meeting_state==='ready'
  && typeof data.meet_url==='string' && /^https:\/\/meet\.google\.com\/[a-z]{3}-[a-z]{4}-[a-z]{3}$/.test(data.meet_url))))
  return {...data,meet_url:null,meeting_state:'needs_attention'};
 return data;
}

export function checkedEmailCopy(value){
 const keys='blocked_reason,booking_revision,can_request,has_booking_email,next_request_at,operation_id,remaining_requests,state,target_hint';
 const states=['not_requested','pending','processing','provider_accepted','delivered','superseded','needs_attention'];
 const reasons=['delivery_pending','delivery_unknown','cooldown','quota','destination_unavailable','copy_unavailable','booking_unavailable'];
 requireValue(value && Object.keys(value).sort().join(',')===keys && states.includes(value.state)
  && typeof value.has_booking_email==='boolean' && typeof value.can_request==='boolean' && integer(value.remaining_requests,0,3)
  && (value.blocked_reason===null || reasons.includes(value.blocked_reason)) && value.can_request===(value.blocked_reason===null)
  && (value.next_request_at===null || instant(value.next_request_at))
  && (value.target_hint===null || text(value.target_hint,254) && /^[^\s@]\*\*\*@[^\s@]+$/u.test(value.target_hint)));
 if(value.operation_id===null)requireValue(value.booking_revision===null && value.state==='not_requested' && value.target_hint===null);
 else requireValue(/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(value.operation_id)
  && value.operation_id!=='00000000-0000-0000-0000-000000000000' && integer(value.booking_revision,1) && value.state!=='not_requested');
 return value;
}

export function checkedCheckout(data,id){
 const receipt=checkedReceipt(data?.receipt,id);
 if(data.checkout!==null && data.checkout!==undefined){
  const c=data.checkout,r=data.receipt;
  requireValue(/^rzp_live_[A-Za-z0-9]+$/.test(c?.key_id) && /^order_[A-Za-z0-9]{1,64}$/.test(c?.order_id)
   && c.amount_paise===r.amount_paise && c.currency==='INR' && r.appointment_state==='held'
   && r.captured_paise===0 && r.refunded_paise===0 && ['unobserved','pending','failed_observed'].includes(r.payment_state)
   && r.order_state==='ready' && r.next_actions.includes('resume_payment')
   && Date.parse(r.hold_expires_at)>Date.parse(r.server_now));
  if(c.email_optional!==undefined)requireValue(typeof c.email_optional==='boolean' && typeof r.email_copy?.has_booking_email==='boolean'
   && c.email_optional===!r.email_copy.has_booking_email);
 }
 if(data.retry_after!==undefined)requireValue(integer(data.retry_after,1,3600));
 return receipt===data.receipt?data:{...data,receipt};
}

export function checkedChallenge(data){
 requireValue(data?.code==='ok' && data.state==='awaiting_verification'
  && /^[a-f0-9]{64}$/.test(data.booking_verification_policy_hash)
  && /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(data.challenge_id)
  && integer(data.generation,1,3) && instant(data.expires_at));return data;
}
export function checkedGrant(data){
 requireValue(data?.code==='ok' && data.state==='verified' && instant(data.expires_at)
  && /^[a-f0-9]{64}$/.test(data.booking_verification_policy_hash)
  && /^bv1\.[a-z0-9][a-z0-9_-]{0,31}\.[A-Za-z0-9_-]{43}$/.test(data.verification_grant));return data;
}

export function createBookingAPI(options={}){
 const request=createTransport({...options,allowed:path=>/^\/api\/(booking-policy|availability\?[^#]*|checkout-context|booking-verification\/(start|verify|resend)|checkout(?:\/(status|resume|verify-payment|email-details))?)$/.test(path)});
 return (path,{credential,...rest}={})=>request(path,{...rest,headers:credential?{'X-Booking-Receipt':credential.secret}:{}});
}
// This list is restricted to explicit pre-commit rejection codes from checkout.
// Network errors, payment uncertainty and conflicts NEVER discard access.
export const rejectedWithoutBooking=error=>error instanceof RequestError &&
 ((error.status===409 && ['intake_closed','quote_changed','service_unavailable','invalid_time','time_unavailable','request_rejected','verification_required'].includes(error.code))
  || (error.status===422 && ['invalid_request','invalid_details','preparation_required'].includes(error.code)) || (error.status===503 && error.code==='payment_not_configured'));
