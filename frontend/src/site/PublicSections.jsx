import {useEffect,useRef,useState} from 'react';
import {useLocation} from 'react-router-dom';
import {BookingLink as Link,BookingOnly,useBookingProduct} from './BookingProduct.jsx';
import {usePublicHeader} from './PublicHeaderContext.jsx';
import {moveToTarget} from './anchor-navigation.mjs';
import {watchCardAttention} from './card-attention.mjs';
import copy from './public-copy.json';
import './public-pages.css';

export {copy};
export const art=id=>`/media/sarsa-public/${id}-illustration.svg`;
export function Action({to,secondary=false,light=false,children,...props}){return <Link to={to} className={`button${secondary?' secondary':''}${light?' light':''}`} {...props}>{children}<span aria-hidden="true">↗</span></Link>;}
export function Motifs(){return <><img className="side-motif left" src="/media/sarsa-public/jyotish-orbit-motif.svg" alt="" width="320" height="320"/><img className="side-motif right" src="/media/sarsa-public/jyotish-orbit-motif.svg" alt="" width="320" height="320"/></>;}
export function Portrait({smaller=false}){return <figure className={`portrait${smaller?' smaller':''}`}><img src="/media/madhuri-gupta-portrait.jpeg" alt="Madhuri Gupta" width="800" height="1000" loading="lazy"/><figcaption lang="hi">माधुरी गुप्ता</figcaption></figure>;}
export function ServiceCards({attention=false}){
 const root=useRef(null),played=useRef(false);
 useEffect(()=>{if(!attention)return;return watchCardAttention(root.current,{played});},[attention]);
 return <div className="service-grid" ref={root}>{copy.services.map(service=><article className="service-card" key={service.id}><img className="service-art" src={art(service.id)} alt="" width="640" height="320" loading="lazy"/><div className="card-content"><h3>{service.name}</h3><p>{service.description}</p><div className="actions"><Action to={'/services/'+service.id} secondary>Explore the service</Action><Action to={'/booking?service='+service.id} bookingMode="hide">Book an appointment</Action></div></div></article>)}</div>;
}
export function FAQ({items,name}){return <div className="faq">{items.map(([question,answer])=><details name={name} key={question}><summary>{question}<span className="faq-icon" aria-hidden="true"/></summary><p>{answer}</p></details>)}</div>;}
export function Process(){return <ol className="process">{copy.process.map(([title,body],i)=><li key={title}><span className="step-number">0{i+1}</span><h3>{title}</h3><p>{body}</p></li>)}</ol>;}
export function NextStep({shield=false}){
 const {enabled,verified}=useBookingProduct();
 return <section className="section deep"><div className="wrap"><div className={shield?'begin-title':''}>{shield&&<div className="shield" aria-hidden="true"><span>✦</span><i>✧</i><b>✧</b></div>}<div><h2>{copy.home.begin_title}</h2><p className="hindi" lang="hi">{enabled?copy.home.begin_hindi:copy.product_modes.unavailable_hindi}</p></div></div><BookingOnly><Process/><div className="actions"><Action to="/booking" light>Book an appointment</Action></div></BookingOnly>{!enabled&&<div className="off-copy"><h3>{copy.product_modes.off_heading}</h3><p>{verified?copy.product_modes.off_body:copy.product_modes.unknown_body}</p><Action to="/contact" secondary>Contact the practice</Action></div>}</div></section>;
}
export function BackToTop(){
 const [visible,setVisible]=useState(false),[editing,setEditing]=useState(false),button=useRef(null),cancel=useRef(()=>{}),bar=usePublicHeader(),location=useLocation();
 useEffect(()=>{
  const update=()=>setVisible(old=>window.scrollY>600?true:window.scrollY<400&&document.activeElement!==button.current?false:old);
  const focus=()=>setEditing(location.pathname==='/contact'&&!!document.activeElement?.matches('input,textarea,select,[contenteditable]'));
  window.addEventListener('scroll',update,{passive:true});document.addEventListener('focusin',focus);document.addEventListener('focusout',focus);update();
  return()=>{cancel.current();window.removeEventListener('scroll',update);document.removeEventListener('focusin',focus);document.removeEventListener('focusout',focus);};
 },[location.pathname]);
 return <button ref={button} type="button" className="back-top" aria-label="Back to top" hidden={!visible||editing} onBlur={()=>{if(window.scrollY<400)setVisible(false);}} onClick={()=>{cancel.current();const heading=document.querySelector('#page-content h1');cancel.current=moveToTarget({target:heading,header:bar?.current,top:true,smooth:true,onDone:()=>setVisible(false)});}}><span aria-hidden="true">↑</span><span className="top-tooltip" aria-hidden="true">Top</span></button>;
}
export function PublicPage({children,className=''}){return <div className={'sarsa-public '+className}>{children}<BackToTop/></div>;}
