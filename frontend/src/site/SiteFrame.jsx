import {NavLink,useLocation} from 'react-router-dom';
import {BookingLink as Link,BookingOnly} from './BookingProduct.jsx';
import BackToTop from './BackToTop.jsx';
import PhoneLink from './PhoneLink.jsx';
import './site.css';
import './brand.css';
function MenuLabel({children}){return <><span className="sarsa-nav-label">{children}</span><span className="sarsa-nav-reserve" aria-hidden="true">{children}</span></>;}
export function SiteHeader({headerRef,sticky=false}){
 const {pathname}=useLocation();
 const booking=pathname==='/booking'||pathname.startsWith('/booking/')||['/booking-help','/booking-policy'].includes(pathname);
 return <header ref={headerRef} className={'sarsa-header'+(sticky?' booking-header':'')}>
  <Link className="sarsa-brand" to="/"><img className="brand-logo" src="/media/sarsa-kundli-lotus-logo-128.png" alt="" width="42" height="42"/><span className="brand-copy">Sarsa<small>JYOTISH SANSTHAN</small></span></Link>
  <nav aria-label="Main navigation"><NavLink to="/about"><MenuLabel>About Madhuri</MenuLabel></NavLink><NavLink to="/services"><MenuLabel>Services</MenuLabel></NavLink><NavLink to="/testimonials"><MenuLabel>Reviews</MenuLabel></NavLink><NavLink to="/contact"><MenuLabel>Contact</MenuLabel></NavLink></nav>
  <PhoneLink className="header-phone"/>
  <Link className="sarsa-action" to="/booking" bookingMode="hide" aria-current={booking?'page':undefined}>Book an appointment <span aria-hidden="true">↗</span></Link>
 </header>;
}
export function SiteFooter({home=false,showBackToTop=home,scrollerRef}){return <footer className="sarsa-footer"><div className="sarsa-footer-identity"><div className="sarsa-brand">Sarsa<span>WITH MADHURI GUPTA</span></div><PhoneLink className="footer-phone"/></div><nav aria-label="Footer navigation"><Link to="/about">About</Link><Link to="/services">Services</Link><Link to="/testimonials">Reviews</Link><Link to="/contact">Contact</Link><Link to="/booking" bookingMode="hide">Book an appointment</Link><Link to="/privacy">Privacy</Link><Link to="/terms">Terms</Link><BookingOnly><Link to="/booking-policy">Booking policy</Link></BookingOnly></nav><p>© 2026 Sarsa Jyotish Sansthan</p>{showBackToTop&&<BackToTop scrollerRef={scrollerRef}/>}</footer>;}
