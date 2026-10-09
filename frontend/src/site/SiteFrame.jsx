import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {NavLink,useLocation} from 'react-router-dom';
import {BookingLink as Link,BookingOnly} from './BookingProduct.jsx';
import {usePublicHeader} from './PublicHeaderContext.jsx';
import {AnchorLink} from './AnchorNavigation.jsx';
import './site.css';

const navigation=[['/','Home'],['/about','About Madhuri'],['/services','Services'],['/contact','Contact']];
export function SiteHeader(){
 const bar=usePublicHeader(),container=useRef(null),trigger=useRef(null),panel=useRef(null);
 const [open,setOpen]=useState(false),location=useLocation();
 useEffect(()=>setOpen(false),[location.pathname,location.hash]);
 useLayoutEffect(()=>{
  const frame=container.current.closest('.sarsa-site');let height;
  const measure=()=>{const next=bar.current.getBoundingClientRect().height;if(next!==height){height=next;frame.style.setProperty('--site-header-height',next+'px');}};
  const observer=new ResizeObserver(measure);observer.observe(bar.current);measure();return()=>observer.disconnect();
 },[bar]);
 useEffect(()=>{
  const media=matchMedia('(min-width: 1024px)');
  function resize(){if(!media.matches)return;const active=document.activeElement;
   if(panel.current?.contains(active)||active===trigger.current){const href=active.getAttribute('href');const replacement=href&&container.current.querySelector(`.sarsa-desktop-nav a[href="${href}"]`);(replacement||container.current.querySelector('.sarsa-brand')).focus({preventScroll:true});}
   setOpen(false);
  }
  media.addEventListener('change',resize);return()=>media.removeEventListener('change',resize);
 },[]);
 useEffect(()=>{
  if(!open)return;
  function outside(event){if(!container.current.contains(event.target))setOpen(false);}
  function escape(event){if(event.key==='Escape'){setOpen(false);trigger.current.focus({preventScroll:true});}}
  document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape);};
 },[open]);
 return <header className="sarsa-header" ref={container}>
  <div className="sarsa-frame-wrap sarsa-header-bar" ref={bar}>
   <Link className="sarsa-brand" to="/">SARSA<span>Jyotish Sansthan</span></Link>
   <nav className="sarsa-desktop-nav" aria-label="Main navigation">{navigation.slice(1).map(([to,label])=><NavLink key={to} to={to}>{label}</NavLink>)}<Link className="sarsa-action" to="/booking" bookingMode="hide">Book an appointment <span aria-hidden="true">↗</span></Link></nav>
   <div className="sarsa-phone-tools"><Link className="sarsa-action sarsa-compact" to="/booking" bookingMode="hide">Book <span aria-hidden="true">↗</span></Link><button ref={trigger} type="button" className="sarsa-menu-trigger" aria-expanded={open} aria-controls="sarsa-phone-menu" onClick={()=>setOpen(value=>!value)}>Menu <span aria-hidden="true">{open?'×':'☰'}</span></button></div>
  </div>
  <nav id="sarsa-phone-menu" ref={panel} hidden={!open} aria-label="Phone navigation">{navigation.map(([to,label])=><NavLink key={to} to={to} end={to==='/'} onClick={()=>setOpen(false)}>{label}</NavLink>)}</nav>
 </header>;
}
export function SiteSkip(){return <AnchorLink className="sarsa-skip" to={useLocation().pathname+'#page-content'}>Skip to content</AnchorLink>;}
export function SiteFooter(){return <footer className="sarsa-footer"><div className="sarsa-frame-wrap sarsa-footer-grid"><div><Link className="sarsa-brand" to="/">SARSA<span>Jyotish Sansthan</span></Link><p>Kundli, Vastu and numerology.<br/>Begin with your question.</p></div><nav aria-label="Footer pages"><Link to="/about">About Madhuri</Link><Link to="/services">Services</Link><Link to="/contact">Contact</Link><Link to="/booking" bookingMode="hide">Book an appointment</Link><BookingOnly><Link to="/booking-help">Booking help</Link></BookingOnly></nav><div><address>8, Gailana Road, LIC Colony, Agra - 282007</address><nav className="sarsa-policy-links" aria-label="Policies"><Link to="/privacy">Privacy</Link><Link to="/terms">Terms</Link><BookingOnly><Link to="/booking-policy">Booking policy</Link></BookingOnly></nav></div></div><p className="sarsa-frame-wrap sarsa-footer-note">© {new Date().getFullYear()} Sarsa Jyotish Sansthan.</p></footer>;}
