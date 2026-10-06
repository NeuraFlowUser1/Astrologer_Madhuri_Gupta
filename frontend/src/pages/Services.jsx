
import {BookingLink as Link,BookingOnly,BookingCopy} from '../site/BookingProduct.jsx';
import {useEffect} from 'react';
import catalogue from '../site/catalogue.json';
import '../site/services.css';
const descriptions={'kundli-prediction':'Life questions, explored through your birth chart.','kundli-matching':'A considered conversation about compatibility.','vastu-consultation':'A fresh perspective on the spaces around you.',numerology:'Explore the patterns associated with names and dates.'};
export default function Services(){useEffect(()=>{document.title='Consultations | Sarsa Jyotish Sansthan';},[]);return <div className="sarsa-services">
<section className="service-intro">
<p className="eyebrow">FIND YOUR STARTING POINT</p>
<h1>Different questions.<br/>
<em>Space to explore them.</em>
</h1>
<p>Choose the consultation that best fits what is on your mind. <BookingCopy off="Contact the practice with your questions.">Each is a personal, 30-minute online conversation with the practice.</BookingCopy></p>
</section>
<section className="service-directory" aria-label="Consultation choices">{catalogue.services.map((s,i)=>
<article key={s.id}>
<span className="service-number">0{i+1}</span>
<h2>{s.name}</h2>
<p>{descriptions[s.id]}</p>
<BookingOnly><p className="service-facts">₹{(s.amount_paise/100).toLocaleString('en-IN')} · {s.duration_minutes} minutes · Google Meet</p></BookingOnly>
<div className="service-actions">
<Link to={'/services/'+s.id}>Explore the consultation ↗</Link>
<Link className="service-button" to={'/booking?service='+s.id}>Choose a time</Link>
</div>
</article>)}</section>
<section className="service-preparation">
<p className="eyebrow">BEFORE WE BEGIN</p>
<h2>A question is enough<br/>to start a conversation.</h2>
<p>Write down what you would like to discuss. If you are unsure which consultation fits your needs, ask the practice before booking.</p>
<Link className="service-button" to="/contact">Ask a question ↗</Link>
</section>
</div>;}
