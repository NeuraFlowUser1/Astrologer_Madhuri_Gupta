import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {beforeEach,afterEach,test,expect,vi} from 'vitest';
import {legacyDestination,migrateLegacyLocation} from '../../src/site/routes.mjs';
import {pages,origin,titleFor} from '../../src/site/page-metadata.mjs';
import {productState} from '../../src/site/product-state.mjs';
vi.mock('../../src/pages/Booking.jsx',()=>({default:()=> <h1>Booking form integration</h1>}));
vi.mock('../../src/pages/BookingReceipt.jsx',()=>({default:()=> <h1>Receipt integration</h1>}));
vi.mock('../../src/pages/BookingAccess.jsx',()=>({default:()=> <h1>Receipt help integration</h1>}));
import App from '../../src/App.jsx';
let root,host;
beforeEach(()=>{globalThis.IS_REACT_ACT_ENVIRONMENT=true;vi.stubGlobal('matchMedia',()=>({matches:true,addEventListener(){},removeEventListener(){}}));vi.stubGlobal('ResizeObserver',class{observe(){}disconnect(){}});vi.stubGlobal('IntersectionObserver',class{observe(){}disconnect(){}});window.scrollTo=vi.fn();vi.stubGlobal('fetch',vi.fn(async()=>new Response(JSON.stringify({enabled:true,activation_epoch:'11111111-1111-4111-8111-111111111111'}),{status:200,headers:{'content-type':'application/json'}})));host=document.createElement('div');document.body.append(host);root=createRoot(host);document.head.innerHTML='<meta name="title"><meta name="description"><meta name="robots"><meta property="og:title"><meta property="og:description"><meta property="og:url"><meta name="twitter:title"><meta name="twitter:description"><meta name="twitter:url"><link rel="canonical">';});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();productState.invalidate();vi.unstubAllGlobals();vi.restoreAllMocks();});
async function render(path,enabled=true){window.history.replaceState(null,'',path);fetch.mockImplementation(async()=>new Response(JSON.stringify({enabled,activation_epoch:'11111111-1111-4111-1111-111111111111'}),{status:200,headers:{'content-type':'application/json'}}));await productState.refresh({force:true});await act(async()=>{root.render(<App/>);});for(let i=0;i<100;i++){await act(async()=>new Promise(r=>setTimeout(r,5)));if(host.querySelector('h1')&&!host.querySelector('[role=status]'))break;}}
test.each(['/','/about','/services','/services/numerology','/services/kundli-prediction','/contact','/privacy','/terms','/booking-policy','/booking','/booking/receipt','/booking-help','/missing','/testimonials'])('route %s has a shared frame, path-only canonical and correct indexing',async path=>{
 await render(path);expect(host.querySelectorAll('.sarsa-header')).toHaveLength(1);expect(host.querySelectorAll('.sarsa-footer')).toHaveLength(1);expect(host.querySelector('h1')).not.toBeNull();expect(document.querySelector('link[rel=canonical]').href).toBe(origin+location.pathname);expect(document.title).toBe(titleFor(location.pathname));if(!pages[location.pathname])expect(document.querySelector('meta[name=robots]').content).toBe('noindex');
});
test.each(['/','/services','/contact','/about','/booking','/booking-policy','/missing'])('OFF route %s does not expose a new booking',async path=>{
 await render(path,false);expect(host.textContent).not.toContain('Booking form integration');expect(host.querySelector('a[href="/booking"]')).toBeNull();if(['/booking','/booking-policy','/missing'].includes(path))expect(document.querySelector('meta[name=robots]').content).toBe('noindex');
});
test('metadata ignores private query and hash contents',async()=>{await render('/services?email=private#not-a-target');expect(document.querySelector('link[rel=canonical]').href).toBe(origin+'/services');expect(document.head.innerHTML).not.toContain('private');});
test('legacy route migration preserves allowlisted service only and rejects unsafe destinations',()=>{
 expect(legacyDestination('#/booking?service=numerology&secret=private#details')).toBe('/booking?service=numerology#details');expect(legacyDestination('#/booking?service=unknown')).toBe('/booking');
 for(const input of [undefined,null,0,{},[],'#//example.com','#/studio','#/api/callback?code=private','#/unknown','#approach','#/\\example.com','#/%2fexample.com','#/\\[invalid'])expect(legacyDestination(input)).toBeNull();
 expect(legacyDestination('#/contact?email=private#access_secret')).toBe('/contact');const replaceState=vi.fn(),history={state:{key:'saved'},replaceState};migrateLegacyLocation({pathname:'/',hash:'#/about#approach'},history);expect(replaceState).toHaveBeenCalledWith(history.state,'','/about#approach');replaceState.mockClear();migrateLegacyLocation({pathname:'/studio',hash:'#/about'},history);migrateLegacyLocation({pathname:'/',hash:'#bad'},history);expect(replaceState).not.toHaveBeenCalled();
});
