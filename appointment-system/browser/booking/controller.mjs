import {RequestError} from '../transport.mjs';
import {checkedPolicy,checkedAvailability,checkedReceipt,checkedCheckout,checkedChallenge,checkedGrant,localDate,date,rejectedWithoutBooking} from './protocol.mjs';
import {messageFor} from './messages.mjs';

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
  error,busy:false,ack:false,retryAt:0,challenge:null,verification:null,serverOffset:0,
  details:{full_name:'',email:'',phone:'',country:'91',birth_date:'',birth_time:'',birth_place:'',notes:''}});
 const listeners=new Set();let alive=false,lifecycle=0,busy=false,polls=0,stopProduct,timer,closePayment;
 let attempt=null,slotRead=null,policyRead=null,write=null,slotSequence=0,policySequence=0,verificationOperation=null,offset=0;
 const notify=change=>{state=frozen({...state,...change});for(const listener of listeners)listener();};
 const enabled=()=>alive && product.getSnapshot().enabled===true;
 const snapshot=()=>({lifecycle,epoch:product.getSnapshot().activation_epoch});
 const current=mark=>enabled() && mark.lifecycle===lifecycle && mark.epoch===product.getSnapshot().activation_epoch;
 const fail=e=>notify({error:messageFor(e),retryAt:clock()+(e.retryAfter||0)*1000});
 function stopReads(){slotSequence++;policySequence++;slotRead?.abort();policyRead?.abort();}
 async function loadSlots(){
  slotRead?.abort();const sequence=++slotSequence,mark=snapshot(),s=state;
  if(!enabled() || !s.policy || s.credential || !s.service || !s.day || s.phase==='blocked')return;
  const abort=slotRead=new AbortController();notify({slots:[],quote:null,slot:null,slotsStatus:'loading',ack:false});
  try{
   const data=checkedAvailability(await api(`/api/availability?service_id=${encodeURIComponent(s.service)}&day=${s.day}&questions=${s.questions}`,{signal:abort.signal}),
    {service:s.service,day:s.day,questions:s.questions,policy:s.policy});
   if(!current(mark) || abort.signal.aborted || sequence!==slotSequence)return;
   notify({slots:data.slots,quote:data.service,slotsStatus:'ready'});
  }catch(e){if(current(mark) && !abort.signal.aborted && sequence===slotSequence)notify({slots:[],quote:null,slotsStatus:'error',error:messageFor(e)});}
 }
 async function loadPolicy(){
  if(!enabled())return;policyRead?.abort();const sequence=++policySequence,mark=snapshot(),abort=policyRead=new AbortController();
  notify({loadingPolicy:true});
  try{
   const value=checkedPolicy(await api('/api/booking-policy',{signal:abort.signal}));
   if(!current(mark) || abort.signal.aborted || sequence!==policySequence)return;
   offset=Date.parse(value.server_now)-clock();
   const services=value.policy.services.filter(s=>s.enabled),selected=services.find(s=>s.id===state.service)||services[0];
   const changed=state.policy?.quote_version!==value.quote_version;
   notify({policy:value,serverOffset:offset,loadingPolicy:false,service:selected?.id||'',questions:Math.min(state.questions,selected?.pricing.maximum_questions||1),
    day:state.day||localDate(value.server_now,value.policy.timezone),...(changed?{ack:false,slot:null,quote:null}:{}),error:''});
   await loadSlots();
  }catch(e){if(current(mark) && !abort.signal.aborted && sequence===policySequence)notify({loadingPolicy:false,error:messageFor(e)});}
 }
 async function operation(work){
  if(!enabled() || busy || state.phase==='blocked' || state.phase==='payment' || clock()<state.retryAt)return;
  busy=true;const mark=snapshot(),abort=write=new AbortController();notify({busy:true,error:''});
  try{await work(mark,abort.signal);}catch(e){if(current(mark) && !abort.signal.aborted)fail(e);}
  finally{if(mark.lifecycle===lifecycle){busy=false;if(write===abort)write=null;notify({busy:false});}}
 }
 function accept(value,c){const receipt=checkedReceipt(value,c.request_id);notify({receipt,phase:'receipt',error:''});return receipt;}
 const check=()=>operation(async(mark,signal)=>{
  const c=state.credential;if(!c)return;
  const data=await api('/api/checkout/status',{body:{request_id:c.request_id},credential:c,signal});
  if(current(mark))accept(data,c);
 });
 async function context(signal){const value=await api('/api/checkout-context',{body:{},signal});if(value.ready!==true)throw new RequestError('invalid_response');}
 function edit(name,value){
  if(state.credential || busy || state.phase==='blocked')return;
  if(name==='service'){
   if(!state.policy?.policy.services.some(s=>s.id===value && s.enabled))return;
   notify({service:value,questions:1,ack:false,error:''});void loadSlots();
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
  const email=state.details.email.trim();if(state.credential || !state.policy?.policy.booking_verification.email || !email)return;
  await context(signal);if(!current(mark))return;
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
  if(!current(mark))return;
  if(kind==='verify')notify({verification:{...checkedGrant(value),email},ack:false,error:''});
  else notify({challenge:checkedChallenge(value),verification:null,ack:false,error:''});
  verificationOperation=null;
 });
 async function showPayment(result,c,mark){
  checkedCheckout(result,c.request_id);if(!current(mark))return;accept(result.receipt,c);
  if(!result.checkout)return;
  try{await payment.load();}catch{throw new RequestError('payment_unavailable');}if(!current(mark))return;
  notify({phase:'payment'});
  try{closePayment=payment.open(result.checkout,{
   onSuccess:async signed=>{
    // Save signed evidence even if the customer navigated away. The recovery
    // adapter observes OFF before submitting it; no replacement payment is made.
    try{const response=await payment.rememberAndSubmit(c,signed,result.checkout.order_id);
     if(current(mark))accept(response.receipt,c);
    }catch(e){if(current(mark)){notify({phase:'receipt'});fail(e);}}
   },
   onClose:()=>{if(current(mark)){notify({phase:'receipt'});void check();}},
  });}catch{notify({phase:'receipt'});throw new RequestError('payment_unavailable');}
 }
 async function sendOriginal(saved,mark,signal){
  try{const result=await api('/api/checkout',{body:saved.payload,credential:saved.credential,signal});
   if(current(mark))await showPayment(result,saved.credential,mark);
  }catch(e){
   if(!current(mark) || signal.aborted)return;
   if(!rejectedWithoutBooking(e))throw e;
   receipts.clearReceipt(storage(),saved.credential);attempt=null;
   notify({credential:null,receipt:null,phase:'draft',ack:false,retryAt:0,error:messageFor(e),
    ...(e.code==='verification_required'?{verification:null,challenge:null}:{})});
   if(e.code==='quote_changed')await loadPolicy();else await loadSlots();
  }
 }
 const checkout=()=>operation(async(mark,signal)=>{
  const s=state;if(s.credential || !s.policy || !s.quote || !s.slot || !s.ack)return;
  const grant=s.verification;
  if(s.policy.policy.booking_verification.email && (!grant || grant.email!==s.details.email.trim() || Date.parse(grant.expires_at)<=clock()+offset)){
   notify({verification:null,ack:false});throw new RequestError('verification_required');
  }
  await context(signal);if(!current(mark))return;
  const c=receipts.prepareReceipt(storage(),s.policy,cryptoSource);
  const phone=s.details.country==='other'?s.details.phone.trim():'+'+s.details.country+s.details.phone.replace(/[\s()-]/g,'');
  const payload={request_id:c.request_id,normalization_version:2,full_name:s.details.full_name.trim(),email:s.details.email.trim(),
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
  if(current(mark)){await showPayment(result,c,mark);if(result.retry_after)notify({retryAt:clock()+result.retry_after*1000});}
 });
 const restart=()=>operation(async(mark,signal)=>{
  const c=state.credential;if(!c || !state.receipt?.next_actions.includes('choose_new_time'))return;
  const value=await api('/api/checkout/status',{body:{request_id:c.request_id},credential:c,signal});
  if(!current(mark) || !accept(value,c).next_actions.includes('choose_new_time'))return;
  receipts.clearReceipt(storage(),c);attempt=null;polls=0;verificationOperation=null;
  notify({credential:null,receipt:null,phase:'draft',ack:false,challenge:null,verification:null,retryAt:0});await loadPolicy();
 });
 function stop(){
  alive=false;lifecycle++;busy=false;stopReads();write?.abort();write=null;closePayment?.();closePayment=null;
  stopProduct?.();stopProduct=null;clearInterval(timer);timer=null;
 }
 function start(){
  if(alive)return stop;alive=true;lifecycle++;notify({busy:false,phase:state.credential?'checking':blocked?'blocked':'draft'});let prior=product.getSnapshot();
  const change=()=>{
   const next=product.getSnapshot();if(next.enabled===prior.enabled && next.activation_epoch===prior.activation_epoch)return;
   prior=next;stopReads();write?.abort();closePayment?.();closePayment=null;verificationOperation=null;
   notify({policy:null,quote:null,slots:[],slot:null,ack:false,verification:null,challenge:null,
    phase:state.credential?'checking':blocked?'blocked':'draft'});
   if(enabled()){void loadPolicy();void check();}
  };
  stopProduct=product.subscribe(change);if(enabled()){void loadPolicy();if(state.credential)void check();}
  timer=interval(()=>{
   if(!enabled() || documentObject?.visibilityState==='hidden' || !state.credential || busy || polls>=24 || state.phase==='payment')return;
   const r=state.receipt;
   if(r && (['cancelled','payment_review','expired'].includes(r.appointment_state) || (r.appointment_state==='confirmed' && r.meeting_state==='ready')))return;
   if(clock()<state.retryAt)return;polls++;void check();
  },5000);return stop;
 }
 return Object.freeze({getSnapshot:()=>state,subscribe:listener=>{listeners.add(listener);return()=>listeners.delete(listener);},
  start,stop,loadPolicy,loadSlots,edit,details,acknowledge,checkout,retryOriginal,resume,restart,check,
  startVerification:()=>verification('start'),resendVerification:()=>verification('resend'),verifyCode:code=>verification('verify',code),
  report:message=>{if(typeof message==='string' && message.length<=500)notify({error:message});},
  canRetryOriginal:()=>!!attempt && !state.receipt});
}
