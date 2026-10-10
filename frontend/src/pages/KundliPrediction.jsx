import {BookingAnchor,BookingButton,BookingOnly,BookingCopy} from '../site/BookingProduct.jsx';
import {useLayoutEffect,useRef} from 'react';
import {useNavigate} from 'react-router-dom';
import {mountKundliPredictionMotion} from '../site/kundliprediction-motion.mjs';
import '../site/kundliprediction.css';
import catalogue from '../site/catalogue.json';
import ServiceVisualStory from '../site/ServiceVisualStory.jsx';
const consultation=catalogue.services.find(s=>s.id==='kundli-prediction');
export default function KundliPrediction(){
 const root=useRef(null),navigate=useNavigate();
 useLayoutEffect(()=>{document.title="Kundli Prediction | Sarsa Jyotish Sansthan";return mountKundliPredictionMotion(root.current);},[]);
 function actions(event){if(event.defaultPrevented)return;const el=event.target.closest('[data-contact],#enquire,a');if(!el)return;if(el.matches('[data-contact]')){event.preventDefault();navigate('/contact');}else if(el.id==='enquire'){event.preventDefault();navigate('/booking?service=kundli-prediction');}else if(el.getAttribute('href')?.startsWith('/')&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey&&event.button===0){event.preventDefault();navigate(el.getAttribute('href'));}}
 return <div className="sarsa-kundli settled" ref={root} onClick={actions}>
<section className="hero wrap" id="welcome" data-kundli-scene="welcome">
<div className="hero-copy">
<p className="breadcrumb">
<BookingAnchor href="/services">{"Services"}</BookingAnchor>{" "}<span>{"/"}</span>{" Kundli Prediction"}</p>
<p className="eyebrow">{"A PERSONAL CONSULTATION"}</p>
<h1>Life’s questions.<br />Your kundli.<br /><em>A little guidance.</em>
</h1>
<p className="lead">{"Explore your kundli with Madhuri Gupta. Bring the questions about life and your next steps that matter to you."}</p>
<div className="actions">
<BookingAnchor className="button" href="/booking?service=kundli-prediction">{"Book Kundli Prediction "}<span aria-hidden="true">{"\u2197"}</span>
</BookingAnchor>
<BookingAnchor className="text-link" href="#understand" data-public-scroll>{"Explore the service \u2193"}</BookingAnchor>
</div>
<p className="small">{"Kundli Prediction \u00b7 Sarsa Jyotish Sansthan"}</p>
</div>{"\n"}<figure className="chart-scene motion-scene" data-scene="registration" aria-label="Decorative paper layers with abstract chart geometry">
<div className="light-cast" aria-hidden="true">
</div>
<div className="art" aria-hidden="true">
<div className="plate plate-back" data-part="back">
</div>
<div className="plate plate-middle" data-part="middle">
<span className="corner top">{"01"}</span>
<span className="corner bottom">{"A DIFFERENT POINT OF VIEW"}</span>
</div>
<div className="plate plate-front" data-part="front">
<div className="plate-label">{"THE READING ROOM"}<span>{"\u2726"}</span>
</div>
<svg viewBox="0 0 340 340" fill="none">
<g className="engraving" stroke="currentColor" strokeWidth="1">
<circle cx="170" cy="170" r="135">
</circle>
<circle cx="170" cy="170" r="124" strokeDasharray="1 8">
</circle>
<path d="M170 35 305 170 170 305 35 170Z M75 75H265V265H75Z M75 75 265 265 M265 75 75 265 M170 35V305 M35 170H305">
</path>
<path d="M170 102 238 170 170 238 102 170Z">
</path>
</g>
<circle cx="170" cy="170" r="21" fill="#26483d">
</circle>
<path d="M170 158V182 M158 170H182" stroke="#f7f5ef">
</path>
<g fill="#955d45">
<circle cx="170" cy="35" r="4">
</circle>
<circle cx="305" cy="170" r="4">
</circle>
<circle cx="170" cy="305" r="4">
</circle>
<circle cx="35" cy="170" r="4">
</circle>
</g>
</svg>
<div className="plate-foot">
<span>{"CONTEXT"}</span>
<span>{"REFLECTION"}</span>
<span>{"PERSPECTIVE"}</span>
</div>
</div>
<div className="brass-seal" data-part="seal">{"S"}<span>{"J S"}</span>
</div>
</div>
<figcaption>{"AN ABSTRACT STUDY \u00b7 NOT A PERSONAL BIRTH CHART"}</figcaption>
</figure>
</section><div className="wrap"><ServiceVisualStory serviceId="kundli-prediction" name="Kundli Prediction"/></div>{"\n"}<div className="section-rule wrap">
<span>{"01 / UNDERSTAND"}</span>
<span>{"A LITTLE SPACE TO LOOK MORE CLOSELY"}</span>
</div>{"\n"}<span className="sarsa-scroll-destination" tabIndex="-1" data-scroll-destination="understand">Understand Kundli Prediction</span><section className="topics wrap" id="understand" data-kundli-scene="understand">
<div className="section-intro">
<p className="eyebrow">{"THE CONVERSATION"}</p>
<h2>What would you like<br />to understand?</h2>
<p>{"A kundli is your birth chart. In Jyotish, it is a starting point for life’s questions and the traditional meaning of the grah, or planets. Bring the questions you would like to discuss."}</p>
</div>
<div className="topic-list">
<article>
<span>{"01"}</span>
<div>
<h3>{"Your birth chart"}</h3>
<p>{"A kundli is a birth chart. Explore the chart as a whole and the questions you would like to bring to it."}</p>
</div>
<span className="topic-symbol" aria-hidden="true">{"\u25c7"}</span>
</article>
<article>
<span>{"02"}</span>
<div>
<h3>{"Periods & transitions"}</h3>
<p>{"Dasha means a planetary period in Jyotish. Ask about these periods and what they mean."}</p>
</div>
<span className="topic-symbol" aria-hidden="true">{"\u25f7"}</span>
</article>
<article>
<span>{"03"}</span>
<div>
<h3>{"Planetary transits"}</h3>
<p>{"Explore how transits are interpreted alongside a birth chart, with space to ask questions."}</p>
</div>
<span className="topic-symbol" aria-hidden="true">{"\u25ce"}</span>
</article>
</div>
</section>{"\n"}<section className="process" id="conversation" data-kundli-scene="conversation">
<div className="wrap">
<div className="process-heading">
<p className="eyebrow">{"02 / THE CONSULTATION"}</p>
<h2>{"A chart is the starting point."}<br />
<em>{"The conversation is yours."}</em>
</h2>
<p>{"A little preparation can help you make space for a thoughtful conversation."}</p>
</div>
<div className="thread-scene motion-scene" data-scene="thread">
<svg className="thread" viewBox="0 0 1080 130" preserveaspectratio="none" aria-hidden="true">
<path d="M50 90C170 -15 240 -15 360 65S540 160 650 70 860 -10 1030 65" pathLength="1">
</path>
</svg>
<div className="steps">
<article>
<span className="step-seal" data-part="step">{"01"}</span>
<h3>{"Begin with your questions"}</h3>
<p>{"Give the conversation a focus. What would you most like to understand?"}</p>
</article>
<article>
<span className="step-seal" data-part="step">{"02"}</span>
<h3>{"Explore the chart together"}</h3>
<p>{"Leave room for explanation, context and questions along the way."}</p>
</article>
<article>
<span className="step-seal" data-part="step">{"03"}</span>
<h3>{"Reflect on the discussion"}</h3>
<p>{"Bring the conversation back to what matters to you."}</p>
</article>
</div>
</div>
</div>
</section>{"\n"}<section className="preparation wrap" id="prepare" data-kundli-scene="prepare">
<figure className="field-scene motion-scene" data-scene="field">
<div className="field-art" aria-hidden="true">
<div className="sheet sheet-left" data-part="sheet">
<span>{"NOTES TO SELF"}</span>
<i>
</i>
<i>
</i>
<i>
</i>
<i>
</i>
<b>{"What would I"}<br />{"like to understand?"}</b>
</div>
<div className="sheet sheet-right" data-part="sheet">
<span>{"A LITTLE CONTEXT"}</span>
<div className="mini-diagram">{"\u25c7"}</div>
<i>
</i>
<i>
</i>
</div>
<div className="sheet sheet-main" data-part="sheet">
<span>{"BEFORE WE SPEAK"}</span>
<h3>{"Leave space"}<br />{"for your"}<br />
<em>{"questions."}</em>
</h3>
<div className="ink-line">
</div>
<small>{"A PERSONAL NOTEBOOK"}</small>
</div>
</div>
<figcaption>{"03 / PREPARE AT YOUR OWN PACE"}</figcaption>
</figure>
<div className="prepare-copy">
<p className="eyebrow">{"BEFORE THE CONVERSATION"}</p>
<h2>A few things<br />to keep ready.</h2>
<p>{"Note your questions and the birth details you know. Ask the practice if any details are uncertain."}</p>
<ul className="checklist">
<li>
<span>{"01"}</span>
<div>
<strong>{"Write down your questions."}</strong>
<p>{"Note the questions you would like to explore."}</p>
</div>
</li>
<li>
<span>{"02"}</span>
<div>
<strong>{"Keep useful context nearby."}</strong>
<p>{"The information needed for your reading will be confirmed before the consultation."}</p>
</div>
</li>
<li>
<span>{"03"}</span>
<div>
<strong>{"Ask if you are unsure."}</strong>
<p>{"If you are unsure which details are needed, include that question in your enquiry."}</p>
</div>
</li>
</ul>
</div>
</section>{"\n"}<section className="details-section" id="questions" data-kundli-scene="questions">
<div className="wrap details-grid">
<div>
<p className="eyebrow">{"04 / THE PRACTICAL DETAILS"}</p>
<h2>A few details<br />before you book.</h2>
<p>{"Read the details before you decide to book."}</p>
<BookingOnly><div className="terms">
<p className="eyebrow">{"YOUR CONSULTATION"}</p>
<p>₹{(consultation.amount_paise/100).toLocaleString('en-IN')} · {consultation.duration_minutes} minutes · Google Meet. View available times on the booking page.</p>
</div></BookingOnly>
</div>
<div className="faqs">
<details open>
<summary>{"What can I bring to the conversation?"}</summary>
<p>{"Bring the questions that led you to explore a kundli reading. Ask the practice which topics can be covered."}</p>
</details>
<details>
<summary>{"Do I need to understand astrology?"}</summary>
<p>{"You can ask what the consultation involves before deciding. Start with your questions, in your own words."}</p>
</details>
<details>
<summary>{"What information will be needed?"}</summary>
<p>{"Have the birth date, time and place you know available. If any details are uncertain, contact the practice about what is useful to bring."}</p>
</details>
<details>
<summary>{"How do I arrange a consultation?"}</summary>
<p><BookingCopy off="Contact the practice with your questions.">{"Your Kundli Prediction selection carries into booking. Choose a time and review your details before payment. If you want to ask first, use Contact."}</BookingCopy></p>
</details>
</div>
</div>
</section>{"\n"}<section className="closing wrap" id="begin" data-kundli-scene="begin">
<div className="closing-image">
<img src="/media/consultation-still-life.png" alt="" loading="lazy" />
</div>
<div className="closing-copy">
<p className="eyebrow">{"05 / YOUR NEXT STEP"}</p>
<h2>{"Bring your questions."}<br />
<em>{"Explore your kundli."}</em>
</h2>
<p>{"Explore a Kundli Prediction consultation with Madhuri Gupta."}</p>
<BookingButton className="button" id="enquire">{"Book Kundli Prediction "}<span aria-hidden="true">{"\u2197"}</span>
</BookingButton>
<BookingOnly><p className="small">{"Choose a time and review your details before payment."}</p></BookingOnly>
<button className="text-link contact-link" data-contact>{"Ask a question before booking \u2192"}</button>
<br />
<BookingAnchor className="text-link" href="/services">{"Explore other services \u2192"}</BookingAnchor>
</div>
</section>{"\n"}</div>;
}
