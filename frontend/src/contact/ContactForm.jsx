import {useEffect,useRef,useState} from 'react';
import {useEnquiry} from './useEnquiry.jsx';
import {useBookingProduct} from '../site/BookingProduct.jsx';

export default function ContactForm({topicRequest}){
 const {enabled}=useBookingProduct();
 const flow=useEnquiry(),result=useRef(null),codeInput=useRef(null);
 const [draft,setDraft]=useState({name:'',email:'',phone:'',subject:'Before booking',reference:'',message:''});
 const [code,setCode]=useState(''),[localError,setLocalError]=useState('');
 useEffect(()=>{if(topicRequest&&!flow.started)setDraft(old=>({...old,subject:topicRequest.topic}));},[topicRequest]);
 useEffect(()=>{if(flow.receipt?.state==='received'){setCode('');result.current?.focus();}},[flow.receipt?.state]);
 useEffect(()=>{setCode('');},[flow.receipt?.generation]);
 const change=e=>setDraft(old=>({...old,[e.target.name]:e.target.value}));
 const disabled=flow.busy||flow.waiting>0;
 async function submit(event){
  event.preventDefault();setLocalError('');
  if(flow.started){
   if(!/^[0-9]{6}$/.test(code)){setLocalError('Enter the six-digit code from your latest email.');codeInput.current?.focus();return;}
   await flow.verify(code);setCode('');return;
  }
  const message=(['Existing booking','Payment question'].includes(draft.subject)&&draft.reference.trim()?`Booking reference: ${draft.reference.trim()}\n\n`:'')+draft.message.trim();
  if(message.length>4000){setLocalError('Please shorten your question slightly to leave room for the booking reference.');return;}
  if(draft.name.trim().length<2||draft.message.trim().length<5){setLocalError('Please enter your name and a question of at least five characters.');return;}
  await flow.start({name:draft.name.trim(),email:draft.email.trim(),phone:draft.phone.trim(),subject:draft.subject,message,source:'contact'});
 }
 const delivery=flow.receipt?.verification_delivery;
 const received=flow.receipt?.state==='received';
 return <>
  {!received&&<form id="enquiry" onSubmit={submit} aria-busy={flow.busy}>
   <fieldset disabled={disabled||flow.blocked}>
    {!flow.started?<div id="writing"><div className="fields">
     <div className="field"><label htmlFor="visitor-name">Your name <small>Required</small></label><input id="visitor-name" name="name" autoComplete="name" maxLength={100} minLength={2} required value={draft.name} onChange={change}/></div>
     <div className="field"><label htmlFor="visitor-email">Email address <small>Required</small></label><input id="visitor-email" name="email" type="email" autoComplete="email" maxLength={254} required value={draft.email} onChange={change}/></div>
     <div className="field"><label htmlFor="visitor-phone">Phone number <small>Optional</small></label><input id="visitor-phone" name="phone" type="tel" autoComplete="tel" maxLength={32} value={draft.phone} onChange={change} aria-describedby="phone-hint"/><small id="phone-hint">Include your country code, for example +91.</small></div>
     <div className="field"><label htmlFor="topic">What is it about?</label><select id="topic" name="subject" value={draft.subject} onChange={change}>{['Before booking','General enquiry','Existing booking','Payment question'].map(v=><option key={v} value={v}>{!enabled && v==='Before booking'?'Choosing guidance':v}</option>)}</select></div>
     {['Existing booking','Payment question'].includes(draft.subject)&&<div className="field full"><label htmlFor="reference">Booking reference <small>Optional</small></label><input id="reference" name="reference" maxLength={80} value={draft.reference} onChange={change}/><small>Check your original booking status before paying again. Never include card or bank details.</small></div>}
     <div className="field full"><label htmlFor="message">Your question <small>Required</small></label><textarea id="message" name="message" rows={5} maxLength={4000} minLength={5} required value={draft.message} onChange={change} aria-describedby="message-hint"/><small id="message-hint">A little context is helpful. Save birth details for your consultation booking.</small></div>
    </div><p className="form-help">Next, verify your email to submit your enquiry.</p><button className="button submit" type="submit">Continue to email verification <span aria-hidden="true">↗</span></button></div>:
    <div id="verification"><p className="eyebrow">02 / VERIFY YOUR EMAIL</p><h3>A small check.<br/><em>A clear connection.</em></h3>
     {flow.receipt?<>
      <p>{draft.email?`Use the latest six-digit code for ${draft.email}.`:'Use the latest six-digit code for your saved enquiry.'}</p>
      <p className="form-help">{['failed','unavailable'].includes(delivery)?'We could not send this code. You can request another when the resend option is available.':delivery==='queued'?'Your verification email is being prepared.':'Check your inbox and spam folder. Delivery can take a moment.'}</p>
      {(flow.expired||flow.receipt.state==='expired'||flow.receipt.state==='locked')?<p className="form-help">This code is no longer usable. {flow.receipt.sends_remaining>0?'Request a new code below.':'This request has reached its limit. Please email the practice for help.'}</p>:
       <><div className="field"><label htmlFor="code">Six-digit code</label><input ref={codeInput} id="code" name="code" type="text" inputMode="numeric" autoComplete="one-time-code" maxLength={6} pattern="[0-9]{6}" required value={code} onChange={e=>setCode(e.target.value)} aria-describedby="form-status"/></div><button className="button submit" type="submit">Verify &amp; send enquiry <span aria-hidden="true">↗</span></button></>}
      <div className="verification-links"><button type="button" className="text-button" onClick={flow.check}>Check enquiry status</button><button type="button" className="text-button" onClick={flow.resend} disabled={disabled||flow.resendWait>0||flow.receipt.sends_remaining===0}>{flow.resendWait>0?`Resend in ${flow.resendWait}s`:'Request a new code'}</button></div>
     </>:<><p>We’re checking your saved request. Your enquiry is not yet confirmed as received.</p><button type="button" className="text-button" onClick={flow.check}>Check enquiry status</button></>}
     {flow.retry&&<button type="button" className="button" onClick={flow.retryRequest}>{flow.retry==='status'?'Check saved enquiry':'Retry the same request'}</button>}
    </div>}
   </fieldset>
  </form>}
  {received&&<div id="outcome" ref={result} tabIndex={-1}><div className="state-seal" aria-hidden="true">✓</div><p className="eyebrow">ENQUIRY RECEIVED</p><h3>Your note.<br/><em>Safely received.</em></h3><p>Your enquiry has been saved for the practice. This does not reserve an appointment.</p><p className="enquiry-reference">Reference: <span>{flow.receipt.request_id}</span></p>{enabled&&<a className="button" href="/booking">Choose a consultation ↗</a>}<button type="button" className="text-button" disabled={flow.busy||flow.blocked} onClick={async()=>{if(await flow.restart())setDraft({name:'',email:'',phone:'',subject:'Before booking',reference:'',message:''});}}>Write another enquiry</button></div>}
  <p id="form-status" role="status" aria-live="polite">{localError||flow.error||(flow.busy?'Checking your enquiry…':'')}</p>
  {(flow.error||flow.blocked||flow.receipt?.state==='locked'||flow.receipt?.state==='expired')&&<p className="form-help">Need help? <a href="mailto:sarsajyotish@gmail.com">Email the practice</a>. Do not send payment or bank details.</p>}
 </>;
}
