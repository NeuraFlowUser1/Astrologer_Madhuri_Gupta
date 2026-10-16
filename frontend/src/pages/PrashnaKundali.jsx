import {useId,useLayoutEffect,useRef,useState} from 'react';
import {BookingAnchor,BookingCopy,BookingLink,BookingOnly} from '../site/BookingProduct.jsx';
import catalogue from '../site/catalogue.json';
import {questionTopics,preparation} from '../site/prashna-content.mjs';
import PrashnaArtwork from '../site/PrashnaArtwork.jsx';
import ServiceMedia from '../site/ServiceMedia.jsx';
import {mountPrashnaMotion} from '../site/prashna-motion.mjs';
import '../site/prashna.css';

export default function PrashnaKundali(){
 const root=useRef(null),tabs=useRef([]),panel=useRef(null),transition=useRef(null),id=useId();
 const [topic,setTopic]=useState(0),service=catalogue.services.find(s=>s.id==='prashna-kundali');
 const fee=new Intl.NumberFormat('en-IN',{style:'currency',currency:service.currency,maximumFractionDigits:0}),unit=fee.format(service.amount_paise/100),limit=service.maximum_questions,duration=service.duration_minutes;
 useLayoutEffect(()=>{const stop=mountPrashnaMotion(root.current),reduced=matchMedia('(prefers-reduced-motion: reduce)');const settle=()=>{if(reduced.matches){transition.current?.cancel();transition.current=null;}};reduced.addEventListener('change',settle);return()=>{reduced.removeEventListener('change',settle);transition.current?.cancel();stop();};},[]);
 function selectTopic(next,pointer=false){
  root.current.dispatchEvent(new Event('prashna:topic'));if(next===topic)return;
  const opacity=transition.current?.playState==='running'?getComputedStyle(panel.current).opacity:.55;
  transition.current?.cancel();transition.current=null;
  setTopic(next);
  if(pointer&&typeof panel.current.animate==='function'&&!matchMedia('(prefers-reduced-motion: reduce)').matches)transition.current=panel.current.animate([{opacity},{opacity:1}],{duration:180,easing:getComputedStyle(root.current).getPropertyValue('--ease-action').trim()||'cubic-bezier(.23,1,.32,1)'});
 }
 function tabKeys(event,index){
  let next;if(event.key==='ArrowRight')next=(index+1)%questionTopics.length;else if(event.key==='ArrowLeft')next=(index+questionTopics.length-1)%questionTopics.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=questionTopics.length-1;else return;
  event.preventDefault();selectTopic(next);tabs.current[next].focus();
 }
 function exclusiveFaq(event){if(event.currentTarget.open)root.current.querySelectorAll('details[name="prashna-faq"]').forEach(other=>{if(other!==event.currentTarget)other.open=false;});}
 const book=<BookingLink to="/booking?service=prashna-kundali" bookingMode="hide" className="prashna-button">Book Prashna Kundali <span aria-hidden="true">↗</span></BookingLink>;
 const contact=<BookingLink to="/contact" className="prashna-text-link">Contact the practice <span aria-hidden="true">→</span></BookingLink>;
 const faqs=[
  ['Do I need my birth date or birth time?','They are not required to book Prashna Kundali. Bring the specific question you want to discuss.'],
  ['Can I ask more than one question?',<BookingCopy off="Contact the practice with the questions you would like to discuss.">Yes. Choose between 1 and {limit} questions while booking. The fee is {unit} for each question.</BookingCopy>],
  ['Does a higher question count give me more time?',<BookingCopy off="Contact the practice to discuss your questions and the next step.">No. Each booking is one {duration}-minute appointment, including the questions you select.</BookingCopy>],
  ['Do I need to send my question separately?',<>No separate form is needed. <BookingCopy off="Bring your question when you contact the practice.">You can use the optional notes while booking, or bring your question to the appointment.</BookingCopy></>],
  ['What if I am unsure which service to book?',<>Read about <BookingLink to="/services/kundli-prediction">Kundli Prediction</BookingLink>, or <BookingLink to="/contact">contact the practice</BookingLink> with your question before booking.</>],
 ];
 return <div className="sarsa-prashna" ref={root}>
  <section className="prashna-hero" data-prashna-scene="hero"><div className="prashna-wrap hero-grid"><div className="hero-copy">
   <p className="eyebrow">A specific question</p><h1>Prashna Kundali</h1><p className="support-heading">Discuss a specific question with Madhuri.</p>
   <p>Prashna Kundali uses a chart based on the time a question is asked. Madhuri looks at the chart and discusses that question with you. You can book without your birth details.</p>
   <p className="hindi">Apna sawaal saath laayein.</p>
   <p className="fee-line"><BookingCopy off="Contact the practice to talk about your question."><strong>{unit} per question</strong> · One {duration}-minute {service.meeting_platform} appointment</BookingCopy></p>
   <div className="prashna-actions">{book}<BookingAnchor href="#prashna-examples" data-public-scroll className="prashna-text-link">See what you can ask <span aria-hidden="true">↓</span></BookingAnchor></div>
  </div><div className="prashna-art-stage"><PrashnaArtwork/></div></div></section>
  <section className="prashna-chapter difference" data-prashna-scene="difference"><div className="prashna-wrap"><div className="chapter-intro"><p className="eyebrow">Choosing a service</p><h2>How Prashna Kundali is different</h2></div><div className="difference-grid">
   <div className="supporting-art" data-prashna-part="image"><ServiceMedia serviceId={service.id} index={1} detail/></div>
   <div><div className="comparison-item" data-prashna-part="comparison"><h3>Prashna Kundali</h3><p>Starts with <strong>a specific question</strong> and the time it is asked. You do not need birth details to book.</p></div><div className="comparison-item" data-prashna-part="comparison"><h3><BookingLink to="/services/kundli-prediction">Kundli Prediction ↗</BookingLink></h3><p>Explores <strong>your birth chart</strong> and a wider phase of life, using your birth details.</p></div><p className="difference-note">If you are unsure which one fits your question, <BookingLink to="/contact">contact the practice</BookingLink> before booking.</p></div>
  </div></div></section>
  <section className="prashna-chapter examples" id="prashna-examples" data-prashna-scene="examples"><div className="prashna-wrap"><div className="chapter-intro"><p className="eyebrow">Your question</p><h2>Questions you can bring</h2><p>You may have a question about work, family or a choice you are considering. Here are some ways to put it into words.</p></div>
   <div className="question-tabs" role="tablist" aria-label="Question topics">{questionTopics.map((entry,i)=><button type="button" key={entry.label} role="tab" id={`${id}-topic-${i}`} aria-selected={topic===i} tabIndex={topic===i?0:-1} aria-controls={`${id}-examples`} ref={el=>{tabs.current[i]=el;}} onClick={event=>selectTopic(i,event.detail>0)} onKeyDown={event=>tabKeys(event,i)}>{entry.label}</button>)}</div>
   <div className="example-panel" id={`${id}-examples`} role="tabpanel" aria-labelledby={`${id}-topic-${topic}`} tabIndex="0" ref={panel}>{questionTopics[topic].questions.map(question=><article className="example-sheet" key={question}><p>{question}</p></article>)}</div><p className="example-note">These are examples of questions you can discuss. Bring the question that matters to you.</p>
  </div></section>
  <section className="prashna-chapter preparation" data-prashna-scene="preparation"><div className="prashna-wrap"><div className="chapter-intro"><p className="eyebrow">Getting ready</p><h2>Before your appointment</h2></div><div className="prep-grid">{preparation.map((step,i)=><article className="prep-step" key={step.title}><span className="prep-number">0{i+1}</span><div className="prep-copy"><h3><BookingCopy off={step.offTitle||step.title}>{step.title}</BookingCopy></h3><p><BookingCopy off={step.offBody||step.body}>{i===1?<>Select 1–{limit} questions while booking. You will see the full fee before payment.</>:step.body}</BookingCopy></p></div></article>)}</div></div></section>
  <section className="prashna-chapter fees" data-prashna-scene="fee"><div className="prashna-wrap"><BookingOnly><div className="chapter-intro"><p className="eyebrow">Fee and appointment</p><h2><span className="fee-emphasis">{unit}</span> per question</h2><p>The fee depends on the number of questions you choose. The appointment is still one {duration}-minute conversation. Choose your question count in Booking, then check the total before payment.</p></div><div className="amount-grid">{[1,3,limit].map(count=><div className="amount-example" key={count}><span>{count} {count===1?'question':'questions'}</span><strong>{fee.format(count*service.amount_paise/100)}</strong></div>)}</div><p data-prashna-part="appointment">Choose 1–{limit} questions · One {duration}-minute appointment · {service.meeting_platform}</p>{book}</BookingOnly>
   <BookingCopy off={<><div className="chapter-intro"><p className="eyebrow">Your next step</p><h2>Talk to the practice about your question.</h2><p>A short message is enough to begin.</p></div>{contact}</>}>{null}</BookingCopy>
  </div></section>
  <section className="prashna-chapter prashna-faq" data-prashna-scene="questions"><div className="prashna-wrap"><p className="eyebrow">Before you book</p><h2>Questions before you book</h2><div className="faqs">{faqs.map(([question,answer])=><details name="prashna-faq" key={question} onToggle={exclusiveFaq}><summary>{question}</summary><p>{answer}</p></details>)}</div><div className="prashna-actions">{book}{contact}</div></div></section>
 </div>;
}
