import {BookingAnchor,BookingButton,BookingCopy} from '../site/BookingProduct.jsx';
import {useLayoutEffect,useRef} from 'react';
import {useNavigate} from 'react-router-dom';
import {mountAboutMotion} from '../site/about-motion.mjs';
import '../site/about.css';
export default function About(){
 const root=useRef(null),navigate=useNavigate();
 useLayoutEffect(()=>{document.title='About Madhuri Gupta | Sarsa Jyotish Sansthan';return mountAboutMotion(root.current);},[]);
 function actions(event){const button=event.target.closest('[data-book],#contact');if(!button)return;const service=button.dataset.book?.toLowerCase().replaceAll(' ','-');navigate(button.id==='contact'?'/contact':'/booking'+(['kundli-prediction','kundli-matching','vastu-consultation','numerology'].includes(service)?'?service='+service:''));}
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
<BookingAnchor href="#approach" className="text-link" data-enter="3">{"Discover her approach \u2193"}</BookingAnchor>
</div>
</div>
</section>{"\n"}<section className="welcome wrap" id="welcome">
<span className="eyebrow">{"A PERSONAL INTRODUCTION"}</span>
<h2>{"Meet the person."}<br />
<em>{"Find your starting point."}</em>
</h2>
<p>{"Madhuri Gupta leads Sarsa Jyotish Sansthan, bringing a personal identity to its astrology, numerology and Vastu consultations."}</p>
</section>{"\n"}<section className="approach" id="approach">
<div className="wrap">
<div className="section-title">
<div>
<p className="eyebrow">{"01 / THE APPROACH"}</p>
<h2>{"A conversation"}<br />{"with room "}<em>{"for you."}</em>
</h2>
</div>
<p>{"Begin with a question."}<br />{"Make space to explore it."}<br />{"Bring the discussion back to what matters."}</p>
</div>
<div className="approach-scene" id="approach-scene">
<div className="connecting-rule" aria-hidden="true">
</div>
<article>
<div className="moving-paper" aria-hidden="true">
</div>
<span className="chapter">{"I."}</span>
<h3>{"Begin with listening."}</h3>
<p>{"The context behind a question deserves space, as much as the question itself."}</p>
</article>
<article>
<div className="moving-paper" aria-hidden="true">
</div>
<span className="chapter">{"II."}</span>
<h3>{"Explore with curiosity."}</h3>
<p>{"A thoughtful exchange makes room for explanation and for the questions that follow."}</p>
</article>
<article>
<div className="moving-paper" aria-hidden="true">
</div>
<span className="chapter">{"III."}</span>
<h3>{"Keep the person in view."}</h3>
<p>{"The conversation comes back to you and what brought you to the consultation."}</p>
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
<h2>{"A name."}<br />{"A face."}<br />
<em>{"A personal connection."}</em>
</h2>
<p>{"Behind Sarsa Jyotish Sansthan is Madhuri Gupta. The practice offers Kundli Prediction, Kundli Matching, Numerology and Vastu Consultation."}</p>
<p>{"Getting to know the person behind a consultation is part of choosing where to begin. Explore the areas below, or contact the practice if you have a question before booking."}</p>
<div className="signature-rule">
</div>
<span className="signature">{"Madhuri Gupta"}</span>
<small className="signature-note">{"SARSA JYOTISH SANSTHAN"}</small>
<BookingAnchor className="text-link" href="#consultations">{"Explore the consultations \u2192"}</BookingAnchor>
</div>
</section>{"\n"}<section className="consultations" id="consultations">
<div className="wrap consultation-grid">
<div>
<p className="eyebrow">{"03 / YOUR STARTING POINT"}</p>
<h2>{"Different questions."}<br />
<em>{"A considered choice."}</em>
</h2>
<p><BookingCopy off="Explore a guidance area, or contact the practice with your questions.">{"Choose a consultation to take your selection into the appointment journey."}</BookingCopy></p>
<BookingAnchor className="text-link" href="/services/kundli-prediction">{"Explore Kundli Prediction \u2197"}</BookingAnchor>
</div>
<div className="service-list">
<BookingButton data-book="Kundli Prediction" offText="Explore Kundli Prediction" offPath="/services/kundli-prediction">
<span>{"01"}</span>
<strong>{"Kundli Prediction"}</strong>
<b>{"\u2197"}</b>
</BookingButton>
<BookingButton data-book="Kundli Matching" offText="Explore Kundli Matching" offPath="/services/kundli-matching">
<span>{"02"}</span>
<strong>{"Kundli Matching"}</strong>
<b>{"\u2197"}</b>
</BookingButton>
<BookingButton data-book="Vastu Consultation" offText="Explore Vastu Consultation" offPath="/services/vastu-consultation">
<span>{"03"}</span>
<strong>{"Vastu Consultation"}</strong>
<b>{"\u2197"}</b>
</BookingButton>
<BookingButton data-book="Numerology" offText="Explore Numerology" offPath="/services/numerology">
<span>{"04"}</span>
<strong>{"Numerology"}</strong>
<b>{"\u2197"}</b>
</BookingButton>
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
