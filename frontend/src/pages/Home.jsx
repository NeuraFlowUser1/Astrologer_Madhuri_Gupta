import {BookingAnchor,BookingButton,BookingCopy,BookingOnly} from '../site/BookingProduct.jsx';
import {useLayoutEffect,useRef} from 'react';
import {useNavigate} from 'react-router-dom';
import {mountHomeMotion} from '../site/home-motion.mjs';
import '../site/home.css';
import {mountHomeEnhancements,exclusiveFaq} from '../site/home-enhancements.mjs';
import MarginArt from '../site/MarginArt.jsx';
export default function Home(){
 const root=useRef(null),navigate=useNavigate();
 useLayoutEffect(()=>{document.title="Sarsa Jyotish Sansthan | Madhuri Gupta";const stopMotion=mountHomeMotion(root.current),stopExtras=mountHomeEnhancements(root.current);return()=>{stopExtras();stopMotion();};},[]);
 function actions(event){if(event.defaultPrevented)return;const el=event.target.closest('[data-contact],#enquire,a');if(!el)return;if(el.matches('[data-contact]')){event.preventDefault();navigate('/contact');}else if(el.id==='enquire'){event.preventDefault();navigate('/booking');}else if(el.getAttribute('href')?.startsWith('/')&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey&&event.button===0){event.preventDefault();navigate(el.getAttribute('href'));}}
 return <div className="sarsa-home settled" ref={root} onClick={actions}>{"\n"}<section id="welcome" className="scroll-scene hero" data-chapter="welcome" data-effect="g">
<div className="scene hero-scene">
<div className="hero-photo">
</div>
<div className="hero-soften">
</div>
<div className="hero-foreground left" aria-hidden="true">
</div>
<div className="hero-foreground right" aria-hidden="true">
</div>
<div className="hero-copy">
<p className="eyebrow">{"Jyotish guidance with Madhuri Gupta"}</p>
<h1>{"Questions about life?"}<br />{"Let’s look at your kundli."}</h1>
<p className="lead">Marriage, work, family, or a new beginning. Bring the questions that matter to you.</p>
<div className="actions">
<BookingAnchor className="button" href="/booking">{"Book an appointment "}<span aria-hidden="true">{"\u2197"}</span>
</BookingAnchor>
<BookingAnchor className="text-link" href="#madhuri" data-public-scroll>{"Meet Madhuri"}</BookingAnchor>
</div>
</div>
<div className="hero-bottom">
<span lang="hi">जीवन के सवाल, ज्योतिष की समझ के साथ।</span>
<BookingAnchor href="#madhuri" data-public-scroll className="scroll-cue">{"Take a closer look "}<span aria-hidden="true">{"\u2193"}</span>
</BookingAnchor>
</div>
</div>
</section>{"\n"}<span className="sarsa-scroll-destination" tabIndex="-1" data-scroll-destination="madhuri">Meet Madhuri Gupta</span><section id="madhuri" className="scroll-scene about" data-chapter="madhuri" data-effect="e">
<div className="scene about-scene">
<div className="about-image">
<img className="approved-portrait" src="/media/madhuri-gupta-portrait.jpeg" alt="Madhuri Gupta" loading="lazy" />
</div>
<div className="about-copy">
<p className="eyebrow">{"Meet Madhuri Gupta"}</p>
<h2>Meet Madhuri<br />Gupta.</h2>
<p className="body-large">Speak with Madhuri.<br />Guidance for your questions.</p>
<p>{"Madhuri Gupta leads Sarsa Jyotish Sansthan. Explore the services, get to know her, and bring the questions you would like to discuss."}</p>
<div className="signature">{"Madhuri Gupta"}</div>
<BookingAnchor className="text-link" href="/about">{"Read about Madhuri "}<span aria-hidden="true">{"\u2198"}</span>
</BookingAnchor>
</div>
<div className="about-foot">{"Get to know Madhuri, before you book."}</div>
</div>
<MarginArt targetId="madhuri" canvasSelector=".about-scene" />
</section>{"\n"}<section id="consultations" className="consultations section-pad" data-chapter="consultations">
<div className="section-top">
<div>
<p className="eyebrow">{"Explore the possibilities"}</p>
<h2>{"What brings"}<br />{"you here?"}</h2>
</div>
<p>{"Start with the question you have. Explore the services and find where you’d like to begin."}</p>
</div>
<div className="service-grid">{"\n"}<article className="service">
<div className="service-glow" aria-hidden="true" />
<div className="service-top">
<span className="index">{"01"}</span>
<svg viewBox="0 0 100 100" aria-hidden="true">
<circle cx="36" cy="50" r="24">
</circle>
<circle cx="64" cy="50" r="24">
</circle>
<path d="M50 20v60">
</path>
</svg>
</div>
<h3>{"Kundli Matching"}</h3>
<p>{"Thinking about marriage? Explore two birth charts and your compatibility."}</p>
<BookingAnchor href="/services/kundli-matching" data-service="Kundli Matching">{"Explore the service "}<span aria-hidden="true">{"\u2197"}</span>
</BookingAnchor>
</article>{"\n"}<article className="service">
<div className="service-glow" aria-hidden="true" />
<div className="service-top">
<span className="index">{"02"}</span>
<svg viewBox="0 0 100 100" aria-hidden="true">
<path d="M50 8L92 50 50 92 8 50Z M8 50h84 M50 8v84 M29 29l42 42 M71 29L29 71">
</path>
<circle cx="50" cy="50" r="17">
</circle>
</svg>
</div>
<h3>{"Kundli Prediction"}</h3>
<p>{"Explore your kundli and the questions about work, marriage or family."}</p>
<BookingAnchor href="/services/kundli-prediction">{"Explore the service "}<span aria-hidden="true">{"\u2197"}</span>
</BookingAnchor>
</article>{"\n"}<article className="service">
<div className="service-glow" aria-hidden="true" />
<div className="service-top">
<span className="index">{"03"}</span>
<svg viewBox="0 0 100 100" aria-hidden="true">
<rect x="20" y="20" width="60" height="60">
</rect>
<path d="M50 8v84 M8 50h84 M20 20l60 60 M80 20L20 80">
</path>
<circle cx="50" cy="50" r="13">
</circle>
</svg>
</div>
<h3>{"Vastu Consultation"}</h3>
<p>{"Explore your home or workplace through the principles of Vastu."}</p>
<BookingAnchor href="/services/vastu-consultation" data-service="Vastu Consultation">{"Explore the service "}<span aria-hidden="true">{"\u2197"}</span>
</BookingAnchor>
</article>{"\n"}<article className="service">
<div className="service-glow" aria-hidden="true" />
<div className="service-top">
<span className="index">{"04"}</span>
<div className="number-art" aria-hidden="true">{"3"}<span>{"6"}</span>{"9"}</div>
</div>
<h3>{"Numerology"}</h3>
<p>{"Explore what names, dates and numbers mean in Numerology."}</p>
<BookingAnchor href="/services/numerology" data-service="Numerology">{"Explore the service "}<span aria-hidden="true">{"\u2197"}</span>
</BookingAnchor>
</article>{"\n"}</div>
<p className="service-foot">{"Not sure where to begin? "}<button className="nav-contact" data-contact><BookingCopy off="Ask the practice.">{"Ask before booking."}</BookingCopy></button>
</p>
</section>{"\n"}<section id="conversation" className="scroll-scene connection" data-chapter="conversation" data-effect="hc">
<div className="scene connection-scene">
<div className="forest-reveal">
</div>
<div className="connection-start">
<p className="eyebrow">{"From a question"}</p>
<h2>{"Something"}<br />{"on your mind?"}</h2>
</div>
<div className="shared-disc" aria-hidden="true">
<i>
</i>
<b>{"\u2726"}</b>
</div>
<div className="connection-end">
<p className="eyebrow">{"To a conversation"}</p>
<h2>Bring your<br />questions.</h2>
<p lang="hi">एक कदम,<br />समझ की ओर।</p>
</div>
<div className="disc-orbit" aria-hidden="true">
</div>
</div>
</section>{"\n"}<section id="process" className="process section-pad" data-chapter="process" data-effect="i">
<div className="section-top">
<div>
<p className="eyebrow"><BookingCopy off="How to begin">How to book</BookingCopy></p>
<h2><BookingCopy off={<>Start with<br />your question.</>}>Three steps to<br />your appointment.</BookingCopy></h2>
</div>
<p>{"You don’t need to have every question worked out before you begin."}</p>
</div>
<div className="steps">
<div className="step-line" aria-hidden="true">
</div>
<article>
<span>{"01"}</span>
<h3><BookingCopy off="Explore a service">Choose a service</BookingCopy></h3>
<p><BookingCopy off="Read about the service that fits your question.">Explore a service and check its fee and timings.</BookingCopy></p>
</article>
<article>
<span>{"02"}</span>
<h3><BookingCopy off="Send a question">{"Make your payment"}</BookingCopy></h3>
<p><BookingCopy off="Tell the practice what you would like guidance with.">{"Choose a suitable appointment time, add your details and make payment."}</BookingCopy></p>
</article>
<article>
<span>{"03"}</span>
<h3><BookingCopy off="Wait for a reply">Check your booking</BookingCopy></h3>
<p><BookingCopy off="The practice can respond to your enquiry. Sending a message does not reserve an appointment.">{"Check the consultation details before proceeding. Your appointment is confirmed after your payment is verified."}</BookingCopy></p>
</article>
</div>
</section>{"\n\n"}<section id="questions" className="questions section-pad" data-chapter="questions" data-effect="b">
<div className="faq-title">
<div className="paper-door door-left" aria-hidden="true">
</div>
<div className="paper-door door-right" aria-hidden="true">
</div>
<div>
<p className="eyebrow">{"Before you begin"}</p>
<h2>{"A few questions,"}<br />{"answered simply."}</h2>
</div>
</div>
<div className="faq-list">
<details name="sarsa-home-faq" onToggle={exclusiveFaq}><summary>Which service should I choose?<span aria-hidden="true">+</span></summary><p>Kundli Matching is for marriage compatibility. Kundli Prediction explores birth-chart questions. Vastu concerns your home or workspace, and Numerology concerns names, dates and numbers. <BookingAnchor href="/services">Read about the services</BookingAnchor>, or <BookingAnchor href="/contact">ask the practice</BookingAnchor> if you are unsure.</p></details>
<details name="sarsa-home-faq" onToggle={exclusiveFaq}><summary>What should I keep ready?<span aria-hidden="true">+</span></summary><p>Read your selected service’s preparation notes. For birth-chart questions, keep the birth date, time and place you know nearby, along with the questions you want to discuss.</p></details>
<details name="sarsa-home-faq" onToggle={exclusiveFaq}><summary>What if I do not know my exact birth time?<span aria-hidden="true">+</span></summary><p>Tell the practice before booking. Ask what information would be useful for your appointment.</p></details>
<BookingOnly><details name="sarsa-home-faq" onToggle={exclusiveFaq}><summary>How do online appointments work?<span aria-hidden="true">+</span></summary><p>Online consultations use Google Meet. Your saved booking shows its status and the available appointment details.</p></details>
<details name="sarsa-home-faq" onToggle={exclusiveFaq}><summary>When is my appointment confirmed?<span aria-hidden="true">+</span></summary><p>After payment is verified and the appointment is secured. Selecting a time or sending an enquiry alone does not confirm an appointment.</p></details>
<details name="sarsa-home-faq" onToggle={exclusiveFaq}><summary>Do I need to enter an email address?<span aria-hidden="true">+</span></summary><p>The booking form will tell you whether an email check is needed. Your mobile number is required. Contact enquiries use a separate email check.</p></details>
<details name="sarsa-home-faq" onToggle={exclusiveFaq}><summary>Can I change or cancel my appointment?<span aria-hidden="true">+</span></summary><p>Read the current <BookingAnchor href="/booking-policy">Booking Policy</BookingAnchor> for the rules. For help, <BookingAnchor href="/booking-help">restore your booking access</BookingAnchor> or <BookingAnchor href="/contact">contact the practice</BookingAnchor>.</p></details></BookingOnly>
<details name="sarsa-home-faq" onToggle={exclusiveFaq}><summary>Can I ask something before booking?<span aria-hidden="true">+</span></summary><p>Yes. <BookingAnchor href="/contact">Send a question to the practice</BookingAnchor>. A short message is enough to begin; sending it does not reserve an appointment.</p></details>
</div>
</section>{"\n"}<section id="enquiry" className="enquiry section-pad" data-chapter="enquiry">
<div className="enquiry-ring" aria-hidden="true">
</div>
<p className="eyebrow">{"Your next chapter"}</p>
<h2>{"Your questions."}<br /><BookingCopy off="A place to begin.">{"Your next appointment."}</BookingCopy></h2>
<p>{"Bring the questions you would like to understand."}</p>
<div id="chosen-service" hidden>
</div>
<BookingButton className="button" id="enquire">{"Book an appointment "}<span aria-hidden="true">{"\u2197"}</span>
</BookingButton>
</section>{"\n"}</div>;
}
