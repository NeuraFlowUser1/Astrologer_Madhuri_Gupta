import React,{act,useEffect} from 'react';
import {createRoot} from 'react-dom/client';
import {beforeEach,afterEach,test,expect,vi} from 'vitest';
const model=vi.hoisted(()=>({snapshot:{},listeners:new Set(),bookingMounts:0,header:null}));
vi.mock('../../src/site/BookingProduct.jsx',async()=>{
 const React=await import('react'),Router=await import('react-router-dom'),{createReactBindings}=await import('../../../appointment-system/browser/react-bindings.mjs'),{surfaces}=await import('../../../appointment-settings/project.json');
 return createReactBindings(React,Router,{surfaces,state:{subscribe:fn=>{model.listeners.add(fn);return()=>model.listeners.delete(fn);},getSnapshot:()=>model.snapshot,getServerSnapshot:()=>model.snapshot,start:()=>()=>{},refresh:async()=>{}}});
});
vi.mock('../../src/pages/Home.jsx',()=>({default:()=> <h1>Home</h1>}));
vi.mock('../../src/pages/About.jsx',()=>({default:()=> <h1>About</h1>}));
vi.mock('../../src/pages/Services.jsx',()=>({default:()=> <h1>Services</h1>}));
vi.mock('../../src/pages/ContactPage.jsx',()=>({default:()=> <h1>Contact</h1>}));
vi.mock('../../src/pages/ServiceDetail.jsx',()=>({default:()=> <h1>Service</h1>}));
vi.mock('../../src/pages/KundliPrediction.jsx',()=>({default:()=> <h1>Prediction</h1>}));
vi.mock('../../src/pages/PolicyPage.jsx',()=>({default:()=> <h1>Policy</h1>}));
vi.mock('../../src/pages/BookingReceipt.jsx',()=>({default:()=> <h1>Receipt</h1>}));
vi.mock('../../src/pages/BookingAccess.jsx',()=>({default:()=> <h1>Access</h1>}));
vi.mock('../../src/pages/Booking.jsx',()=>({default:({headerRef})=>{model.header=headerRef;useEffect(()=>{model.bookingMounts++;},[]);return <><h1>Booking</h1><input aria-label="Draft" defaultValue=""/></>;}}));
import App from '../../src/App.jsx';
import {titleFor} from '../../src/site/page-metadata.mjs';
let root,host;
async function flush(){await act(async()=>{for(let i=0;i<10;i++)await new Promise(resolve=>setTimeout(resolve,0));});}
async function go(path){await act(async()=>{window.history.pushState({},'',path);window.dispatchEvent(new PopStateEvent('popstate'));});await flush();}
async function state(value){await act(async()=>{model.snapshot={...model.snapshot,...value};model.listeners.forEach(fn=>fn());});}
beforeEach(async()=>{
 globalThis.IS_REACT_ACT_ENVIRONMENT=true;model.snapshot={enabled:true,verified:true,checking:false,retained_on_epoch:'synthetic'};model.listeners.clear();model.bookingMounts=0;window.history.replaceState({},'','/');
 document.head.innerHTML='<meta name="title"><meta name="description"><meta name="robots"><meta property="og:title"><meta property="og:description"><meta property="og:url"><meta name="twitter:title"><meta name="twitter:description"><meta name="twitter:url"><link rel="canonical">';
 window.scrollTo=vi.fn();vi.stubGlobal('matchMedia',()=>({matches:true,addEventListener:vi.fn(),removeEventListener:vi.fn()}));vi.stubGlobal('ResizeObserver',class{observe(){}disconnect(){}});vi.stubGlobal('IntersectionObserver',class{observe(){}disconnect(){}});
 host=document.createElement('div');document.body.append(host);root=createRoot(host);await act(async()=>root.render(<App/>));await flush();
});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.restoreAllMocks();vi.unstubAllGlobals();});
test('every public route has the same persistent frame and metadata, while receipt/help remain noindex',async()=>{
 const header=host.querySelector('.sarsa-header'),footer=host.querySelector('.sarsa-footer');
 for(const path of ['/about','/services','/services/kundli-prediction','/services/numerology','/contact','/booking','/privacy','/terms','/booking-policy','/booking/receipt','/booking-help','/missing']){
  await go(path);expect(host.querySelector('.sarsa-header')).toBe(header);expect(host.querySelector('.sarsa-footer')).toBe(footer);expect(document.title).toBe(titleFor(path));expect(host.querySelectorAll('.sarsa-header')).toHaveLength(1);
 }
 await go('/testimonials');expect(window.location.pathname).toBe('/about');
});
test('shared frame updates preserve the booking input and the existing retention/unmount rules',async()=>{
 await go('/booking');const input=host.querySelector('input');input.value='Saved draft';const header=model.header.current;expect(header).toBe(host.querySelector('.sarsa-header'));expect(header.closest('main')).toBeNull();expect(model.bookingMounts).toBe(1);
 await state({checking:true});expect(host.querySelector('input')).toBe(input);await state({enabled:false,verified:false,checking:false});expect(host.querySelector('input')).toBe(input);expect(input.closest('[hidden]').hasAttribute('inert')).toBe(true);
 await state({enabled:true,verified:true});expect(input.value).toBe('Saved draft');await state({enabled:false,retained_on_epoch:null});expect(host.querySelector('input')).toBeNull();await state({enabled:true,verified:true,retained_on_epoch:'new'});expect(model.bookingMounts).toBe(2);
});
test('OFF metadata/actions and policy routes fail closed without losing Services or Contact',async()=>{
 await state({enabled:false,verified:true,retained_on_epoch:null});for(const path of ['/','/services','/contact','/booking-policy']){await go(path);expect(host.querySelector('a[href="/booking"]')).toBeNull();expect(host.querySelector('a[href="/services"]')).not.toBeNull();expect(document.querySelector('meta[name="description"]').content).not.toBe('');}
 expect(host.querySelector('main h1').textContent).toBe('Page not found');document.head.replaceChildren();await go('/unknown');expect(document.title).toBe(titleFor('/unknown'));
});
