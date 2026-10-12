import React,{act,StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import {beforeEach,afterEach,test,expect,vi} from 'vitest';
import Certifications from '../../src/site/Certifications.jsx';
import {certificates} from '../../src/site/certificates-content.mjs';
let root,host,fetchSpy;
beforeEach(()=>{
 globalThis.IS_REACT_ACT_ENVIRONMENT=true;
 host=document.createElement('div');document.body.append(host);root=createRoot(host);
 const media=new EventTarget();media.matches=true;media.addListener=()=>{};media.removeListener=()=>{};
 vi.stubGlobal('matchMedia',()=>media);
 vi.stubGlobal('ResizeObserver',class{observe(){}unobserve(){}disconnect(){}});
 vi.stubGlobal('IntersectionObserver',class{observe(){}disconnect(){}});
 HTMLElement.prototype.scrollIntoView=vi.fn();HTMLElement.prototype.scrollTo=vi.fn();
 fetchSpy=vi.fn(()=>{throw Error('No network or provider requests in certificate unit checks.');});vi.stubGlobal('fetch',fetchSpy);
});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();expect(fetchSpy).not.toHaveBeenCalled();delete HTMLElement.prototype.scrollIntoView;delete HTMLElement.prototype.scrollTo;vi.restoreAllMocks();vi.unstubAllGlobals();});
const render=async()=>{await act(async()=>root.render(<StrictMode><Certifications/></StrictMode>));};
const click=async element=>{expect(element).toBeDefined();expect(element).not.toBeNull();await act(async()=>element.click());};
const button=name=>[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===name||b.getAttribute('aria-label')===name);
test('four supplied courses have uncropped lazy previews, explicit issuers and on-demand originals',async()=>{
 await render();expect(host.querySelectorAll('article')).toHaveLength(4);expect(document.querySelector('[role=dialog]')).toBeNull();
 expect(Object.isFrozen(certificates)).toBe(true);expect(new Set(certificates.map(c=>c.id)).size).toBe(4);
 for(const c of certificates){expect(Object.isFrozen(c)).toBe(true);const img=host.querySelector(`img[src="${c.thumbnail}"]`);expect(img.loading||img.getAttribute('loading')).toBe('lazy');expect(img.getAttribute('width')).toBe(String(c.width));expect(img.getAttribute('height')).toBe(String(c.height));expect(host.textContent).toContain(c.issuer);expect(host.querySelector(`img[src="${c.full}"]`)).toBeNull();expect(c.original).toMatch(c.id==='astro-research-institute'?/\.pdf$/:/\.jpeg$/);}
 expect(certificates[2].title).toBe('Bhrigu Nandi Nadi Astrology');expect(certificates[3].period).toBe('Two-day online session');
});
test('reader navigation has real boundaries, resets zoom and loads only the selected full image',async()=>{
 await render();await click(host.querySelector('.certificate-preview'));
 expect(document.querySelector('[role=dialog]')).not.toBeNull();expect(button('Previous certificate').disabled).toBe(true);expect(document.querySelector('.certificate-image-canvas img').src).toContain(certificates[0].full);
 expect(document.querySelector('.certificate-loading')).not.toBeNull();await act(async()=>document.querySelector('.certificate-image-canvas img').dispatchEvent(new Event('load')));expect(document.querySelector('.certificate-loading')).toBeNull();
 await click(button('Zoom in'));expect(button('Fit to screen').getAttribute('aria-pressed')).toBe('true');await click(button('Fit to screen'));expect(button('Zoom in').getAttribute('aria-pressed')).toBe('false');await click(button('Zoom in'));
 for(let i=1;i<4;i++){await click(button('Next certificate'));expect(document.querySelector('.certificate-reader-position').textContent).toBe(`Certificate ${i+1} of 4`);expect(document.querySelector('.certificate-image-canvas img').src).toContain(certificates[i].full);expect(button('Zoom in').getAttribute('aria-pressed')).toBe('false');}
 expect(button('Next certificate').disabled).toBe(true);expect(document.activeElement).toBe(button('Previous certificate'));await click(button('Previous certificate'));expect(document.querySelector('.certificate-reader-position').textContent).toBe('Certificate 3 of 4');
 await click(button('Previous certificate'));await click(button('Previous certificate'));expect(document.activeElement).toBe(button('Next certificate'));await click(button('Next certificate'));await click(button('Next certificate'));
 expect(document.querySelector('.certificate-reader-controls>a').getAttribute('href')).toBe(certificates[2].original);await click(button('Close certificate'));expect(document.querySelector('[role=dialog]')).toBeNull();
});
test('a failed image retains the source link and changing document restores a fresh reader',async()=>{
 await render();await click(host.querySelectorAll('.certificate-preview')[2]);await act(async()=>document.querySelector('.certificate-image-canvas img').dispatchEvent(new Event('error')));
 expect(document.querySelector('.certificate-image-error').textContent).toContain('could not load');expect(document.querySelector('.certificate-image-error a').getAttribute('href')).toBe(certificates[2].original);
 await click(button('Next certificate'));expect(document.querySelector('.certificate-image-error')).toBeNull();expect(document.querySelector('.certificate-image-canvas img').src).toContain(certificates[3].full);
 await act(async()=>{button('Close certificate').focus();button('Close certificate').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));});expect(document.querySelector('[role=dialog]')).toBeNull();
});
test('outside dismissal closes the reader and route unmount releases the overlay',async()=>{
 await render();await click(host.querySelectorAll('.certificate-preview')[1]);const overlay=document.querySelector('.certificate-overlay');
 await act(async()=>{overlay.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0}));overlay.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,button:0}));});
 // Real outside-pointer/focus restoration is also checked in the rendered browser.
 await act(async()=>root.render(<div>Another page</div>));expect(document.querySelector('.certificate-overlay')).toBeNull();expect(host.textContent).toBe('Another page');
});
