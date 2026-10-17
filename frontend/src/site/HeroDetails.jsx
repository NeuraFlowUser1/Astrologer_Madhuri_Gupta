import {BookingLink} from './BookingProduct.jsx';
import catalogue from './catalogue.json';
import {Fragment} from 'react';
import {madhuriExperience,madhuriStudies} from './hero-content.mjs';
export {madhuriExperience} from './hero-content.mjs';

/** Owner-confirmed experience and source-backed studies; the document gallery stays retired. */
const paths={
 calendar:'M6 2h2v3h8V2h2v3h2a2 2 0 0 1 2 2v13a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2V2Zm14 8H4v10h16V10Zm-4 3v2h-2v-2h2Zm-6 0v2H8v-2h2Z',
 chat:'M12 2C6.48 2 2 5.97 2 10.86c0 2.37 1.06 4.53 2.8 6.12L4 22l5.2-2.5c.9.2 1.84.3 2.8.3 5.52 0 10-4 10-8.94S17.52 2 12 2Zm-5 8h10v2H7v-2Zm0-4h7v2H7V6Z',
 sun:'M11 0h2v4h-2V0Zm0 20h2v4h-2v-4ZM0 11h4v2H0v-2Zm20 0h4v2h-4v-2ZM3.5 2l2.9 2.9L5 6.3 2.1 3.4 3.5 2Zm15 15 2.9 2.9-1.4 1.4-2.9-2.9 1.4-1.4ZM2 20.5l2.9-2.9 1.4 1.4-2.9 2.9L2 20.5ZM17.6 5l2.9-2.9 1.4 1.4L19 6.4 17.6 5ZM12 6a6 6 0 1 0 0 12 6 6 0 0 0 0-12Z',
 book:'M2 3c3.8-1 7.5-.5 10 1.4C14.5 2.5 18.2 2 22 3v17c-3.8-1-7.5-.5-10 1.4C9.5 19.5 5.8 19 2 20V3Zm9 3C8.9 4.7 6.5 4.3 4 4.6v13.1c2.5-.2 4.9.2 7 1.2V6Zm2 12.9c2.1-1 4.5-1.4 7-1.2V4.6c-2.5-.3-4.9.1-7 1.4v12.9Z',
 'kundli-matching':'M9 3a6 6 0 1 0 0 12 6 6 0 0 0 0-12Zm0 2a4 4 0 1 1 0 8 4 4 0 0 1 0-8Zm6 4a6 6 0 1 0 0 12 6 6 0 0 0 0-12Zm0 2a4 4 0 1 1 0 8 4 4 0 0 1 0-8Z',
 'kundli-prediction':'M12 1 23 12 12 23 1 12 12 1Zm0 3.2L4.2 12l7.8 7.8 7.8-7.8L12 4.2Zm0 3.3 4.5 4.5-4.5 4.5-4.5-4.5L12 7.5Z',
 'vastu-consultation':'m12 2 11 9-1.3 1.55L20 11.15V22h-6v-7h-4v7H4V11.15l-1.7 1.4L1 11 12 2Z',
 numerology:'m8 2 2 .4L9.1 7H15l1-5 2 .4-.9 4.6H22v2h-5.3l-1.2 6H20v2h-4.9l-1 5-2-.4.9-4.6H7.1l-1 5-2-.4L5 17H1v-2h4.4l1.2-6H2V7h5l1-5Zm.7 7-1.2 6h5.9l1.2-6H8.7Z',
 'prashna-kundali':'M12 2a9 9 0 0 0-9 9v7a3 3 0 0 0 3 3h12a3 3 0 0 0 3-3v-7a9 9 0 0 0-9-9Zm0 4a3.5 3.5 0 0 1 2 6.37V14h-2v-2.6l.65-.24A1.5 1.5 0 1 0 10.5 9H8.5A3.5 3.5 0 0 1 12 6Zm1 10v2h-2v-2h2Z',
};
export function HeroIcon({name}){return <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fillRule={name==='kundli-prediction'?'evenodd':undefined} d={paths[name]}/></svg>;}
const serviceOrder=['kundli-matching','kundli-prediction','vastu-consultation','numerology','prashna-kundali'];
export function HomeHeroBand(){return <div className="hero-band" data-hero-band><div className="hero-band-inner"><div className="band-intro"><h2>How can we help?</h2><p>Explore a service.</p></div><ul className="service-choices">{serviceOrder.map(id=><li key={id}><BookingLink className="service-choice" to={'/services/'+id}><HeroIcon name={id}/>{catalogue.services.find(service=>service.id===id).name}</BookingLink></li>)}</ul></div></div>;}
export function AboutHeroBand(){return <div className="hero-band" data-hero-band><div className="hero-band-inner"><div className="band-intro"><h2>Her experience<br/>and studies</h2><p>Get to know Madhuri.</p></div><article className="study-fact experience-fact"><div className="fact-icon"><HeroIcon name="sun"/></div><div><h3>{madhuriExperience}<span>years of experience</span></h3><p>Personal guidance with Madhuri.</p></div></article>{madhuriStudies.map(study=><article className="study-fact" key={study.icon}><div className="fact-icon"><HeroIcon name={study.icon}/></div><div><h3>{study.titles.map((title,index)=><Fragment key={title}>{index>0&&<br/>}{title}</Fragment>)}</h3><p>{study.institute}</p></div></article>)}</div></div>;}
