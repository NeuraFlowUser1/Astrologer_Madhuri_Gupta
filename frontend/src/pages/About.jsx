import {BookingAnchor,BookingButton,BookingCopy,BookingLink} from '../site/BookingProduct.jsx';
import {useLayoutEffect,useRef} from 'react';
import {useNavigate} from 'react-router-dom';
import {mountAboutMotion} from '../site/about-motion.mjs';
import '../site/about.css';
import catalogue from '../site/catalogue.json';
import MarginArt from '../site/MarginArt.jsx';
import {mountAboutLayout} from '../site/about-layout.mjs';
const serviceOrder=['kundli-prediction','kundli-matching','vastu-consultation','numerology'];
export default function About(){
 const root=useRef(null),navigate=useNavigate();
 useLayoutEffect(()=>{document.title='About Madhuri Gupta | Sarsa Jyotish Sansthan';const stopMotion=mountAboutMotion(root.current),stopLayout=mountAboutLayout(root.current);return()=>{stopLayout();stopMotion();};},[]);
 function actions(event){const button=event.target.closest('[data-book],#contact');if(button)navigate(button.id==='contact'?'/contact':'/booking');}
 return <div className="sarsa-about settled" ref={root} onClick={actions}>
<section className="opening" id="opening">
<div className="scene" id="scene">
<div className="material">
</div>
<div className="portrait-plane" id="portrait-plane">
<div className="portrait-light" aria-hidden="true">
</div>
<img id="portrait" src="/media/madhuri-gupta-portrait.jpeg" alt="Madhuri Gupta, lead of Sarsa Jyotish Sansthan" />
<div className="portrait-wash">
</div>
</div>
<div className="curtain curtain-left" id="curtain-left">
<span className="eyebrow">{"BEHIND THE PRACTICE"}</span>
<h1>{"Every story"}<br />{"begins with"}<br />
<em>{"a person."}</em>
</h1>
<p>{"Meet Madhuri Gupta."}</p>
<span className="scroll-note">{"MEET THE PERSON BEHIND THE PRACTICE"}</span>
</div>
<div className="curtain curtain-right" id="curtain-right">
</div>
<div className="carry" id="carry" aria-hidden="true">
<i>
</i>
<span>{"\u2726"}</span>
</div>
<div className="moment" id="moment">
<span>{"THE PERSON BEHIND SARSA"}</span>
<strong>{"Madhuri Gupta"}</strong>
</div>
<div className="introduction" id="introduction">
<p className="eyebrow" data-enter="0">{"MEET MADHURI GUPTA"}</p>
<h2 data-enter="1">{"A personal practice."}<br />
<em>{"A thoughtful"}<br />{"conversation."}</em>
</h2>
<div className="rule" id="intro-rule">
</div>
<p data-enter="2">{"The person behind Sarsa Jyotish Sansthan."}<br />{"A place to begin with your questions."}</p>
<BookingButton className="button" data-book="General consultation" data-enter="3">{"Book an appointment "}<span>{"\u2197"}</span>
</BookingButton>
<BookingAnchor href="#approach" data-public-scroll className="text-link" data-enter="3">{"Discover her approach \u2193"}</BookingAnchor>
</div>
</div>
</section>{"\n"}<section className="welcome wrap" id="welcome">
<span className="eyebrow">{"A PERSONAL INTRODUCTION"}</span>
<h2>{"Meet the person."}<br />
<em>{"Find your starting point."}</em>
</h2>
<p>{"Madhuri Gupta leads Sarsa Jyotish Sansthan, bringing a personal identity to its astrology, numerology and Vastu consultations."}</p>
</section>{"\n"}<span className="sarsa-scroll-destination" tabIndex="-1" data-scroll-destination="approach">Madhuri’s approach</span><section className="approach" id="approach">
<div className="wrap">
<div className="section-title">
<div>
<p className="eyebrow">{"01 / THE APPROACH"}</p>
<h2>Start with what<br />matters <em>to you.</em>
</h2>
</div>
<div className="approach-intro"><p>Tell us what you would like to understand.</p><BookingLink className="approach-action" to="/services">Explore the services ↗</BookingLink></div>
</div>
<div className="approach-scene" id="approach-scene">
<div className="connecting-rule" aria-hidden="true">
</div>
<article>
<div className="moving-paper" aria-hidden="true">
</div>
<span className="chapter">{"I."}</span>
<h3>{"Begin with listening."}</h3>
<p>{"Tell the practice what brought you here and what you would like to understand."}</p>
</article>
<article>
<div className="moving-paper" aria-hidden="true">
</div>
<span className="chapter">{"II."}</span>
<h3>{"Explore with curiosity."}</h3>
<p>{"Ask for a simple explanation when a word is unfamiliar, and bring the questions you have."}</p>
</article>
<article>
<div className="moving-paper" aria-hidden="true">
</div>
<span className="chapter">{"III."}</span>
<h3>{"Keep the person in view."}</h3>
<p>{"Bring the discussion back to your life and the questions that matter to you."}</p>
</article>
</div>
</div>
</section>{"\n"}<section className="personal wrap" id="personal">
<div className="portrait-detail">
<img src="/media/madhuri-gupta-portrait.jpeg" alt="Approved studio portrait of Madhuri Gupta" loading="lazy" />
<span>{"\u092e\u093e\u0927\u0941\u0930\u0940 \u0917\u0941\u092a\u094d\u0924\u093e "}<small>{"MADHURI GUPTA"}</small>
</span>
</div>
<div className="personal-copy">
<p className="eyebrow">{"02 / THE PERSON & THE PRACTICE"}</p>
<h2>{"A name."}<br />{"A face."}<br /><em>{"A personal connection."}</em>
</h2>
<p>{"Behind Sarsa Jyotish Sansthan is Madhuri Gupta. The practice offers Kundli Prediction, Kundli Matching, Numerology and Vastu Consultation."}</p>
<p>{"Getting to know the person behind the practice is part of choosing where to begin. Explore the services below, or contact the practice if you have a question before booking."}</p>
<div className="signature-rule">
</div>
<span className="signature">{"Madhuri Gupta"}</span>
<small className="signature-note">{"SARSA JYOTISH SANSTHAN"}</small>
<BookingAnchor className="text-link" href="#consultations" data-public-scroll>{"Find your service \u2192"}</BookingAnchor>
</div>
</section>{"\n"}<MarginArt targetId="personal" /><span className="sarsa-scroll-destination" tabIndex="-1" data-scroll-destination="consultations">Find your service</span><section className="consultations" id="consultations">
<div className="wrap consultation-grid">
<div>
<p className="eyebrow">{"03 / YOUR STARTING POINT"}</p>
<h2>What would you like<br /><em>to understand?</em>
</h2>
<p><BookingCopy off="Read about a service, or contact the practice with your questions.">{"Read about each service, then book an appointment when you are ready."}</BookingCopy></p>
<BookingAnchor className="text-link" href="/services/kundli-prediction">{"Explore Kundli Prediction \u2197"}</BookingAnchor>
</div>
<div className="service-list">
{serviceOrder.map((id,i)=>{const service=catalogue.services.find(item=>item.id===id);return <div className="service-row" key={id}>
<div className="row-identity"><span>{'0'+(i+1)}</span><strong>{service.name}</strong><b aria-hidden="true">↗</b></div>
<div className="row-actions"><BookingLink to={'/services/'+service.id} aria-label={'Explore '+service.name}>Explore</BookingLink><BookingLink to={'/booking?service='+service.id} bookingMode="hide" aria-label={'Book '+service.name}>Book</BookingLink></div>
</div>;})}
</div>
</div>
</section>{"\n"}<section className="invitation wrap" id="invitation">
<div className="invitation-main">
<p className="eyebrow">{"LET\u2019S BEGIN"}</p>
<h2>{"Your questions."}<br />
<em>{"Your own conversation."}</em>
</h2>
<BookingButton className="button" data-book="General consultation">{"Book an appointment "}<span>{"\u2197"}</span>
</BookingButton>
</div>
<div className="contact-side">
<span>{"BEFORE YOU BOOK"}</span>
<p>{"Something you\u2019d"}<br />{"like to ask first?"}</p>
<button id="contact" className="contact-button">{"Contact the practice \u2192"}</button>
</div>
</section>
</div>;
}
