import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {MemoryRouter,Routes,Route,useLocation} from 'react-router-dom';
import {beforeEach,afterEach,test,expect,vi} from 'vitest';
const model=vi.hoisted(()=>({snapshot:{},listeners:new Set(),location:null,scenes:[],cleanups:0}));
vi.mock('../../src/site/BookingProduct.jsx',async()=>{
 const React=await import('react'),Router=await import('react-router-dom');const {createReactBindings}=await import('../../../appointment-system/browser/react-bindings.mjs');const {surfaces}=await import('../../../appointment-settings/project.json');
 return createReactBindings(React,Router,{surfaces,state:{subscribe:fn=>{model.listeners.add(fn);return()=>model.listeners.delete(fn);},getSnapshot:()=>model.snapshot,getServerSnapshot:()=>model.snapshot,start:()=>()=>{},refresh:async()=>{}}});
});
vi.mock('../../src/site/scenes.mjs',()=>({mountScenes:(root,definitions)=>{model.scenes=definitions;definitions.forEach(d=>d.render(1));return()=>{model.cleanups++;};}}));
vi.mock('../../src/contact/motion.mjs',()=>({mountContactMotion:()=>()=>{}}));
vi.mock('../../src/contact/useEnquiry.jsx',()=>({useEnquiry:()=>({started:false,busy:false,blocked:false,retry:null,waiting:0,receipt:null})}));
import Home from '../../src/pages/Home.jsx';
import About from '../../src/pages/About.jsx';
import KundliPrediction from '../../src/pages/KundliPrediction.jsx';
import ContactPage from '../../src/pages/ContactPage.jsx';
import Services from '../../src/pages/Services.jsx';
import ServiceDetail from '../../src/pages/ServiceDetail.jsx';
import PolicyPage from '../../src/pages/PolicyPage.jsx';
import ServiceArtwork from '../../src/site/ServiceArtwork.jsx';
import {SiteHeader,SiteFooter} from '../../src/site/SiteFrame.jsx';
let host,root;
function Recorder(){model.location=useLocation();return null;}
const click=async(node,options={})=>act(async()=>node.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,button:0,detail:1,...options})));
const render=async(node,path='/')=>act(async()=>root.render(<MemoryRouter initialEntries={[path]}>{node}<Recorder/></MemoryRouter>));
const update=async(snapshot)=>act(async()=>{model.snapshot={...model.snapshot,...snapshot};model.listeners.forEach(fn=>fn());});
beforeEach(()=>{
 SVGElement.prototype.getTotalLength=()=>100;
 globalThis.IS_REACT_ACT_ENVIRONMENT=true;model.snapshot={enabled:true,verified:true,checking:false,retained_on_epoch:'synthetic'};model.listeners.clear();model.cleanups=0;
 host=document.createElement('div');document.body.append(host);root=createRoot(host);window.scrollTo=vi.fn();HTMLElement.prototype.scrollIntoView=vi.fn();
 vi.stubGlobal('matchMedia',query=>({matches:query.includes('reduce'),addEventListener:vi.fn(),removeEventListener:vi.fn()}));
 vi.stubGlobal('ResizeObserver',class{observe(){}disconnect(){}});vi.stubGlobal('IntersectionObserver',class{observe(){}disconnect(){}});
 Object.defineProperty(document,'fonts',{value:{ready:Promise.resolve()},configurable:true});
});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.restoreAllMocks();vi.unstubAllGlobals();delete document.fonts;delete HTMLElement.prototype.scrollIntoView;delete SVGElement.prototype.getTotalLength;});

test.each([[Home,'/','/booking'],[KundliPrediction,'/services/kundli-prediction','/booking?service=kundli-prediction']])('original page actions keep their routes and cannot bypass latest booking admission',async(Page,path,booking)=>{
 await render(<Page/>,path);await click(host.querySelector('h1'));expect(model.location.pathname).toBe(path);
 const paid=host.querySelector('a[href^="/booking"]');model.snapshot={...model.snapshot,checking:true};await click(paid);expect(model.location.pathname).toBe(path);
 model.snapshot={...model.snapshot,checking:false};await click(host.querySelector('#enquire'));expect(model.location.pathname+model.location.search).toBe(booking);
 await click(host.querySelector('[data-contact]'));expect(model.location.pathname).toBe('/contact');
 const link=host.querySelector('a[href="/services"],a[href="/about"]');await click(link,{ctrlKey:true});expect(model.location.pathname).toBe('/contact');await click(link);expect(['/about','/services']).toContain(model.location.pathname);
 await update({enabled:false,verified:true,retained_on_epoch:null});expect(host.querySelectorAll('#questions details').length).toBeGreaterThan(2);
});

test('About keeps four permanent row identities and selected service handoffs in both availability modes',async()=>{
 await render(<About/>,'/about');expect(host.querySelectorAll('.service-row')).toHaveLength(4);
 for(const [i,id] of ['kundli-prediction','kundli-matching','vastu-consultation','numerology'].entries()){
  const row=host.querySelectorAll('.service-row')[i];expect(row.querySelector('span').textContent).toBe('0'+(i+1));await click(row.querySelector('a'));expect(model.location.pathname).toBe('/services/'+id);await click(row.querySelectorAll('a')[1]);expect(model.location.pathname+model.location.search).toBe('/booking?service='+id);
 }
 await click(host.querySelector('h1'));await click(host.querySelector('[data-book]'));expect(model.location.pathname).toBe('/booking');await click(host.querySelector('#contact'));expect(model.location.pathname).toBe('/contact');
 await update({enabled:false,retained_on_epoch:null});expect(host.querySelectorAll('.row-identity b')).toHaveLength(4);expect(host.querySelectorAll('.row-actions a')).toHaveLength(4);expect(host.querySelector('[data-motion-fallback]')).toBeNull();
});

test.each([false,true])('About motion preserves all phases and row transforms with phone=%s',async(phone)=>{
 vi.stubGlobal('matchMedia',query=>({matches:query.includes('max-width')?phone:true,addEventListener:vi.fn(),removeEventListener:vi.fn()}));
 await render(<About/>,'/about');expect(model.scenes).toHaveLength(6);expect(model.scenes.map(d=>d.duration)).toEqual([7150,2437.5,2925,2925,2925,2925]);
 for(const p of [0,.15,.25,.4,.49,.6,.8,1])for(const scene of model.scenes)expect(()=>scene.render(p)).not.toThrow();
 const scene=model.scenes[4];scene.render(0);expect(host.querySelector('.row-identity span').style.transform).toBe('translateX(-35px)');expect(host.querySelector('.row-identity b').style.transform).toBe('rotate(-55deg) scale(0.65)');scene.render(1);expect(host.querySelector('.row-identity span').style.transform).toBe('translateX(0px)');expect(host.querySelector('.row-actions a').style.transform).toBe('');
});

test('Services uses real catalogue destinations and artwork, with one Explore action per card when OFF',async()=>{
 await render(<Services/>,'/services');expect(document.title).toBe('Services | Sarsa Jyotish Sansthan');expect(host.querySelectorAll('.directory-art')).toHaveLength(4);expect(host.querySelectorAll('.service-guide')).toHaveLength(2);
 for(const link of host.querySelectorAll('.service-actions a[href^="/booking"]')){await click(link);expect(model.location.search).toContain('service=');}
 await update({enabled:false,retained_on_epoch:null});expect(host.querySelectorAll('.service-actions a')).toHaveLength(4);expect(host.querySelector('a[href^="/booking"]')).toBeNull();await render(<ServiceArtwork id="unknown"/>);expect(host.querySelector('svg')).toBeNull();
});

test.each(['kundli-matching','vastu-consultation','numerology','unknown'])('detail %s keeps its four scenes or redirects an invalid ID',async(id)=>{
 await render(<Routes><Route path="/services/:serviceId" element={<ServiceDetail/>}/><Route path="/services" element={<h1>Services</h1>}/></Routes>,'/services/'+id);
 if(id==='unknown'){expect(model.location.pathname).toBe('/services');return;}
 expect(host.querySelectorAll('section')).toHaveLength(4);expect(host.querySelectorAll('.service-art [data-layer]')).toHaveLength(3);await click(host.querySelector('a[href^="/booking"]'));expect(model.location.search).toBe('?service='+id);
});

test('Contact retains topic/focus handoff, five stages and original plaque while adding a separate map and process',async()=>{
 await render(<ContactPage/>,'/contact');expect(host.querySelectorAll('.stage')).toHaveLength(5);expect(host.querySelector('.contact-location').closest('.stage')).toBeNull();expect(host.querySelector('.contact-booking-steps').closest('.stage')).toBeNull();
 await click(host.querySelector('h1'));await click(host.querySelector('[data-route="existing"]'));expect(host.querySelector('#topic').value).toBe('Existing booking');expect(document.activeElement.id).toBe('visitor-name');
 vi.stubGlobal('matchMedia',()=>({matches:false}));await click(host.querySelector('[data-route="question"]'));expect(host.querySelector('#topic').value).toBe('Before booking');await click(host.querySelector('[data-book]'));expect(model.location.pathname).toBe('/booking');
 expect(host.querySelector('address').textContent).toBe('8, Gailana Road, LIC Colony, Agra - 282007');expect(host.querySelector('.contact-location a').href).toBe('https://maps.app.goo.gl/CwQftW8iYfxAZFDo8');expect(host.querySelector('iframe').title).toContain('Google Maps');
 const arrow=host.querySelector('.weave-book-link');model.snapshot={...model.snapshot,checking:true};await click(arrow);model.snapshot={...model.snapshot,checking:false};await click(arrow);expect(model.location.pathname).toBe('/booking');
 await update({enabled:false,retained_on_epoch:null});expect(host.querySelectorAll('.stage')).toHaveLength(4);expect(host.querySelector('.contact-booking-steps')).toBeNull();expect(host.querySelector('iframe')).not.toBeNull();
});

test('the shared frame retains every destination, a single Top control, and capability-aware policy/access links',async()=>{
 const scrollerRef={current:{top:vi.fn()}},headerRef={current:null};await render(<><main id="page-content" tabIndex="-1"/><SiteHeader sticky headerRef={headerRef}/><SiteFooter home scrollerRef={scrollerRef}/></>);
 expect(headerRef.current.isConnected).toBe(true);expect(host.querySelectorAll('.sarsa-header')).toHaveLength(1);expect(host.querySelectorAll('nav[aria-label="Main navigation"] a')).toHaveLength(3);
 const button=host.querySelector('.sarsa-top');await click(button,{detail:0});expect(scrollerRef.current.top).toHaveBeenLastCalledWith(true);await click(button);expect(scrollerRef.current.top).toHaveBeenLastCalledWith(false);
 await update({enabled:false,retained_on_epoch:null});expect(host.querySelector('a[href="/booking-help"]')).toBeNull();expect(host.querySelector('a[href="/services"]')).not.toBeNull();scrollerRef.current=null;await click(button);
});
test.each(['privacy','terms','booking-policy'])('policy %s preserves its actual ON and OFF wording/related navigation',async(policy)=>{
 await render(<PolicyPage policy={policy}/>);expect(host.querySelector('h1')).not.toBeNull();await update({enabled:false});expect(host.querySelector('h1')).not.toBeNull();expect(host.querySelector('a[href="/booking-policy"]')).toBeNull();
});
