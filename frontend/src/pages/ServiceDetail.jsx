import {useLayoutEffect,useRef} from 'react';
import {useParams,Navigate} from 'react-router-dom';
import {BookingLink as Link} from '../site/BookingProduct.jsx';
import catalogue from '../site/catalogue.json';
import {mountServiceMotion} from '../site/service-motion.mjs';
import '../site/services.css';
const content={
 'kundli-matching':{word:'Before marriage.',line:'Look at both kundlis.',intro:'Planning marriage? Bring both birth charts and your questions about compatibility.',heading:'Understanding two kundlis.',points:['The questions you share','The context each person brings','What you would like to understand'],prepare:'Have the birth details you know for both people available. If any details are uncertain, ask the practice what is useful to bring.',art:'matching'},
 'vastu-consultation':{word:'The spaces around you.',line:'A Vastu perspective.',intro:'Explore questions about your home or workspace through a Vastu consultation.',heading:'Begin with the space you know.',points:['How you use the space','The questions you have','The context for your consultation'],prepare:'Make a note of the space you would like to discuss. Contact the practice to check whether a layout or photographs would be useful for your appointment.',art:'vastu'},
 numerology:{word:'Names. Dates. Numbers.',line:'Let’s understand them.',intro:'A personal conversation about the numbers linked to your names and dates.',heading:'Start with what matters to you.',points:['The name or date you want to discuss','The question behind your interest','The perspective you are looking for'],prepare:'Have the names and dates you would like to discuss available. Write down your questions so the conversation can focus on what matters to you.',art:'numerology'}
};
function Detail({service,data}){const root=useRef(null);useLayoutEffect(()=>{document.title=service.name+' | Sarsa Jyotish Sansthan';return mountServiceMotion(root.current,data.art);},[service.name,data.art]);return <div className={'sarsa-services detail-'+data.art} ref={root}>
<section className="detail-hero">
<div>
<p className="eyebrow">{service.name.toUpperCase()}</p>
<h1>{data.word}<br/>
<em>{data.line}</em>
</h1>
<p>{data.intro}</p>
<p className="service-facts">₹{(service.amount_paise/100).toLocaleString('en-IN')} · {service.duration_minutes} minutes · Google Meet</p>
<Link className="service-button" to={'/booking?service='+service.id}>Book an appointment ↗</Link>
</div>
<div className={'service-art art-'+data.art} aria-hidden="true">{data.art==='matching'?<>
<div data-layer className="chart-disc">✧</div>
<div data-layer className="chart-disc">✧</div>
<span data-layer className="art-seal">&amp;</span>
</>:data.art==='vastu'?<>
<div data-layer className="room-plane plane-back"/>
<div data-layer className="room-plane plane-floor"/>
<div data-layer className="room-object">⌂</div>
</>:<>
<span data-layer className="number-tile">3</span>
<span data-layer className="number-tile">6</span>
<span data-layer className="number-tile">9</span>
</>}</div>
</section>
<section className="service-preparation">
<p className="eyebrow">THE CONVERSATION</p>
<h2>{data.heading}</h2>
<div className="detail-topics">{data.points.map((point,i)=>
<article data-layer key={point}>
<span>0{i+1}</span>
<h3>{point}</h3>
</article>)}</div>
<p data-copy>A consultation helps you explore your questions. It does not guarantee an outcome or replace qualified medical, legal or financial advice.</p>
</section>
<section className="detail-prepare">
<div className="preparation-paper" data-layer>
<span>BEFORE YOUR APPOINTMENT</span>
<h2>A little preparation.<br/>
<em>A clearer starting point.</em>
</h2>
</div>
<div data-copy>
<p>{data.prepare}</p>
<p>All appointment times are shown in India time. After payment is verified and the appointment is confirmed, your Google Meet details will be prepared.</p>
<Link to="/contact">Ask the practice before booking ↗</Link>
</div>
</section>
<section className="service-preparation">
<div data-copy>
<p className="eyebrow">YOUR NEXT STEP</p>
<h2>Your questions.<br/>
<em>Your next step.</em>
</h2>
<Link className="service-button" to={'/booking?service='+service.id}>Book {service.name} ↗</Link>
</div>
</section>
</div>;}
export default function ServiceDetail(){const {serviceId}=useParams(),data=content[serviceId],service=catalogue.services.find(s=>s.id===serviceId);return data&&service?<Detail key={serviceId} data={data} service={service}/>:<Navigate to="/services" replace/>;}
