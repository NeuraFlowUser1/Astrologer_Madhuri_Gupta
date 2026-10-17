import {test,expect,vi} from 'vitest';
import {resolve} from 'node:path';
import {heroStatic} from '../../scripts/hero-static.mjs';
const io=vi.hoisted(()=>({files:new Map(),calls:[]}));
vi.mock('node:fs',async importOriginal=>{
 const actual=await importOriginal();
 const readFileSync=(path,...args)=>io.files.has(path)?io.files.get(path):actual.readFileSync(path,...args);
 const writeFileSync=(path,value)=>io.files.set(path,value);
 return {...actual,readFileSync,writeFileSync,default:{...actual.default,readFileSync,writeFileSync}};
});
vi.mock('../../../appointment-system/tools/build/surfaces.mjs',()=>({writeSurfaceManifest:options=>({public_paths:options.publicPaths,booking_paths:options.bookingPaths})}));
vi.mock('../../../appointment-system/tools/build/page-modes.mjs',()=>({generateModes:options=>{
 io.calls.push(options);
 // Boundary double for the unchanged contained generator. The real build separately runs it.
 for(const mode of ['on','off'])for(const path of ['/','/about','/services']){
  const file=path==='/'?'index.html':path.slice(1)+'.html';
  io.files.set(resolve(options.dist,'__booking_display',mode,file),options.shell);
  if(mode==='off')io.files.set(resolve(options.dist,file),options.shell);
 }
}}));

test.each(['/','/about'])('script-free %s retains the same confirmed facts and honours both booking modes',path=>{
 for(const mode of ['on','off']){
  const host=document.createElement('div');host.innerHTML=heroStatic(path,mode).replace('<noscript data-sarsa-static>','').replace('</noscript>','');
  expect(host.querySelectorAll('h1')).toHaveLength(1);expect(host.querySelectorAll('a[href="/booking"]')).toHaveLength(mode==='on'?1:0);expect(host.querySelector('a[href="/contact"]')).not.toBeNull();
  expect(host.textContent).toContain('15+ years of experience');
  if(path==='/'){expect(host.querySelectorAll('[data-hero-band] li')).toHaveLength(5);expect(host.querySelector('a[href="/services/prashna-kundali"]')).not.toBeNull();}
  else for(const text of ['Jyotish Shastri','Jyotish Acharya','Shri Vedang Jyotish Sansthan','Bhrigu Nandi Nadi Astrology','Yogrishi Astro Research Institute'])expect(host.textContent).toContain(text);
 }
});
test('unrelated routes receive no extra reading page',()=>{expect(heroStatic('/services','on')).toBe('');});
test('the client build attaches one reading view per intended route/mode and is safe to repeat',async()=>{
 const dist=resolve(import.meta.dirname,'../../dist');io.files.set(resolve(dist,'index.html'),'<html><head><meta name="booking-display-mode" content="off"></head><body><noscript data-sarsa-static>stale old text</noscript><div id="root"></div></body></html>');
 await import('../../scripts/public-pages.mjs');
 for(const mode of ['on','off'])for(const file of ['index.html','about.html']){
  const html=io.files.get(resolve(dist,'__booking_display',mode,file));expect(html.match(/<noscript data-sarsa-static>/g)).toHaveLength(1);expect(html).not.toContain('stale old text');expect(html).toContain('<div id="root">');
 }
 expect(io.files.get(resolve(dist,'services.html'))).not.toContain('data-sarsa-static');
 const first=new Map(io.files);vi.resetModules();await import('../../scripts/public-pages.mjs');expect(io.files).toEqual(first);expect(io.calls).toHaveLength(2);
});
