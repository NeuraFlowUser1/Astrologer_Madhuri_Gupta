import {RequestError} from '../transport.mjs';
import {checkedPolicy,checkedAvailability,checkedReceipt,checkedCheckout,checkedChallenge,checkedGrant,localDate,date,rejectedWithoutBooking} from './protocol.mjs';
import {messageFor} from './messages.mjs';
import {admissionAllowed} from '../product-state.mjs';

const frozen=value=>{if(value && typeof value==='object' && !Object.isFrozen(value)){Object.values(value).forEach(frozen);Object.freeze(value);}return value;};
const editable=new Set(['full_name','email','phone','country','birth_date','birth_time','birth_place','notes']);

/** Shared coordinator, independent of either site's layout and React version. */
export function createBookingController({api,receipts,storage,payment,product,initialService='',
 cryptoSource=globalThis.crypto,clock=Date.now,documentObject=globalThis.document,
 interval=globalThis.setInterval,clearInterval=globalThis.clearInterval}){
 let credential=null,error='',blocked=false;
 try{credential=receipts.readReceipt(storage());}catch(e){error=messageFor(e);blocked=true;}
 let state=frozen({service:initialService,day:'',questions:1,slot:null,quote:null,policy:null,loadingPolicy:true,
  slots:[],slotsStatus:'idle',credential,receipt:null,phase:blocked?'blocked':credential?'checking':'draft',
  error,busy:false,ack:false,retryAt:0,challenge:null,verification:null,serverOffset:0,policyFresh:false,slotsFresh:false,
  details:{full_name:'',email:'',phone:'',country:'91',birth_date:'',birth_time:'',birth_place:'',notes:''}});
 const listeners=new Set();let alive=false,lifecycle=0,busy=false,polls=0,stopProduct,timer,closePayment;
 let attempt=null,slotRead=null,policyRead=null,write=null,slotSequence=0,policySequence=0,verificationOperation=null,offset=0,pendingPayment=null;
 const notify=change=>{state=frozen({...state,...change});for(const listener of listeners)listener();};
 const enabled=()=>alive && admissionAllowed(product.getSnapshot());
 const snapshot=()=>({lifecycle,epoch:product.getSnapshot().activation_epoch});
 const sameLife=mark=>alive && mark.lifecycle===lifecycle && mark.epoch===product.getSnapshot().activation_epoch
  && !(product.getSnapshot().verified===true && product.getSnapshot().enabled===false);
 const current=mark=>enabled() && sameLife(mark);
 const fail=e=>notify({error:messageFor(e),retryAt:clock()+(e.retryAfter||0)*1000});
 function stopReads(){slotSequence++;policySequence++;slotRead?.abort();policyRead?.abort();}
 async function loadSlots({preserve=false}={}){
  slotRead?.abort();const sequence=++slotSequence,mark=snapshot(),s=state;
  if(!enabled() || !s.policy || s.credential || !s.service || !s.day || s.phase==='blocked')return;
  const abort=slotRead=new AbortController();notify({slotsFresh:false,slotsStatus:'loading',
   ...(!preserve?{slots:[],quote:null,slot:null,ack:false}:{})});
  try{
   const data=checkedAvailability(await api(`/api/availability?service_id=${encodeURIComponent(s.service)}&day=${s.day}&questions=${s.questions}`,{signal:abort.signal}),
    {service:s.service,day:s.day,questions:s.questions,policy:s.policy});
   if(!current(mark) || abort.signal.aborted || sequence!==slotSequence)return;
   const retained=preserve && state.slot && data.slots.find(slot=>slot.starts_at===state.slot.starts_at && slot.ends_at===state.slot.ends_at);
   const unchanged=retained && ['amount_paise','duration_minutes','questions','timezone','quote_version'].every(key=>data.service[key]===s.quote?.[key]);
   notify({slots:data.slots,quote:data.service,slot:retained||null,slotsFresh:true,slotsStatus:'ready',ack:!!unchanged && state.ack});
  }catch(e){if(sameLife(mark) && !abort.signal.aborted && sequence===slotSequence)notify({slotsFresh:false,slotsStatus:'error',error:messageFor(e)});}
 }
 async function loadPolicy(){
  if(!enabled())return;policyRead?.abort();const sequence=++policySequence,mark=snapshot(),abort=policyRead=new AbortController();
  notify({loadingPolicy:true,policyFresh:false});
  try{
   const value=checkedPolicy(await api('/api/booking-policy',{signal:abort.signal}));
   if(!current(mark) || abort.signal.aborted || sequence!==policySequence)return;
   offset=Date.parse(value.server_now)-clock();
   const services=value.policy.services.filter(s=>s.enabled),selected=services.find(s=>s.id===state.service)
    || (!state.policy && !state.service?services[0]:null);
   const changed=state.policy?.quote_version!==value.quote_version;
   const bound=state.challenge?.booking_verification_policy_hash||state.verification?.booking_verification_policy_hash;
   const verificationChanged=!!bound && bound!==value.booking_verification_policy_hash;
   notify({policy:value,serverOffset:offset,loadingPolicy:false,policyFresh:true,service:selected?.id||'',questions:Math.min(state.questions,selected?.pricing.maximum_questions||1),
    day:state.day||localDate(value.server_now,value.policy.timezone),...(changed?{ack:false}:{}),
    ...(verificationChanged?{challenge:null,verification:null,ack:false}:{}),
    ...(!selected?{slot:null,quote:null,slots:[],slotsFresh:false,ack:false}:{}),error:''});
   await loadSlots({preserve:true});
  }catch(e){if(sameLife(mark) && !abort.signal.aborted && sequence===policySequence)notify({loadingPolicy:false,policyFresh:false,error:messageFor(e)});}
 }
 async function operation(work){
  if(!enabled() || busy || state.phase==='blocked' || state.phase==='payment' || clock()<state.retryAt)return;
  busy=true;const mark=snapshot(),abort=write=new AbortController();notify({busy:true,error:''});
  try{await work(mark,abort.signal);}catch(e){if(sameLife(mark) && !abort.signal.aborted)fail(e);}
  finally{if(mark.lifecycle===lifecycle && write===abort){busy=false;write=null;notify({busy:false});}}
 }
 function accept(value,c){
  const receipt=checkedReceipt(value,c.request_id),prior=state.receipt;
  if(prior?.booking_revision && receipt.booking_revision && (receipt.booking_revision<prior.booking_revision ||
   receipt.booking_revision===prior.booking_revision && Date.parse(receipt.server_now)<Date.parse(prior.server_now)))return prior;
  notify({receipt,phase:'receipt',error:''});return receipt;
 }
 const check=()=>{polls=0;return checkOnce();};
 const checkOnce=()=>operation(async(mark,signal)=>{
  const c=state.credential;if(!c)return;
  const data=await api('/api/checkout/status',{body:{request_id:c.request_id},credential:c,signal});
  if(sameLife(mark))accept(data,c);
 });
 async function context(signal){
  const value=await api('/api/checkout-context',{body:{},signal});if(value.ready!==true || value.renewed!==undefined && typeof value.renewed!=='boolean')throw new RequestError('invalid_response');
  if(value.renewed===true){verificationOperation=null;notify({challenge:null,verification:null,ack:false});}return value.renewed===true;
 }
 function edit(name,value){
  if(state.credential || busy || state.phase==='blocked')return;
  if(name==='service'){
   if(!state.policy?.policy.services.some(s=>s.id===value && s.enabled))return;
   if(state.service===value)return;notify({service:value,questions:1,ack:false,error:''});void loadSlots();
  }else if(name==='day' || name==='questions'){
   if(name==='day' && !date(value))return;
   if(name==='questions' && (!Number.isInteger(value) || value<1
     || value>(state.policy?.policy.services.find(s=>s.id===state.service)?.pricing.maximum_questions||1)))return;
   notify({[name]:value,ack:false,error:''});void loadSlots();
  }else if(name==='slot'){
   const slot=state.slots.find(s=>s.starts_at===value?.starts_at && s.ends_at===value?.ends_at);
   if(slot)notify({slot,ack:false,error:''});
  }
 }
 function details(name,value){
  if(!editable.has(name) || typeof value!=='string' || state.credential || busy || state.phase==='blocked')return;
  const changed=name==='email' && value.trim()!==state.details.email.trim();
  if(changed)verificationOperation=null;
  notify({details:{...state.details,[name]:value},ack:false,...(changed?{challenge:null,verification:null}:{})});
 }
 function acknowledge(value){if(!busy && !state.credential)notify({ack:value===true});}
 const verification=(kind,code)=>operation(async(mark,signal)=>{
  const email=state.details.email.trim();if(state.credential || !state.policyFresh || !state.policy?.policy.booking_verification.email || !email)return;
  const renewed=await context(signal);if(!current(mark))return;
  if(renewed && kind!=='start')throw new RequestError('verification_required');
  let payload={email};
  if(kind!=='start'){
   if(!state.challenge)return;
   payload={...payload,challenge_id:state.challenge.challenge_id,generation:state.challenge.generation};
  }
  if(kind==='verify'){
   if(typeof code!=='string' || !/^[0-9]{6}$/.test(code))throw new RequestError('invalid_request');payload.code=code;
  }
  const fingerprint=JSON.stringify({kind,...payload});
  if(verificationOperation?.fingerprint!==fingerprint)verificationOperation={fingerprint,payload:{operation_id:cryptoSource.randomUUID(),...payload}};
  const value=await api('/api/booking-verification/'+kind,{body:verificationOperation.payload,signal});
  if(!sameLife(mark) || state.details.email.trim()!==email)return;
  if(kind==='verify')notify({verification:{...checkedGrant(value),email},ack:false,error:''});
  else notify({challenge:checkedChallenge(value),verification:null,ack:false,error:''});
  verificationOperation=null;
  if(value.booking_verification_policy_hash!==state.policy.booking_verification_policy_hash){notify({policyFresh:false});if(enabled())void loadPolicy();}
 });
 async function showPayment(result,c,mark){
  checkedCheckout(result,c.request_id);if(!sameLife(mark))return;accept(result.receipt,c);
  if(!result.checkout)return;
  if(!current(mark)){pendingPayment={result,c,mark};return;}
  try{await payment.load();}catch{throw new RequestError('payment_unavailable');}
  if(!current(mark)){if(sameLife(mark))pendingPayment={result,c,mark};return;}
  pendingPayment=null;
  notify({phase:'payment'});
  try{closePayment=payment.open(result.checkout,{
   onSuccess:async signed=>{
    closePayment=null;
    if(sameLife(mark))notify({phase:'receipt'});
    // Save signed evidence even if the customer navigated away. The recovery
    // adapter observes OFF before submitting it; no replacement payment is made.
    try{const response=await payment.rememberAndSubmit(c,signed,result.checkout.order_id);
     if(sameLife(mark))accept(response.receipt,c);
    }catch(e){if(sameLife(mark)){notify({phase:'receipt'});fail(e);}}
   },
   onClose:()=>{closePayment=null;if(sameLife(mark)){notify({phase:'receipt'});if(enabled())void check();}},
  });}catch{notify({phase:'receipt'});throw new RequestError('payment_unavailable');}
 }
 async function sendOriginal(saved,mark,signal){
  try{const result=await api('/api/checkout',{body:saved.payload,credential:saved.credential,signal});
   if(sameLife(mark))await showPayment(result,saved.credential,mark);
  }catch(e){
   if(!sameLife(mark) || signal.aborted)return;
   if(!rejectedWithoutBooking(e))throw e;
   receipts.clearReceipt(storage(),saved.credential);attempt=null;
   notify({credential:null,receipt:null,phase:'draft',ack:false,retryAt:0,error:messageFor(e),
    ...(e.code==='verification_required'?{verification:null,challenge:null}:{})});
   if(e.code==='quote_changed')await loadPolicy();else await loadSlots();
  }
 }
 const checkout=()=>operation(async(mark,signal)=>{
  const s=state;if(s.credential || !s.policyFresh || !s.slotsFresh || !s.policy || !s.quote || !s.slot || !s.ack)return;
  const grant=s.verification;
  if(s.policy.policy.booking_verification.email && (!grant || grant.email!==s.details.email.trim() || Date.parse(grant.expires_at)<=clock()+offset)){
   notify({verification:null,ack:false});throw new RequestError('verification_required');
  }
  const renewed=await context(signal);if(!current(mark))return;
  if(renewed && s.policy.policy.booking_verification.email)throw new RequestError('verification_required');
  const c=receipts.prepareReceipt(storage(),s.policy,cryptoSource);
  const phone=s.details.country==='other'?s.details.phone.trim():'+'+s.details.country+s.details.phone.replace(/[\s()-]/g,'');
  const payload={request_id:c.request_id,normalization_version:3,full_name:s.details.full_name.trim(),email:s.details.email.trim()||null,
   phone:s.details.phone.trim()?phone:'',service_id:s.service,quote_version:s.policy.quote_version,starts_at:s.slot.starts_at,
   questions:s.questions,notes:s.details.notes.trim(),birth_date:s.details.birth_date||null,birth_time:s.details.birth_time.trim(),birth_place:s.details.birth_place.trim(),
   ...(s.policy.policy.booking_verification.email?{verification_grant:grant.verification_grant}:{})};
  attempt=frozen({credential:c,payload});notify({credential:c,phase:'checking',error:''});
  await sendOriginal(attempt,mark,signal);
 });
 const retryOriginal=()=>operation(async(mark,signal)=>{if(attempt && !state.receipt)await sendOriginal(attempt,mark,signal);});
 const resume=()=>operation(async(mark,signal)=>{
  const c=state.credential;if(!c || !state.receipt?.next_actions.some(a=>['check_payment','resume_payment'].includes(a)))return;
  const result=await api('/api/checkout/resume',{body:{request_id:c.request_id},credential:c,signal});
  if(sameLife(mark)){await showPayment(result,c,mark);if(result.retry_after)notify({retryAt:clock()+result.retry_after*1000});}
 });
 const restart=()=>operation(async(mark,signal)=>{
  const c=state.credential;if(!c || !state.receipt?.next_actions.includes('choose_new_time'))return;
  const value=await api('/api/checkout/status',{body:{request_id:c.request_id},credential:c,signal});
  if(!current(mark) || !accept(value,c).next_actions.includes('choose_new_time'))return;
  receipts.clearReceipt(storage(),c);attempt=null;polls=0;verificationOperation=null;
  notify({credential:null,receipt:null,phase:'draft',ack:false,challenge:null,verification:null,retryAt:0});await loadPolicy();
 });
 function stop(){
  alive=false;lifecycle++;busy=false;stopReads();write?.abort();write=null;closePayment?.();closePayment=null;pendingPayment=null;
  stopProduct?.();stopProduct=null;clearInterval(timer);timer=null;
 }
 function start(){
  if(alive)return stop;alive=true;lifecycle++;notify({busy:false,phase:state.credential?'checking':blocked?'blocked':'draft'});let prior=product.getSnapshot();
  const change=()=>{
   const next=product.getSnapshot(),previous=prior;prior=next;
   const reset=next.activation_epoch!==previous.activation_epoch || next.verified===true && next.enabled===false;
   if(reset){
    stopReads();write?.abort();write=null;busy=false;closePayment?.();closePayment=null;pendingPayment=null;verificationOperation=null;
    notify({policy:null,policyFresh:false,slotsFresh:false,quote:null,slots:[],slot:null,ack:false,verification:null,challenge:null,busy:false,
     phase:state.credential?'checking':blocked?'blocked':'draft'});
   }
   if(!enabled())return;
   const foreground=next.foreground_revision!==revalidatedForeground;
   if(reset || !state.policy || foreground || previous.checking===true && !state.policyFresh)void loadPolicy();
   // A foreground revision was announced before its display check completed.
   if(foreground)revalidatedForeground=next.foreground_revision;
   if(pendingPayment){const waiting=pendingPayment;pendingPayment=null;void showPayment(waiting.result,waiting.c,waiting.mark).catch(fail);}
   if(state.credential && !busy && !closePayment && (reset || previous.verified!==true))void check();
  };
  let revalidatedForeground=prior.foreground_revision;
  stopProduct=product.subscribe(change);if(enabled()){void loadPolicy();if(state.credential)void check();}
  timer=interval(()=>{
   if(!enabled() || documentObject?.visibilityState==='hidden' || !state.credential || busy || polls>=24 || state.phase==='payment')return;
   const r=state.receipt;
   if(r && (['cancelled','payment_review','expired'].includes(r.appointment_state) ||
    (r.appointment_state==='confirmed' && (r.meeting_state==='ready' || r.meeting_mode==='internal') &&
     !['pending','processing'].includes(r.email_copy?.state))))return;
   if(clock()<state.retryAt)return;polls++;void checkOnce();
  },5000);return stop;
 }
 return Object.freeze({getSnapshot:()=>state,subscribe:listener=>{listeners.add(listener);return()=>listeners.delete(listener);},
  start,stop,loadPolicy,loadSlots,edit,details,acknowledge,checkout,retryOriginal,resume,restart,check,
  updateReceipt:value=>{if(alive && state.credential){const prior=state.receipt,result=accept(value,state.credential);
   if(prior?.email_copy?.operation_id!==result.email_copy?.operation_id)polls=0;return result;}},
  startVerification:()=>verification('start'),resendVerification:()=>verification('resend'),verifyCode:code=>verification('verify',code),
  report:message=>{if(typeof message==='string' && message.length<=500)notify({error:message});},
  canRetryOriginal:()=>!!attempt && !state.receipt});
}
