import {beforeEach,afterEach,test,expect,vi} from 'vitest';
import {mountBookingLayout} from '../../src/booking/booking-layout.mjs';
let media,frames,intersections,resizes,time;
const box=(height=80,top=300)=>({height,top});
function advance(now){time=now;const active=[...frames.values()];frames.clear();active.forEach(fn=>fn(now));}
beforeEach(()=>{
 vi.useFakeTimers();time=0;vi.spyOn(performance,'now').mockImplementation(()=>time);frames=new Map();let id=0;
 vi.stubGlobal('requestAnimationFrame',fn=>{frames.set(++id,fn);return id;});vi.stubGlobal('cancelAnimationFrame',i=>frames.delete(i));
 media=new EventTarget();media.matches=false;vi.stubGlobal('matchMedia',()=>media);
 window.scrollTo=vi.fn();Object.defineProperty(window,'scrollY',{value:100,writable:true,configurable:true});Object.defineProperty(window,'innerWidth',{value:1440,writable:true,configurable:true});Object.defineProperty(document.documentElement,'scrollHeight',{value:2000,configurable:true});Object.defineProperty(document,'hidden',{value:false,writable:true,configurable:true});
 intersections=[];resizes=[];
 vi.stubGlobal('IntersectionObserver',class{constructor(fn,options){this.fn=fn;this.options=options;this.observe=vi.fn();this.disconnect=vi.fn();intersections.push(this);}});
 vi.stubGlobal('ResizeObserver',class{constructor(fn){this.fn=fn;this.observe=vi.fn();this.disconnect=vi.fn();resizes.push(this);}});
});
afterEach(()=>{document.body.replaceChildren();vi.restoreAllMocks();vi.unstubAllGlobals();vi.useRealTimers();});
test('booking adapter validates connections and observes only changed measurements',()=>{
 const log=vi.spyOn(console,'error').mockImplementation(()=>{});const invalid=mountBookingLayout(null,vi.fn());invalid.go('service');invalid.dispose();expect(log).toHaveBeenCalledOnce();
 const root=document.createElement('div');root.innerHTML='<nav class="journey-nav"></nav>'+['service','appointment','details','review'].map(id=>`<section id="${id}"><h2 tabindex="-1">${id}</h2></section>`).join('');document.body.append(root);const header=document.createElement('header');document.body.append(header);let height=80;header.getBoundingClientRect=()=>box(height);root.querySelector('nav').getBoundingClientRect=()=>box(60);root.querySelectorAll('section').forEach(n=>n.getBoundingClientRect=()=>box(200,500));const change=vi.fn();const layout=mountBookingLayout(root,change,{headerBar:header});resizes[0].fn();expect(intersections).toHaveLength(1);intersections[0].fn([{target:root.querySelector('#details'),isIntersecting:true}]);expect(change).toHaveBeenLastCalledWith('details');layout.go('missing');layout.go('appointment');advance(220);expect(document.activeElement.textContent).toBe('appointment');height=90;resizes[0].fn();expect(intersections).toHaveLength(2);media.matches=true;window.innerWidth=390;layout.go('review');expect(window.scrollTo).toHaveBeenLastCalledWith({top:434,behavior:'instant'});layout.dispose();layout.go('details');expect(frames.size).toBe(0);
});
test.each(['wheel','touchstart','pointerdown','resize','keydown','input-tab','hidden','preference','detach'])('booking step movement yields to %s without stale focus',event=>{
 const root=document.createElement('div');root.innerHTML='<nav class="journey-nav"></nav>'+['service','appointment','details','review'].map(id=>`<section id="${id}"><h2 tabindex="-1">${id}</h2></section>`).join('');document.body.append(root);
 const header=document.createElement('header');document.body.append(header);header.getBoundingClientRect=()=>box(80);root.querySelector('nav').getBoundingClientRect=()=>box(60);root.querySelectorAll('section').forEach(n=>n.getBoundingClientRect=()=>box(200,500));
 const layout=mountBookingLayout(root,vi.fn(),{headerBar:header});layout.go('appointment');advance(100);expect(window.scrollTo).toHaveBeenCalledOnce();window.scrollTo.mockClear();
 if(event==='hidden'){document.hidden=true;document.dispatchEvent(new Event('visibilitychange'));}
 else if(event==='preference')media.dispatchEvent(new Event('change'));
 else if(event==='detach')root.remove();
 else if(event==='input-tab'){const input=document.createElement('input');root.append(input);input.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',bubbles:true}));}
 else window.dispatchEvent(event==='keydown'?new KeyboardEvent('keydown',{key:'Tab'}):new Event(event));
 advance(300);expect(window.scrollTo).not.toHaveBeenCalled();expect(document.activeElement.textContent).not.toBe('appointment');layout.dispose();resizes.at(-1).fn();
});
test('booking observation preserves the current step when nothing is visible and typing preserves movement',()=>{
 const root=document.createElement('div');root.innerHTML='<nav class="journey-nav"></nav><input>'+['service','appointment','details','review'].map(id=>`<section id="${id}"><h2 tabindex="-1">${id}</h2></section>`).join('');document.body.append(root);const header=document.createElement('header');document.body.append(header);header.getBoundingClientRect=()=>box(80);root.querySelector('nav').getBoundingClientRect=()=>box(60);root.querySelectorAll('section').forEach(n=>n.getBoundingClientRect=()=>box(200,500));const onStep=vi.fn();const layout=mountBookingLayout(root,onStep,{headerBar:header});intersections.at(-1).fn([{target:root.querySelector('#details'),isIntersecting:false}]);expect(onStep).not.toHaveBeenCalled();layout.go('details');root.querySelector('input').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true}));window.dispatchEvent(new KeyboardEvent('keydown',{key:'a'}));document.dispatchEvent(new Event('visibilitychange'));advance(220);expect(document.activeElement.textContent).toBe('details');layout.dispose();
});
