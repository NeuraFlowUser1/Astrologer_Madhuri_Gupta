import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {MemoryRouter,Routes,Route} from 'react-router-dom';
import {beforeEach,afterEach,test,expect,vi} from 'vitest';
const state=vi.hoisted(()=>({enabled:true,verified:true,flow:{started:false,busy:false,blocked:false,retry:null,waiting:0,error:'',receipt:null,start:vi.fn(),check:vi.fn(),verify:vi.fn(),resend:vi.fn(),restart:vi.fn(async()=>true)}}));
vi.mock('../../src/contact/useEnquiry.jsx',()=>({useEnquiry:()=>state.flow}));
vi.mock('../../src/site/BookingProduct.jsx',async()=>{
 const {Link}=await import('react-router-dom');
 return {useBookingProduct:()=>state,BookingOnly:({children})=>state.enabled?children:null,BookingNavigationLink:props=>state.enabled?<Link {...props}/>:null,
 BookingLink:({to,bookingMode,children,...props})=>!state.enabled&&to.startsWith('/booking')&&bookingMode==='hide'?null:<Link to={!state.enabled&&to.startsWith('/booking')?'/contact':to} {...props}>{children}</Link>};
});
import {PublicHeaderProvider} from '../../src/site/PublicHeaderContext.jsx';
import {AnchorNavigationProvider} from '../../src/site/AnchorNavigation.jsx';
import {SiteHeader,SiteFooter,SiteSkip} from '../../src/site/SiteFrame.jsx';
import Home from '../../src/pages/Home.jsx';
import About from '../../src/pages/About.jsx';
import Services from '../../src/pages/Services.jsx';
import ContactPage from '../../src/pages/ContactPage.jsx';
import ServiceDetail from '../../src/pages/ServiceDetail.jsx';
import KundliPrediction from '../../src/pages/KundliPrediction.jsx';
import PolicyPage from '../../src/pages/PolicyPage.jsx';
let host,root,media,resizes;
const settle=()=>act(async()=>{for(let i=0;i<8;i++)await Promise.resolve();});
async function render(page,route='/'){await act(async()=>root.render(<MemoryRouter initialEntries={[route]}><PublicHeaderProvider><AnchorNavigationProvider><div className="sarsa-site"><SiteHeader/><SiteSkip/><main id="page-content" tabIndex={-1}>{page}</main><SiteFooter/></div></AnchorNavigationProvider></PublicHeaderProvider></MemoryRouter>));await settle();}
const click=element=>act(async()=>element.click());
beforeEach(()=>{
 globalThis.IS_REACT_ACT_ENVIRONMENT=true;state.enabled=true;state.verified=true;Object.assign(state.flow,{started:false,busy:false,blocked:false,retry:null,waiting:0,receipt:null,error:''});
 media=new EventTarget();media.matches=false;vi.stubGlobal('matchMedia',()=>media);vi.stubGlobal('IntersectionObserver',class{observe(){}disconnect(){}});resizes=[];vi.stubGlobal('ResizeObserver',class{constructor(fn){resizes.push(fn);}observe(){}disconnect(){}});window.scrollTo=vi.fn();vi.stubGlobal('requestAnimationFrame',fn=>setTimeout(()=>fn(performance.now()+300),0));vi.stubGlobal('cancelAnimationFrame',clearTimeout);
 host=document.createElement('div');document.body.append(host);root=createRoot(host);
});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.unstubAllGlobals();vi.restoreAllMocks();});
test.each([['Home',<Home/>,8],['About',<About/>,0],['Services',<Services/>,0],['Contact',<ContactPage/>,4]])('%s has one shared frame and clear service actions',async(label,page,faq)=>{
 await render(page);expect(host.querySelectorAll('.sarsa-header')).toHaveLength(1);expect(host.querySelectorAll('.sarsa-footer')).toHaveLength(1);expect(host.querySelectorAll('h1')).toHaveLength(1);expect(host.querySelectorAll('details')).toHaveLength(faq);expect(host.textContent).not.toContain('Pause background');expect(host.querySelector('a[href="/services"]')).not.toBeNull();
 if(label==='Home'||label==='Services'||label==='About')for(const id of ['kundli-matching','kundli-prediction','vastu-consultation','numerology']){expect(host.querySelector(`a[href="/services/${id}"]`)).not.toBeNull();expect(host.querySelector(`a[href="/booking?service=${id}"]`)).not.toBeNull();}
});
test.each(['kundli-matching','vastu-consultation','numerology','kundli-prediction','unknown'])('service route %s retains its destination and useful text',async(id)=>{
 await render(<Routes><Route path="/services/:serviceId" element={<ServiceDetail/>}/><Route path="/services" element={<Services/>}/></Routes>,'/services/'+id);
 if(id==='unknown')expect(host.textContent).toContain('Explore our services');else{expect(host.querySelector(`a[href="/booking?service=${id}"]`)).not.toBeNull();expect(host.querySelectorAll('details')).toHaveLength(3);}
});
test('Kundli Prediction retains birth chart, Mahadasha and transits',async()=>{await render(<KundliPrediction/>);for(const text of ['Your birth chart','Mahadasha','transits'])expect(host.textContent).toContain(text);});
test.each([true,false])('policy truths and map privacy are aligned with booking %s',async(enabled)=>{
 state.enabled=enabled;for(const policy of ['privacy','terms','booking-policy']){await render(<PolicyPage policy={policy}/>);if(policy==='privacy')expect(host.textContent).toContain('Loading or using the map contacts Google.');if(enabled&&['privacy','terms'].includes(policy))expect(host.textContent).toContain('when the email-code check is enabled');}
});
test.each([true,false])('unavailable state %s replaces booking instructions without affecting enquiries',async(verified)=>{
 state.enabled=false;state.verified=verified;await render(<Home/>);expect(host.textContent).toContain(verified?'Online booking is currently unavailable':'Booking availability could not be confirmed');expect(host.textContent).toContain('सेवा समझें');expect(host.querySelector('a[href="/booking"]')).toBeNull();
});
test('phone disclosure Escape, outside click, route action and resize keep reachable focus',async()=>{
 await render(<Home/>);const trigger=host.querySelector('.sarsa-menu-trigger');await click(trigger);expect(trigger.getAttribute('aria-expanded')).toBe('true');await act(async()=>document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'})));expect(document.activeElement).toBe(trigger);
 await click(trigger);await act(async()=>document.body.dispatchEvent(new Event('pointerdown',{bubbles:true})));expect(trigger.getAttribute('aria-expanded')).toBe('false');await click(trigger);const link=host.querySelector('#sarsa-phone-menu a[href="/services"]');link.focus();media.matches=true;await act(async()=>media.dispatchEvent(new Event('change')));expect(document.activeElement.getAttribute('href')).toBe('/services');await click(trigger);await click(host.querySelector('#sarsa-phone-menu a[href="/contact"]'));expect(trigger.getAttribute('aria-expanded')).toBe('false');resizes[0]();
});
test('Contact topic is consumed once; a busy or verified draft does not change or replay',async()=>{
 await render(<ContactPage/>,'/contact');await click([...host.querySelectorAll('a')].find(n=>n.textContent.includes('Ask about your booking')));expect(host.querySelector('#topic').value).toBe('Existing booking');
 state.flow.busy=true;await render(<ContactPage/>,'/contact');await click([...host.querySelectorAll('a')].find(n=>n.textContent.includes('Write your question')));expect(host.querySelector('#topic').value).toBe('Existing booking');state.flow.busy=false;await render(<ContactPage/>,'/contact');expect(host.querySelector('#topic').value).toBe('Existing booking');
});
test('Contact anchor resolves the current verification phase and superseding result',async()=>{
 state.flow.started=true;state.flow.receipt={state:'awaiting_verification',sends_remaining:1,verification_delivery:'accepted'};await render(<ContactPage/>,'/contact');await click([...host.querySelectorAll('a')].find(n=>n.textContent.includes('Ask a question')));await new Promise(r=>setTimeout(r,30));expect(document.activeElement.id).toBe('code');state.flow.receipt={state:'received',request_id:'synthetic'};await render(<ContactPage/>,'/contact');expect(document.activeElement.id).toBe('outcome');
});
test('back to top hysteresis respects editing and returns focus to the opening heading',async()=>{
 await render(<ContactPage/>,'/contact');Object.defineProperty(window,'scrollY',{value:700,writable:true,configurable:true});await act(async()=>window.dispatchEvent(new Event('scroll')));const button=host.querySelector('.back-top');expect(button.hidden).toBe(false);await act(async()=>host.querySelector('#visitor-name').focus());expect(button.hidden).toBe(true);await act(async()=>host.querySelector('h1').focus());expect(button.hidden).toBe(false);await click(button);await new Promise(r=>setTimeout(r,30));expect(document.activeElement.tagName).toBe('H1');
 window.scrollY=0;await act(async()=>window.dispatchEvent(new Event('scroll')));expect(button.hidden).toBe(true);
});
