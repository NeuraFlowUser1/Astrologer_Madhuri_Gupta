
import {BookingLink as Link,BookingOnly,BookingCopy} from '../site/BookingProduct.jsx';
import {useLayoutEffect,useRef} from 'react';
import catalogue from '../site/catalogue.json';
import '../site/services.css';
import ServiceArtwork from '../site/ServiceArtwork.jsx';
import ServiceMedia from '../site/ServiceMedia.jsx';
import {mountDirectoryMotion} from '../site/directory-motion.mjs';
const descriptions={'kundli-prediction':'Questions about work, marriage, family or a changing phase of life? Explore your birth chart, grah and dasha in simple words.','kundli-matching':'Thinking about marriage? Explore what two kundlis can tell you about compatibility and the questions you want to discuss.','vastu-consultation':'Questions about your home or workspace? Understand its layout and directions through the principles of Vastu.',numerology:'Curious about your name, date of birth or numbers? Explore their meaning in the numerology tradition.'};
export default function Services(){const root=useRef(null);useLayoutEffect(()=>{document.title='Services | Sarsa Jyotish Sansthan';return mountDirectoryMotion(root.current);},[]);return <div className="sarsa-services services-directory-page" ref={root}>
<section className="service-intro">
<p className="eyebrow">FIND YOUR STARTING POINT</p>
<h1>Different questions.<br/>
<em>Space to explore them.</em>
</h1>
<p>Start with the question you have. Explore Jyotish, Vastu and Numerology with Madhuri Gupta. <BookingCopy off="Contact the practice with your questions.">Read about a service, then book an appointment when you are ready.</BookingCopy></p>
</section>
<section className="service-directory" aria-label="Services">{catalogue.services.map((s,i)=>
<article key={s.id} data-directory-card>
<div className="directory-photo" data-directory-part="photo"><ServiceMedia serviceId={s.id}/><div className="directory-motif" data-directory-part="motif"><ServiceArtwork id={s.id}/></div></div>
<div data-directory-part="copy"><span className="service-number">0{i+1}</span>
<h2>{s.name}</h2>
<p>{descriptions[s.id]}</p>
<BookingOnly><p className="service-facts">₹{(s.amount_paise/100).toLocaleString('en-IN')} · {s.duration_minutes} minutes · Google Meet</p></BookingOnly>
</div><div className="service-actions" data-directory-part="actions">
<Link to={'/services/'+s.id}>Explore the service ↗</Link>
<Link className="service-button" to={'/booking?service='+s.id} bookingMode="hide">Book an appointment</Link>
</div>
</article>)}</section>
<section className="service-guide first-service-guide" data-directory-guide="questions" aria-labelledby="question-guide-title">
<p className="eyebrow">LIFE’S QUESTIONS</p><h2 id="question-guide-title">Which question brings you here?</h2>
<div className="question-guide">{[
['kundli-matching','Planning a marriage?','Start with Kundli Matching.'],
['kundli-prediction','Thinking about your next phase in life?','Explore Kundli Prediction.'],
['vastu-consultation','Questions about your home or workspace?','Read about Vastu Consultation.'],
['numerology','Curious about names, dates and numbers?','Explore Numerology.']
].map(([id,question,label])=><div key={id} data-guide-part><div className="guide-motif" aria-hidden="true"><ServiceArtwork id={id}/></div><h3>{question}</h3><Link to={'/services/'+id}>{label} ↗</Link></div>)}</div>
<p>These are starting points. Read the service details, or ask the practice which area fits your question.</p>
</section>
<section className="service-guide jyotish-guide" data-directory-guide="jyotish" aria-labelledby="jyotish-guide-title">
<p className="eyebrow" lang="hi">कुंडली, ग्रह और दशा — सरल शब्दों में।</p><h2 id="jyotish-guide-title">A little Jyotish, in simple words</h2>
<div className="jyotish-visual"><svg className="knowledge-diagram" viewBox="0 0 320 320" aria-hidden="true"><g data-guide-part><path d="M160 70 250 160 160 250 70 160ZM70 70h180v180H70ZM70 70l180 180M250 70 70 250"/><circle cx="160" cy="160" r="7"/></g><g data-guide-part><circle cx="160" cy="160" r="146"/><path d="M160 14A146 146 0 0 1 306 160"/><circle cx="160" cy="14" r="6"/><circle cx="306" cy="160" r="6"/><circle cx="160" cy="306" r="6"/></g></svg><dl>{[
['Kundli','A birth chart used in the Jyotish tradition.'],
['Grah','The planetary influences discussed in Jyotish.'],
['Dasha','A planetary period in the traditional astrological system.'],
['Gochar','The movement of planets considered in relation to a birth chart.']
].map(([term,meaning])=><div key={term} data-guide-part><dt>{term}</dt><dd>{meaning}</dd></div>)}</dl></div>
<p>Vastu looks at the layout and directions of a space. Numerology explores names, dates and numbers. These are traditional ideas; you can ask what an unfamiliar term means.</p>
</section>
<section className="service-preparation">
<p className="eyebrow">BEFORE WE BEGIN</p>
<h2>A question is enough<br/>to start a conversation.</h2>
<p>Write down what you would like to discuss. If you are unsure which service fits your question, ask the practice before booking.</p>
<Link className="service-button" to="/contact">Ask a question ↗</Link>
</section>
</div>;}
