import React,{useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {Link,useSearchParams} from 'react-router-dom';
import {useBooking} from '../booking/useBooking.jsx';
import {money,appointmentLabel,timeLabel,dateRange} from '../booking/protocol.mjs';
import {mountBookingLayout} from '../booking/booking-layout.mjs';
import {DateField,BirthTimeField,ReceiptFields} from '../booking/booking-ui.jsx';
import {createVerificationFields} from '../../../appointment-system/browser/booking/verification-fields.mjs';
import '../booking/booking.css';
import ServiceMedia from '../site/ServiceMedia.jsx';
import BookingOrnament from '../site/BookingOrnament.jsx';
import PrashnaArtwork from '../site/PrashnaArtwork.jsx';
import PhoneLink from '../site/PhoneLink.jsx';
const VerificationFields=createVerificationFields(React);
function Symbol({id}) {
  if(id==='prashna-kundali')return <PrashnaArtwork compact/>;
  if(id==='numerology')return <span className="number-symbol" aria-hidden="true">3<em>6</em>9</span>;
  return <svg viewBox="0 0 80 80" aria-hidden="true">{id==='kundli-matching'
    ? <><circle cx="29" cy="40" r="23"/><circle cx="51" cy="40" r="23"/><path d="M40 14v52"/></>
    : id==='vastu-consultation' ? <><rect x="14" y="14" width="52" height="52"/><path d="M40 5v70 M5 40h70 M14 14 66 66 M66 14 14 66"/></>
    : <><path d="M40 5 75 40 40 75 5 40Z M5 40H75 M40 5V75 M22 22 58 58 M58 22 22 58"/><circle cx="40" cy="40" r="16"/></>}</svg>;
}

function ServiceCardCopy({service,index,selected}){
 const perQuestion=service.pricing.kind==='per_question';
 return <><span className="service-top"><span>0{index+1}</span><Symbol id={service.id}/></span><strong>{service.name}</strong><span className={perQuestion?'question-fee':undefined}>{money(service.pricing.amount_paise)}{perQuestion?' per question':''} · {service.duration_minutes} minutes</span>{perQuestion&&<span className="question-limit">Choose 1–{service.pricing.maximum_questions} questions</span>}<span className="card-choice">{selected?'Selected ✓':'Select service →'}</span></>;
}

function Receipt({flow}){
 const {state,check,resume,restart,canRetryOriginal,retryOriginal}=flow;
 const [clock,setClock]=useState(Date.now()),r=state.receipt;
 useEffect(()=>{if(!r||r.appointment_state!=='held')return;const timer=setInterval(()=>setClock(Date.now()),1000);return()=>clearInterval(timer);},[r]);
 const offset=useMemo(()=>r?Date.parse(r.server_now)-Date.now():0,[r]);
 const seconds=r?Math.max(0,Math.ceil((Date.parse(r.hold_expires_at)-clock-offset)/1000)):0;
 const disabled=!flow.available||state.busy||state.phase==='payment'||clock<state.retryAt;
 return <section id="receipt" className="appointment-receipt" tabIndex="-1" aria-label="Your saved appointment">
  {r?<ReceiptFields flow={flow}/>:<p role="status">Checking your saved booking. Please check its status before trying another payment.</p>}
  {state.phase==='payment'&&<p role="status">The secure payment window is open.</p>}
  {r?.appointment_state==='held'&&seconds>0&&<p>Reserved time remaining: {Math.floor(seconds/60)}:{String(seconds%60).padStart(2,'0')}</p>}
  {r?.appointment_state==='payment_review'&&<p>Please contact the practice. Do not pay again while this payment is checked.</p>}
  <div className="result-actions"><button type="button" className="button" disabled={disabled} onClick={check}>{state.busy?'Checking…':'Check booking status'}</button>
   {r?.next_actions.some(a=>['check_payment','resume_payment'].includes(a))&&<button type="button" className="button" disabled={disabled||seconds===0} onClick={resume}>Continue to payment ↗</button>}
   {r?.next_actions.includes('choose_new_time')&&<button type="button" className="button" disabled={disabled} onClick={restart}>Choose a new time</button>}
   {canRetryOriginal&&<button type="button" className="text-button" disabled={disabled} onClick={retryOriginal}>Retry the same saved request</button>}
   <Link className="text-button" to="/contact">Ask for help</Link><Link className="text-button" to="/booking/receipt">View my bookings</Link></div>
 </section>;
}
export default function Booking({headerRef}){
 const [params]=useSearchParams(),requestedService=params.get('service'),flow=useBooking(requestedService||'kundli-prediction'),{state,dispatch}=flow;
 const root=useRef(null),form=useRef(null),layout=useRef(null),arrow=useRef(false),[active,setActive]=useState('service');
 const locked=!!state.credential||state.phase==='blocked'||state.busy||!flow.available;
 const checkingDate=!!state.policy&&flow.viewAvailable&&!flow.available&&!state.credential&&state.phase!=='blocked'&&!state.busy;
 const configured=state.policy?.policy.services.find(s=>s.id===state.service);
 const perQuestion=configured?.pricing.kind==='per_question';
 const amount=state.quote?.amount_paise??(configured?configured.pricing.amount_paise*(perQuestion?state.questions:1):0);
 const prashnaUnavailable=requestedService==='prashna-kundali'&&state.policy&&(state.policyFresh||state.loadingPolicy)&&!state.error&&!state.credential&&!state.receipt&&!state.service&&!state.policy.policy.services.some(s=>s.id==='prashna-kundali'&&s.enabled);
 const selectedName=configured?.name||'Select your service',timezone=state.policy?.policy.timezone||'Asia/Kolkata';
 const range=state.policy?dateRange(state.policy):null,appointment=state.slot?appointmentLabel(state.slot.starts_at,timezone):'Choose a date and time';
 const verificationRequired=state.policy?.policy.booking_verification.email===true;
 useEffect(()=>{window.scrollTo(0,0);},[]);
 useLayoutEffect(()=>{layout.current=mountBookingLayout(root.current,setActive,{headerBar:headerRef?.current});return()=>{layout.current.dispose();layout.current=null;};},[]);
 function go(id){
  if(state.credential)id='review';
  else if(id!=='service'&&!state.service)id='service';
  else if(['details','review'].includes(id)&&!state.slot)id='appointment';
  else if(id==='review'&&!form.current.reportValidity())return;
  layout.current?.go(id);
 }
 const lastReceipt=useRef(false);
 useEffect(()=>{if(state.credential&&!lastReceipt.current){lastReceipt.current=true;layout.current?.go('review');}if(!state.credential)lastReceipt.current=false;},[state.credential]);
 const choose=id=>{if(locked)return;dispatch({type:'edit',name:'service',value:id});layout.current?.go('appointment');};
 function radioKey(event,id){
  if(event.key.startsWith('Arrow'))arrow.current=true;
  if(['Enter',' '].includes(event.key)){event.preventDefault();if(!event.repeat)choose(id);}
 }
 function submit(event){event.preventDefault();if(!state.slot){dispatch({type:'error',message:'Please choose an available time first.'});go('appointment');return;}void flow.start();}
 return <div className="sarsa-booking" ref={root}>
  <div className="booking-opener wrap"><h1>Book your appointment for expert guidance.</h1><p>Apne sawaalon ke saath shuru karein. Choose a service and a time that suits you, then share what you would like to discuss.</p><div className="booking-phone-help"><span>Questions before booking?</span><PhoneLink/></div><Link to="/booking/receipt">Already booked? View my booking ↗</Link><BookingOrnament/></div>
  <nav className="journey-nav wrap" aria-label="Booking steps">{[['service','Service'],['appointment','Date & time'],['details','Your details'],['review','Review']].map(([id,label],i)=><button type="button" key={id} aria-current={active===id?'step':undefined} onClick={()=>go(id)}><span>0{i+1}</span>{label}</button>)}</nav>
  {!flow.available&&<p className="wrap booking-checking" role="status">Checking that booking is available. Your details are kept.</p>}
  {state.error&&<div className="booking-alert wrap" role="alert"><p>{state.error}</p>{!state.policy&&!state.credential&&<button type="button" onClick={flow.loadPolicy} disabled={locked}>Reload service details</button>}<Link to="/contact">Contact the practice</Link></div>}
  {prashnaUnavailable&&<div className="booking-alert wrap" role="status"><p>Prashna Kundali is not available for online booking at the moment. Choose another service or contact us.</p><div className="booking-alert-actions"><button type="button" className="text-button" onClick={flow.loadPolicy} disabled={state.loadingPolicy||state.busy}>{state.loadingPolicy?'Refreshing services…':'Refresh services'}</button><Link to="/contact">Contact the practice</Link></div></div>}
  <form ref={form} onSubmit={submit}><fieldset className="draft-fields" disabled={locked}><legend className="sr-only">Appointment choices</legend>
   <section className="selection story-section wrap section-space" id="service" aria-labelledby="service-title"><h2 id="service-title" tabIndex="-1">Select your service</h2>
    <fieldset className="service-grid"><legend className="sr-only">Select your service</legend>{(state.policy?.policy.services||[]).filter(s=>s.enabled).map((service,i)=><label className={'service-card'+(service.id==='prashna-kundali'?' service-card--prashna':'')} key={service.id}>
     <input type="radio" name="service" value={service.id} checked={state.service===service.id} onChange={()=>dispatch({type:'edit',name:'service',value:service.id})}
      onKeyDown={event=>radioKey(event,service.id)} onKeyUp={event=>{if(event.key.startsWith('Arrow'))arrow.current=false;}}
      onPointerDown={()=>{arrow.current=false;}} onClick={()=>{if(!arrow.current)choose(service.id);}}/>
     <ServiceMedia serviceId={service.id} className="booking-service-photo" hidden/>{service.id==='prashna-kundali'?<div className="booking-service-copy"><ServiceCardCopy service={service} index={i} selected={state.service===service.id}/></div>:<ServiceCardCopy service={service} index={i} selected={state.service===service.id}/>}</label>)}</fieldset>
    <div className="section-action"><span>{selectedName}</span><button type="button" className="button" disabled={!state.service} onClick={()=>go('appointment')}>Choose a date and time →</button></div>
   </section>
   <section className="appointment story-section wrap section-space" id="appointment" aria-labelledby="appointment-title"><h2 id="appointment-title" tabIndex="-1">Select a suitable date and time</h2>
    <div className="appointment-window"><p className="selected-service">{selectedName}</p><p className="field-hint">Times shown in {timezone}</p>
     {perQuestion&&<div className="field"><label htmlFor="question-count">Number of questions</label><select id="question-count" required value={state.questions} aria-describedby="question-count-hint" onChange={e=>dispatch({type:'edit',name:'questions',value:Number(e.target.value)})}>{Array.from({length:configured.pricing.maximum_questions},(_,i)=><option key={i+1} value={i+1}>{i+1} {i===0?'question':'questions'}</option>)}</select><p className="field-hint" id="question-count-hint">{money(configured.pricing.amount_paise)} per question. One {configured.duration_minutes}-minute appointment.</p></div>}
     <DateField label="Appointment date" name="appointmentDate" required value={state.day} min={range?.first_date} max={range?.last_date} disabled={!state.policy||locked} checking={checkingDate} available={flow.viewAvailable} onChange={value=>dispatch({type:'edit',name:'day',value})}/>
     <p id="availability-message" role="status">{state.slotsStatus==='loading'?'Checking available times…':state.slotsStatus==='error'?'Available times could not be checked. Please try again.':state.slotsStatus==='ready'&&!state.slots.length?'No times are available on this date. Please choose another date.':'Select an available start time.'}</p>
     {state.slotsStatus==='error'&&<button type="button" className="text-button" disabled={locked||state.loadingPolicy} onClick={flow.loadPolicy}>Check available times</button>}
     <fieldset className="slot-grid"><legend>Available start times</legend>{state.slots.map(slot=><label className="slot-option" key={slot.starts_at}><input name="time" type="radio" value={slot.starts_at} checked={state.slot?.starts_at===slot.starts_at} disabled={!state.slotsFresh} onChange={()=>dispatch({type:'edit',name:'slot',value:slot})}/>{timeLabel(slot.starts_at,timezone)}</label>)}</fieldset>
     <p className="field-hint">Your time is reserved when you continue to payment.</p><div className="section-action"><button className="text-button" type="button" onClick={()=>go('service')}>← Service</button><button className="button" type="button" disabled={!state.slot||locked||!state.slotsFresh} onClick={()=>go('details')}>Fill your details →</button></div>
    </div>
   </section>
   <section className="details-section story-section wrap section-space" id="details" aria-labelledby="details-title"><h2 id="details-title" tabIndex="-1">Fill your details</h2>
    <div className="details-grid"><div className="context-sheet">
     {[['full_name','Your name','text','name',100],['email','Email address','email','email',254]].map(([name,label,type,auto,max])=>{const required=name==='full_name'||verificationRequired;return <div className="field" key={name}><label htmlFor={name}>{label} <span className={required?'required-label':'optional'}>{required?'*':'(Optional)'}</span></label><input id={name} type={type} autoComplete={auto} required={required} minLength={name==='full_name'?2:undefined} maxLength={max} value={state.details[name]} onChange={e=>dispatch({type:'details',name,value:e.target.value})}/>{name==='email'&&<p className="field-hint">{verificationRequired?'Verify this address below.':'For email updates'}</p>}</div>;})}
     <VerificationFields flow={flow} className="field" buttonClassName="button"/>
     <div className="field"><label htmlFor="phone">Mobile number <span className="required-label">*</span></label><div className="phone-group"><select aria-label="Country calling code" value={state.details.country} onChange={e=>dispatch({type:'details',name:'country',value:e.target.value})}>{[['91','India +91'],['44','UK +44'],['1','US / Canada +1'],['971','UAE +971'],['65','Singapore +65'],['61','Australia +61'],['other','Other country']].map(([value,label])=><option key={value} value={value}>{label}</option>)}</select><input id="phone" type="tel" inputMode="tel" autoComplete="tel-national" required pattern={state.details.country==='other'?'\\+[1-9][0-9\\s\\(\\)\\-]{6,29}':'[0-9\\s\\(\\)\\-]{7,30}'} maxLength="30" value={state.details.phone} onChange={e=>dispatch({type:'details',name:'phone',value:e.target.value})}/></div><p className="field-hint">{state.details.country==='other'?'Include + and your country code.':'Without the country code'}</p></div>
     {(configured?.required_preparation||[]).filter(name=>name!=='notes').map(name=>name==='birth_date'?<DateField key={name} label="Birth date" required available={flow.viewAvailable} value={state.details[name]} onChange={value=>dispatch({type:'details',name,value})}/>:name==='birth_time'?<BirthTimeField key={name} label="Birth time" required available={flow.viewAvailable} value={state.details[name]} onChange={value=>dispatch({type:'details',name,value})}/>:<div className="field" key={name}><label htmlFor={name}>Birth place *</label><input id={name} type="text" required maxLength={200} value={state.details[name]} onChange={e=>dispatch({type:'details',name,value:e.target.value})}/></div>)}
     <div className="field"><label htmlFor="notes">What would you like to discuss? <span className="optional">{configured?.required_preparation.includes('notes')?'*':'(Optional)'}</span></label><textarea id="notes" required={configured?.required_preparation.includes('notes')} rows="4" maxLength="4000" value={state.details.notes} onChange={e=>dispatch({type:'details',name:'notes',value:e.target.value})}/></div>
     <p className="privacy-note">Your details are sent when you continue to payment. <a href="/privacy" target="_blank" rel="noopener noreferrer">Privacy policy</a></p><div className="section-action"><button className="text-button" type="button" onClick={()=>go('appointment')}>← Date & time</button><button className="button" type="button" onClick={()=>go('review')}>Review your booking →</button></div>
    </div><aside className="context-recap" aria-label="Your choices"><dl><div><dt>Service</dt><dd>{selectedName}</dd></div><div><dt>Date & time · {timezone}</dt><dd>{appointment}</dd></div></dl></aside></div>
   </section>
  </fieldset>
  <section className="review-section story-section wrap section-space" id="review" aria-labelledby="review-title"><h2 id="review-title" tabIndex="-1">Review and book</h2>
   {!state.credential?<div className="summary-sheet">{[['Service',selectedName,configured?`${configured.duration_minutes} minutes · ${state.policy.policy.meeting==='google_meet'?'Google Meet':'Practice-arranged meeting'}`:'Details unavailable','service'],['Date & time',appointment,timezone,'appointment'],['Your details',state.details.full_name||'Fill your details', [state.details.email||'No email provided',(state.details.country==='other'?'':'+'+state.details.country+' ')+state.details.phone].join(' · '),'details']].map(([label,value,sub,id])=><div className="summary-row" key={id}><div><span className="summary-label">{label}</span><strong>{value}</strong><span className="summary-sub">{sub}</span></div><button className="edit-button" type="button" disabled={locked} onClick={()=>go(id)}>Edit</button></div>)}
    {perQuestion&&<div className="summary-row"><div><span className="summary-label">Questions</span><strong>{state.questions} × {money(configured.pricing.amount_paise)}</strong><span className="summary-sub">One appointment, including your selected questions</span></div><button className="edit-button" type="button" disabled={locked} onClick={()=>go('appointment')}>Edit</button></div>}
    {state.details.notes&&<div className="summary-row"><div><span className="summary-label">Your question</span><p>{state.details.notes}</p></div></div>}
    <div className="amount-plaque"><span>Total consultation fee</span><strong>{configured?money(amount):'—'}</strong></div>
    <div className="review-bottom"><p>Payment is completed through Razorpay. Your appointment is confirmed after the payment is checked.</p><label className="acknowledgement"><input type="checkbox" checked={state.ack} disabled={locked} onChange={e=>dispatch({type:'ack',value:e.target.checked})}/><span>I’ve checked my appointment and contact details, and read the <a href="/booking-policy" target="_blank" rel="noopener noreferrer">booking policy</a> and <a href="/terms" target="_blank" rel="noopener noreferrer">terms</a>.</span></label><button className="button submit-button" type="submit" disabled={locked||!state.policyFresh||!state.slotsFresh||!state.slot||!state.ack||(verificationRequired&&!state.verification)}>{state.busy?'Preparing your booking…':<><span>Continue to payment</span><span className="payment-amount">{configured?' · '+money(amount):''} ↗</span></>}</button></div>
   </div>:<Receipt flow={flow}/>}
  </section></form>
  <section className="booking-questions wrap section-space" aria-labelledby="booking-questions-title"><h2 id="booking-questions-title">Booking questions</h2>{[
   ['How can I view an existing booking?',<>Use your saved full name and phone number. <Link to="/booking/receipt">View my booking ↗</Link></>],
   ['When is my appointment confirmed?','After payment is checked and the booking is saved. Choosing a time alone does not reserve it.'],
   ['What if the payment window closes?','Check that booking’s status first. A closed window does not tell you whether payment succeeded.'],
   ['How will we meet?',state.policy?.policy.meeting==='google_meet'?'The confirmation page shows your Google Meet link when it is ready. You can also download your appointment details or request an email copy.':'Contact the practice for your meeting arrangements.'],
   ['Can I change my details?','Use Edit before payment begins. For a confirmed appointment, contact the practice for help with a correction.']
  ].map(([question,answer])=><details key={question}><summary>{question}</summary><p>{answer}</p></details>)}</section>
 </div>;
}
