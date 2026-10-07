import {appointmentLabel,timeLabel,money} from './protocol.mjs';
import {admissionAllowed} from '../product-state.mjs';
import {createReceiptActions} from './receipt-actions.mjs';

const delivery={not_requested:'No email address was provided',not_queued:'Not yet queued',pending:'Preparing',processing:'Preparing',
 provider_accepted:'Accepted for sending',accepted:'Accepted for sending',delivered:'Delivered',failed:'Delivery needs attention',
 attention:'Delivery needs attention',needs_attention:'Delivery needs attention',bounced:'Could not be delivered',complained:'Delivery needs attention',
 suppressed:'Delivery needs attention',retry_wait:'Waiting to retry',delivery_unknown:'Delivery is being checked'};
const copies={not_requested:'No copy requested',pending:'Preparing your copy',processing:'Preparing your copy',
 provider_accepted:'Accepted for sending',delivered:'Delivered',superseded:'The appointment changed before this copy was sent',needs_attention:'The copy needs attention'};
const blocked={delivery_pending:'Your earlier copy is still being prepared.',delivery_unknown:'Your earlier copy’s delivery is being checked.',
 cooldown:'Please wait before requesting another copy.',quota:'The daily limit of three copies has been reached.',
 destination_unavailable:'The recorded address cannot receive email. Please contact the practice.',copy_unavailable:'Email copies are temporarily unavailable.',
 booking_unavailable:'New copies are available only for confirmed appointments.'};

/** Identical facts and actions in confirmation and standalone receipts. Theme stays local. */
export function createReceiptFields(React,{browser,brand,loadPDF,theme=''}){
 const {createElement:h,useRef,useEffect,useState,useSyncExternalStore,useId}=React;
 return function ReceiptFields({flow,showTitle=true}){
  const latest=useRef(flow);latest.current=flow;
  const instance=useRef(null);if(!instance.current)instance.current=createReceiptActions({api:browser.api,product:browser.product,
   getCredential:()=>latest.current.state.credential,getReceipt:()=>latest.current.state.receipt,
   onReceipt:value=>latest.current.updateReceipt(value),brand,loadPDF});
  const actions=instance.current,state=useSyncExternalStore(actions.subscribe,actions.getSnapshot,actions.getSnapshot);
  const display=useSyncExternalStore(browser.product.subscribe,browser.product.getSnapshot,browser.product.getSnapshot);
  const enabled=admissionAllowed(display),r=flow.state.receipt;
  const [email,setEmail]=useState(''),[entry,setEntry]=useState(false),emailInput=useRef(null),id=useId(),titleId=useId();
  useEffect(()=>{actions.start();return actions.stop;},[actions]);
  useEffect(()=>{if(r)actions.observe(r);},[actions,r]);
  useEffect(()=>{if(entry)emailInput.current?.focus();},[entry]);
  if(!r)return null;
  const confirmed=r.appointment_state==='confirmed',copy=r.email_copy,contract=!!r.booking_revision && !!r.meeting_mode && !!copy;
  const titles={confirmed:'Your appointment is confirmed',held:'Your time is reserved',expired:'This reservation has ended',
   cancelled:'This appointment was cancelled',payment_review:'Your payment is being checked'};
  const fact=(label,value)=>h('div',{key:label},h('dt',null,label),h('dd',null,value));
  const send=()=>{
   if(!copy.has_booking_email && !state.emailUncertain && !entry){setEntry(true);return;}
   if(!copy.has_booking_email && !state.emailUncertain && !emailInput.current?.reportValidity())return;
   void actions.email(email);
  };
  const linkProps={href:state.pdfURL,download:state.filename,onClick:event=>{if(!actions.canOpen())event.preventDefault();}};
  const meeting=r.meeting_mode==='internal'?'Contact the practice for the meeting arrangements.':
   r.meet_url?h('a',{href:r.meet_url,target:'_blank',rel:'noopener noreferrer',className:'abs-meet-link'},'Open Google Meet ↗'):
   r.meeting_state==='needs_attention'?'Your meeting link needs attention. Please contact the practice.':
   confirmed?'Your meeting link is being prepared.':'Meeting details are available after confirmation.';
  return h('section',{className:'abs-receipt '+theme,...(showTitle?{'aria-labelledby':titleId}:{'aria-label':'Saved appointment details'})},
   showTitle?h('h2',{id:titleId},titles[r.appointment_state]):null,
   h('dl',{className:'abs-receipt-facts'},fact('Service',r.service_name),fact('Appointment',appointmentLabel(r.starts_at,r.timezone)+' – '+timeLabel(r.ends_at,r.timezone)),
    fact('Time zone',r.timezone),fact('Duration',Math.round((Date.parse(r.ends_at)-Date.parse(r.starts_at))/60000)+' minutes'),
    fact('Agreed fee',money(r.amount_paise)),fact('Payment recorded',money(r.captured_paise)),fact('Refund recorded',money(r.refunded_paise)),
    fact('Meeting',meeting),fact('Confirmation email',delivery[r.acknowledgement_state]||'Status being checked'),
    fact('Meeting-details email',delivery[r.meeting_email_state]||'Status being checked'),fact('Booking reference',r.request_id)),
   confirmed && contract?h('div',{className:'abs-receipt-actions'},
    h('button',{type:'button',disabled:!enabled||state.pdfBusy,onClick:()=>void actions.pdf()},state.pdfBusy?'Preparing PDF…':state.pdfURL?'Refresh PDF':'Download appointment PDF'),
    state.pdfURL?h(React.Fragment,null,h('a',{...linkProps,className:'abs-download'},'Download PDF'),
     h('a',{...linkProps,download:undefined,target:'_blank',rel:'noopener noreferrer',className:'abs-download'},'Open PDF')):null,
    h('button',{type:'button',disabled:!enabled||state.emailBusy||!state.emailUncertain&&!copy.can_request,onClick:send},
     state.emailBusy?'Saving request…':state.emailUncertain?'Retry the same email request':entry&&!copy.has_booking_email?'Send email copy':'Email appointment details'),
    entry&&!copy.has_booking_email?h('div',{className:'abs-copy-address'},h('label',{htmlFor:id},'Email address for this copy',
     h('input',{id,ref:emailInput,type:'email',value:email,required:true,maxLength:254,autoComplete:'email',disabled:state.emailBusy||state.emailUncertain,
      onChange:event=>setEmail(event.target.value)})),h('p',null,'This sends an email copy. It does not change your appointment.')):null,
    h('p',{className:'abs-copy-status'},copies[copy.state]||'Status being checked',copy.target_hint?' · '+copy.target_hint:''),
    copy.blocked_reason?h('p',{className:'abs-copy-hint'},blocked[copy.blocked_reason]):null,
    r.meeting_mode==='google_meet'&&!r.meet_url&&copy.state==='pending'?h('p',null,'We’ll email the details when your meeting link is ready.'):null,
    state.message?h('p',{role:'status'},state.message):null,state.error?h('p',{role:'alert',className:'abs-action-error'},state.error):null):null,
   confirmed&&!contract?h('p',null,'Check the latest booking status to see available document and email options.'):null);
 };
}
