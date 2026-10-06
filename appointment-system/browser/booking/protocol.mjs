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
  && instant(data.server_now) && typeof data.schedule_browsing_open==='boolean'
  && integer(p.horizon_days,1,365) && Array.isArray(p.services) && p.services.length>0 && p.services.length<=100
  && unique(p.services.map(service=>service?.id)) && typeof p.booking_verification?.email==='boolean'
  && p.booking_verification.sms===false && ['google_meet','internal'].includes(p.meeting)
  && Array.isArray(p.required_contacts) && unique(p.required_contacts) && p.required_contacts.includes('email')
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
 requireValue(data.meet_url===null || (data.appointment_state==='confirmed' && data.meeting_state==='ready'
  && typeof data.meet_url==='string' && /^https:\/\/meet\.google\.com\/[a-z]{3}-[a-z]{4}-[a-z]{3}$/.test(data.meet_url)));
 return data;
}

export function checkedCheckout(data,id){
 checkedReceipt(data?.receipt,id);
 if(data.checkout!==null && data.checkout!==undefined){
  const c=data.checkout,r=data.receipt;
  requireValue(/^rzp_live_[A-Za-z0-9]+$/.test(c?.key_id) && /^order_[A-Za-z0-9]{1,64}$/.test(c?.order_id)
   && c.amount_paise===r.amount_paise && c.currency==='INR' && r.appointment_state==='held'
   && r.captured_paise===0 && r.refunded_paise===0 && ['unobserved','pending','failed_observed'].includes(r.payment_state)
   && r.order_state==='ready' && r.next_actions.includes('resume_payment')
   && Date.parse(r.hold_expires_at)>Date.parse(r.server_now));
 }
 if(data.retry_after!==undefined)requireValue(integer(data.retry_after,1,3600));
 return data;
}

export function checkedChallenge(data){
 requireValue(data?.code==='ok' && data.state==='awaiting_verification'
  && /^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(data.challenge_id)
  && integer(data.generation,1,3) && instant(data.expires_at));return data;
}
export function checkedGrant(data){
 requireValue(data?.code==='ok' && data.state==='verified' && instant(data.expires_at)
  && /^bv1\.[a-z0-9][a-z0-9_-]{0,31}\.[A-Za-z0-9_-]{43}$/.test(data.verification_grant));return data;
}

export function createBookingAPI(options={}){
 const request=createTransport({...options,allowed:path=>/^\/api\/(booking-policy|availability\?[^#]*|checkout-context|booking-verification\/(start|verify|resend)|checkout(?:\/(status|resume|verify-payment))?)$/.test(path)});
 return (path,{credential,...rest}={})=>request(path,{...rest,headers:credential?{'X-Booking-Receipt':credential.secret}:{}});
}
// This list is restricted to explicit pre-commit rejection codes from checkout.
// Network errors, payment uncertainty and conflicts NEVER discard access.
export const rejectedWithoutBooking=error=>error instanceof RequestError &&
 ((error.status===409 && ['intake_closed','quote_changed','service_unavailable','invalid_time','time_unavailable','request_rejected','verification_required'].includes(error.code))
  || (error.status===422 && error.code==='invalid_request') || (error.status===503 && error.code==='payment_not_configured'));
