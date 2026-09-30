import {useLayoutEffect,useRef} from 'react';
import {useNavigate} from 'react-router-dom';
import {mountHomeMotion} from '../site/home-motion.mjs';
import '../site/home.css';
export default function Home(){
 const root=useRef(null),navigate=useNavigate();
 useLayoutEffect(()=>{document.title="Sarsa Jyotish Sansthan | Madhuri Gupta";return mountHomeMotion(root.current);},[]);
 function actions(event){const el=event.target.closest('[data-contact],#enquire,a');if(!el)return;if(el.matches('[data-contact]')){event.preventDefault();navigate('/contact');}else if(el.id==='enquire'){event.preventDefault();navigate('/booking');}else if(el.getAttribute('href')?.startsWith('/')&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey&&event.button===0){event.preventDefault();navigate(el.getAttribute('href'));}}
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
<p className="eyebrow">{"Personal guidance with Madhuri Gupta"}</p>
<h1>{"A little clarity."}<br />{"A more grounded"}<br />{"way forward."}</h1>
<p className="lead">{"Space for your questions."}<br />{"Perspective for the choices ahead."}</p>
<div className="actions">
<a className="button" href="/booking">{"Book an appointment "}<span aria-hidden="true">{"\u2197"}</span>
</a>
<a className="text-link" href="#madhuri">{"Meet Madhuri"}</a>
</div>
</div>
<div className="hero-bottom">
<span>{"Thoughtful conversation."}<br />{"A personal perspective."}</span>
<a href="#madhuri" className="scroll-cue">{"Take a closer look "}<span aria-hidden="true">{"\u2193"}</span>
</a>
</div>
</div>
</section>{"\n"}<section id="madhuri" className="scroll-scene about" data-chapter="madhuri" data-effect="e">
<div className="scene about-scene">
<div className="about-image">
<img className="approved-portrait" src="/media/madhuri-gupta-portrait.jpeg" alt="Madhuri Gupta" loading="lazy" />
</div>
<div className="about-copy">
<p className="eyebrow">{"Meet Madhuri Gupta"}</p>
<h2>{"The person"}<br />{"behind the practice."}</h2>
<p className="body-large">{"A thoughtful approach."}<br />{"A conversation centred on you."}</p>
<p>{"Madhuri Gupta leads Sarsa Jyotish Sansthan. Here, the focus is on the questions you bring and the perspective you are looking for."}</p>
<div className="signature">{"Madhuri Gupta"}</div>
<a className="text-link" href="/about">{"Read about Madhuri "}<span aria-hidden="true">{"\u2198"}</span>
</a>
</div>
<div className="about-foot">{"An introduction, before an invitation."}</div>
</div>
</section>{"\n"}<section id="consultations" className="consultations section-pad" data-chapter="consultations">
<div className="section-top">
<div>
<p className="eyebrow">{"Explore the possibilities"}</p>
<h2>{"What brings"}<br />{"you here?"}</h2>
</div>
<p>{"Start with the area that speaks to your questions. There is room to explore it thoughtfully."}</p>
</div>
<div className="service-grid">{"\n"}<article className="service">
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
<p>{"Relationship questions, explored through the lens of birth-chart compatibility."}</p>
<a href="/services/kundli-matching" data-service="Kundli Matching">{"Choose this consultation "}<span aria-hidden="true">{"\u2197"}</span>
</a>
</article>{"\n"}<article className="service">
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
<p>{"A birth-chart perspective on the questions and transitions in your life."}</p>
<a href="/services/kundli-prediction">{"Explore Kundli Prediction "}<span aria-hidden="true">{"\u2197"}</span>
</a>
</article>{"\n"}<article className="service">
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
<p>{"Consider your home or workspace through the principles of Vastu."}</p>
<a href="/services/vastu-consultation" data-service="Vastu Consultation">{"Choose this consultation "}<span aria-hidden="true">{"\u2197"}</span>
</a>
</article>{"\n"}<article className="service">
<div className="service-top">
<span className="index">{"04"}</span>
<div className="number-art" aria-hidden="true">{"3"}<span>{"6"}</span>{"9"}</div>
</div>
<h3>{"Numerology"}</h3>
<p>{"Explore the patterns associated with names, dates and numbers."}</p>
<a href="/services/numerology" data-service="Numerology">{"Choose this consultation "}<span aria-hidden="true">{"\u2197"}</span>
</a>
</article>{"\n"}</div>
<p className="service-foot">{"Not sure where to begin? "}<button className="nav-contact" data-contact>{"Ask before booking."}</button>
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
<h2>{"Let\u2019s make"}<br />{"space for it."}</h2>
<p>{"A thoughtful beginning."}<br />{"One step at a time."}</p>
</div>
<div className="disc-orbit" aria-hidden="true">
</div>
</div>
</section>{"\n"}<section id="process" className="process section-pad" data-chapter="process" data-effect="i">
<div className="section-top">
<div>
<p className="eyebrow">{"How it begins"}</p>
<h2>{"A simple way"}<br />{"to take the next step."}</h2>
</div>
<p>{"No need to have every question perfectly formed before you begin."}</p>
</div>
<div className="steps">
<div className="step-line" aria-hidden="true">
</div>
<article>
<span>{"01"}</span>
<h3>{"Choose an area"}</h3>
<p>{"Explore the consultation that feels relevant to you."}</p>
</article>
<article>
<span>{"02"}</span>
<h3>{"Begin your booking"}</h3>
<p>{"Carry your selected consultation into the appointment-booking journey."}</p>
</article>
<article>
<span>{"03"}</span>
<h3>{"Review the next step"}</h3>
<p>{"Check the consultation details before proceeding. Your appointment is confirmed after your payment is verified."}</p>
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
<details>
<summary>{"Where should I start?"}<span aria-hidden="true">{"+"}</span>
</summary>
<p>{"Explore the four consultation areas above. If you are unsure which is relevant to your questions, begin with an enquiry."}</p>
</details>
<details>
<summary>{"What should I prepare?"}<span aria-hidden="true">{"+"}</span>
</summary>
<p>{"Write down the questions you would like to discuss. The details needed for your selected consultation should be confirmed before you book."}</p>
</details>
<details>
<summary>{"How do I arrange a consultation?"}<span aria-hidden="true">{"+"}</span>
</summary>
<p>{"Use Book an appointment below. If you have questions before booking, Contact is available separately."}</p>
</details>
</div>
</section>{"\n"}<section id="enquiry" className="enquiry section-pad" data-chapter="enquiry">
<div className="enquiry-ring" aria-hidden="true">
</div>
<p className="eyebrow">{"Your next chapter"}</p>
<h2>{"Your questions."}<br />{"Your next appointment."}</h2>
<p>{"Take the first step towards a more considered perspective."}</p>
<div id="chosen-service" hidden>
</div>
<button className="button" id="enquire">{"Book an appointment "}<span aria-hidden="true">{"\u2197"}</span>
</button>
</section>{"\n"}</div>;
}
