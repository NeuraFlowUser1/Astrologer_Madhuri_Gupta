import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {MemoryRouter,useLocation} from 'react-router-dom';
import {beforeEach,afterEach,test,expect,vi} from 'vitest';
const model=vi.hoisted(()=>({snapshot:{},listeners:new Set(),location:null}));
vi.mock('../../src/site/BookingProduct.jsx',async()=>{
 const React=await import('react'),Router=await import('react-router-dom');
 const {createReactBindings}=await import('../../../appointment-system/browser/react-bindings.mjs');
 const {surfaces}=await import('../../../appointment-settings/project.json');
 return createReactBindings(React,Router,{surfaces,state:{subscribe:fn=>{model.listeners.add(fn);return()=>model.listeners.delete(fn);},getSnapshot:()=>model.snapshot,getServerSnapshot:()=>model.snapshot,start:()=>()=>{},setProfile:()=>{},refresh:async()=>{}}});
});
import Home from '../../src/pages/Home.jsx';
import About from '../../src/pages/About.jsx';
import {SiteHeader,SiteFooter} from '../../src/site/SiteFrame.jsx';
import {mountHeroBand} from '../../src/site/hero-band-motion.mjs';
import {mountAboutLayout} from '../../src/site/about-layout.mjs';
let root,host;
function Recorder(){const location=useLocation();model.location=location;React.useLayoutEffect(()=>{window.history.replaceState({},'',location.pathname+location.search);},[location]);return null;}
async function render(Page,path){await act(async()=>root.render(<MemoryRouter initialEntries={[path]}><SiteHeader/><Page/><SiteFooter/><Recorder/></MemoryRouter>));}
async function click(node,extra={}){await act(async()=>node.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,button:0,...extra})));}
beforeEach(()=>{
 globalThis.IS_REACT_ACT_ENVIRONMENT=true;document.title='Shell owns page identity';model.snapshot={enabled:true,verified:true,checking:false,retained_on_epoch:'test-only'};model.listeners.clear();
 host=document.createElement('div');document.body.append(host);root=createRoot(host);
 vi.stubGlobal('matchMedia',()=>({matches:true,addEventListener:vi.fn(),removeEventListener:vi.fn()}));
 vi.stubGlobal('ResizeObserver',class{observe(){}disconnect(){}});
 vi.stubGlobal('IntersectionObserver',class{observe(){}unobserve(){}disconnect(){}});
 Object.defineProperty(document,'fonts',{value:{ready:Promise.resolve()},configurable:true});
});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.restoreAllMocks();vi.unstubAllGlobals();delete document.fonts;});

test.each([[Home,'/','Sarsa Jyotish Sansthan'],[About,'/about','Madhuri Gupta']])('approved hero has one meaningful title and all original lower content, in both booking modes',async(Page,path,title)=>{
 await render(Page,path);expect(host.querySelectorAll('h1')).toHaveLength(1);expect(host.querySelector('h1').textContent).toBe(title);expect(document.title).toBe('Shell owns page identity');
 expect(host.querySelector('[data-hero-band]').style.opacity).toBe('1');expect(host.textContent).toContain('15+');expect(host.querySelector('[data-motion-fallback]')).toBeNull();
 const logo=host.querySelector('.sarsa-header img');expect(logo.getAttribute('src')).toBe('/media/sarsa-kundli-lotus-logo-128.png');expect(logo.getAttribute('alt')).toBe('');expect(host.querySelector('.brand-copy').textContent).toBe('SarsaJYOTISH SANSTHAN');
 expect(host.querySelectorAll('.sarsa-header nav a')).toHaveLength(4);expect(host.querySelector('a[href="/testimonials"]')).not.toBeNull();
 if(path==='/'){
  expect(host.querySelector('.hero-byline').textContent).toBe('by Madhuri Gupta');expect(host.querySelector('.hero-question').textContent).toContain('Let’s look at your kundli.');
  expect(host.querySelectorAll('.service-choices a')).toHaveLength(5);expect(host.querySelectorAll('.service')).toHaveLength(5);expect(host.querySelectorAll('#questions details')).toHaveLength(9);
  expect(host.querySelector('.hero-bottom [lang=hi]')).not.toBeNull();expect(host.querySelector('.hero-meet').getAttribute('data-public-scroll')).not.toBeNull();
 }else{
  expect(host.textContent).toContain('Shri Vedang Jyotish Sansthan');expect(host.textContent).toContain('Yogrishi Astro Research Institute');expect(host.textContent).toContain('Bhrigu Nandi Nadi Astrology');
  expect(host.querySelectorAll('[data-enter]')).toHaveLength(4);expect(host.querySelectorAll('.service-row')).toHaveLength(5);expect(host.querySelectorAll('#portrait,.portrait-detail img')).toHaveLength(2);
  expect(host.querySelector('.curtain-left').getAttribute('aria-hidden')).toBe('true');expect(host.querySelector('[data-certificate],.certificate-gallery')).toBeNull();
 }
 const booking=host.querySelector('.hero-action[href="/booking"]');expect(booking).not.toBeNull();
 await click(booking);expect(model.location.pathname).toBe('/booking');
 await act(async()=>{model.snapshot={enabled:false,verified:true,checking:false,retained_on_epoch:null};model.listeners.forEach(fn=>fn());});
 expect(host.querySelector('a[href^="/booking"]')).toBeNull();expect(host.querySelector('.hero-action[href="/contact"]')).not.toBeNull();
 expect(host.querySelector('[data-hero-band]').textContent).toContain(path==='/'?'Prashna Kundali':'Jyotish Acharya');
});

test('Home keeps both question/Meet actions and five service destinations, including modified-click behaviour',async()=>{
 await render(Home,'/');const services=[...host.querySelectorAll('.service-choices a')];
 expect(services.map(a=>a.getAttribute('href'))).toEqual(['kundli-matching','kundli-prediction','vastu-consultation','numerology','prashna-kundali'].map(id=>'/services/'+id));
 await click(services[4],{ctrlKey:true});expect(model.location.pathname).toBe('/');await click(services[4]);expect(model.location.pathname).toBe('/services/prashna-kundali');
 await click(host.querySelector('.hero-action.secondary'));expect(model.location.pathname).toBe('/contact');
});

test('retained Home actions honour admission, prevent double navigation and keep ordinary anchor clicks',async()=>{
 await render(Home,'/');await click(host.querySelector('.hero-question'));expect(model.location.pathname).toBe('/');
 const read=host.querySelector('a[href="/about"]');
 await act(async()=>{const event=new MouseEvent('click',{bubbles:true,cancelable:true,button:0});event.preventDefault();read.dispatchEvent(event);});expect(model.location.pathname).toBe('/');
 for(const extra of [{ctrlKey:true},{metaKey:true},{shiftKey:true},{button:1}]){await click(read,extra);expect(model.location.pathname).toBe('/');}
 await click(read);expect(model.location.pathname).toBe('/about');
 await click(host.querySelector('.hero-meet'));expect(model.location.pathname).toBe('/about');
 await click(host.querySelector('[data-contact]'));expect(model.location.pathname).toBe('/contact');
 await click(host.querySelector('#enquire'));expect(model.location.pathname).toBe('/booking');
});

test('retained About invitation still opens booking and contact without affecting non-action text',async()=>{
 await render(About,'/about');await click(host.querySelector('h1'));expect(model.location.pathname).toBe('/about');
 await click(host.querySelector('[data-book]'));expect(model.location.pathname).toBe('/booking');
 await click(host.querySelector('#contact'));expect(model.location.pathname).toBe('/contact');
});

test('attached bands follow the incumbent clock, settle immediately for reduced motion and ignore stale notifications after cleanup',async()=>{
 const area=document.createElement('div');area.innerHTML='<section data-motion-progress="0"><div data-hero-band></div></section>';const scene=area.firstChild,band=scene.firstChild;
 const stop=mountHeroBand(area,'section');expect(band.style.opacity).toBe('0');
 scene.dataset.motionProgress='.89';await Promise.resolve();expect(Number(band.style.opacity)).toBeCloseTo(.5,8);
 scene.dataset.motionProgress='1.000';await Promise.resolve();expect(band.style.opacity).toBe('1');
 scene.dataset.motionProgress='0';stop();await Promise.resolve();expect(band.style.opacity).toBe('');
 delete scene.dataset.motionProgress;const missingClock=mountHeroBand(area,'section');expect(band.style.opacity).toBe('1');missingClock();
 vi.stubGlobal('MutationObserver',undefined);const unsupported=mountHeroBand(area,'section');expect(band.style.opacity).toBe('1');unsupported();expect(band.style.opacity).toBe('');
 let notify;vi.stubGlobal('MutationObserver',class{constructor(fn){notify=fn;}observe(){}disconnect(){}});const delayed=mountHeroBand(area,'section');delayed();notify();expect(band.style.opacity).toBe('');
});

test('About offsets use actual band layout height and preserve row compensation through resize and cleanup',async()=>{
 const area=document.createElement('div');area.innerHTML='<div data-hero-band></div><div class="consultation-grid"><div><p>Intro</p></div><div class="service-list"><div class="service-row" data-service-id="kundli-prediction"><div class="row-actions" style="margin-top:12px"></div></div></div></div>';
 const band=area.firstChild,list=area.querySelector('.service-list'),row=area.querySelector('.service-row'),intro=area.querySelector('.consultation-grid>div'),actions=area.querySelector('.row-actions');
 let height=138;Object.defineProperty(band,'offsetHeight',{get:()=>height});
 const rect=(h,top=0)=>({height:h,top,bottom:top+h});list.getBoundingClientRect=()=>rect(156);row.getBoundingClientRect=()=>rect(156);intro.getBoundingClientRect=()=>rect(200);intro.firstChild.getBoundingClientRect=()=>rect(60);actions.getBoundingClientRect=()=>rect(44);
 const stop=mountAboutLayout(area);expect(area.style.getPropertyValue('--about-hero-band-growth')).toBe('138px');expect(area.style.getPropertyValue('--about-row-growth')).toBe('56px');
 height=387;window.dispatchEvent(new Event('resize'));expect(area.style.getPropertyValue('--about-hero-band-growth-40')).toBe('154.8px');expect(area.style.getPropertyValue('--about-hero-band-growth-44')).toBe('170.28px');
 stop();await Promise.resolve();expect(area.style.cssText).toBe('');
});
