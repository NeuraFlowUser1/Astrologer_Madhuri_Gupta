import {PublicPage,copy,Action,Motifs,Portrait,ServiceCards,NextStep,FAQ} from '../site/PublicSections.jsx';
export default function Home(){return <PublicPage className="sarsa-home">
 <section className="hero"><div className="wrap"><div className="hero-copy"><h1 tabIndex={-1}>{copy.home.title}</h1><p className="hindi" lang="hi">{copy.home.hindi}</p><p>{copy.home.body}</p><div className="actions"><Action to="/booking" bookingMode="hide">Book an appointment</Action><Action to="/services" secondary>Explore services</Action></div><p className="hero-caption">{copy.home.caption}</p></div></div></section>
 <section className="section person" id="madhuri"><Motifs/><div className="wrap two-column"><Portrait/><div><h2>{copy.home.person_title}</h2><p>{copy.home.person_body}</p><Action to="/about" secondary>Meet the person</Action></div></div></section>
 <section className="section sage"><div className="wrap"><div className="section-heading"><h2>Find your service</h2><Action to="/services" secondary>See all services</Action></div><ServiceCards attention/></div></section>
 <NextStep shield/>
 <section className="section"><div className="wrap faq-wrap"><h2>{copy.home.faq_title}</h2><FAQ name="sarsa-home-faq" items={copy.home.faq}/></div></section>
 <section className="section ending sage"><div className="wrap"><h2>{copy.home.ending_title}</h2><p>{copy.home.ending_body}</p><div className="actions"><Action to="/contact" secondary>Ask a question</Action><Action to="/booking" bookingMode="hide">Book an appointment</Action></div></div></section>
 </PublicPage>;}
