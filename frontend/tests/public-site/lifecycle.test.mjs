import {beforeEach,afterEach,test,expect,vi} from 'vitest';
import {moveToTarget,waitForTarget} from '../../src/site/anchor-navigation.mjs';
import {watchCardAttention} from '../../src/site/card-attention.mjs';
import {mountBookingLayout} from '../../src/booking/booking-layout.mjs';
let media,frames,intersections,resizes,time;
const box=(height=80,top=300)=>({height,top});
function target(){const node=document.createElement('h2');node.tabIndex=-1;node.id='target';document.body.append(node);node.getBoundingClientRect=()=>box(40);return node;}
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
test('anchor moves once with measured bar and focuses the intended heading',()=>{
 const node=target(),header=document.createElement('header');header.getBoundingClientRect=()=>box();const done=vi.fn();
 const dispose=moveToTarget({target:node,header,smooth:true,onDone:done});advance(130);expect(window.scrollTo).toHaveBeenCalledWith({top:275,behavior:'instant'});advance(260);expect(document.activeElement).toBe(node);expect(done).toHaveBeenCalledOnce();dispose();
});
test.each(['wheel','touchstart','pointerdown','resize','keydown','visibilitychange','preference','sarsa-form-focus'])('anchor cancellation by %s never restores focus later',event=>{
 const node=target();moveToTarget({target:node,smooth:true});
 if(event==='preference')media.dispatchEvent(new Event('change'));
 else if(event==='visibilitychange'){document.hidden=true;document.dispatchEvent(new Event(event));}
 else if(event==='sarsa-form-focus')document.dispatchEvent(new Event(event));
 else window.dispatchEvent(event==='keydown'?new KeyboardEvent(event,{key:'Tab'}):new Event(event));
 advance(300);expect(window.scrollTo).not.toHaveBeenCalled();expect(document.activeElement).not.toBe(node);
});
test('top, reduced motion, invalid target, detach and changed bar have bounded behaviour',()=>{
 media.matches=true;const node=target();moveToTarget({target:node,top:true});advance(1);expect(window.scrollTo).toHaveBeenLastCalledWith({top:0,behavior:'instant'});
 moveToTarget({target:null});advance(2);const header=document.createElement('header');let height=80;header.getBoundingClientRect=()=>box(height);moveToTarget({target:node,header,smooth:true});height=100;advance(4);expect(frames.size).toBe(0);
 moveToTarget({target:node});node.remove();advance(5);expect(frames.size).toBe(0);
});
test('typing and non-scroll keys do not cancel; phone gap and maximum scroll are respected',()=>{
 const node=target(),input=document.createElement('input');document.body.append(input);window.innerWidth=390;
 const dispose=moveToTarget({target:node,smooth:true});input.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true}));window.dispatchEvent(new KeyboardEvent('keydown',{key:'a'}));document.dispatchEvent(new Event('visibilitychange'));advance(300);expect(window.scrollTo).toHaveBeenLastCalledWith({top:384,behavior:'instant'});dispose();
 node.getBoundingClientRect=()=>box(80,9000);moveToTarget({target:node});advance(400);expect(window.scrollTo.mock.calls.at(-1)[0].top).toBe(2000-window.innerHeight);
});
test('lazy targets appear once; waiting cancellation and timeout leave no late scroll',async()=>{
 const run=vi.fn(()=>vi.fn());let cancel=waitForTarget('later',run);const node=target();node.id='later';await Promise.resolve();advance(1);expect(run).toHaveBeenCalledOnce();cancel();
 node.remove();cancel=waitForTarget('missing',run);window.dispatchEvent(new KeyboardEvent('keydown',{key:'a'}));document.dispatchEvent(new Event('visibilitychange'));window.dispatchEvent(new Event('wheel'));node.id='missing';document.body.append(node);await Promise.resolve();advance(2);expect(run).toHaveBeenCalledOnce();cancel();
 node.remove();waitForTarget('never',run,{timeout:10});vi.advanceTimersByTime(10);advance(3);expect(run).toHaveBeenCalledOnce();
});
test('a user action after a lazy target appears still cancels the queued handoff',async()=>{
 const run=vi.fn();waitForTarget('later',run);const node=target();node.id='later';await Promise.resolve();window.dispatchEvent(new Event('wheel'));advance(1);expect(run).not.toHaveBeenCalled();
 waitForTarget('later',run);node.remove();advance(2);expect(run).not.toHaveBeenCalled();
});
test('Tab from an editable field cancels both active scrolling and a waiting target',async()=>{
 const node=target(),input=document.createElement('input');document.body.append(input);moveToTarget({target:node,smooth:true});input.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',bubbles:true}));advance(300);expect(window.scrollTo).not.toHaveBeenCalled();expect(document.activeElement).not.toBe(node);
 node.remove();const run=vi.fn();waitForTarget('later',run);input.dispatchEvent(new KeyboardEvent('keydown',{key:'Tab',bubbles:true}));node.id='later';document.body.append(node);await Promise.resolve();advance(600);expect(run).not.toHaveBeenCalled();
});
test('service attention uses two distinct cards and ends within 2040ms',()=>{
 const root=document.createElement('div');root.innerHTML='<article class="service-card"></article><article class="service-card"></article><article class="service-card"></article>';document.body.append(root);const played={current:false};
 const dispose=watchCardAttention(root,{played,rng:()=>0});intersections[0].fn([{isIntersecting:false}]);expect(root.querySelector('.pulse')).toBeNull();intersections[0].fn([{isIntersecting:true}]);expect(root.children[0].classList.contains('pulse')).toBe(true);vi.advanceTimersByTime(1140);expect(root.children[1].classList.contains('pulse')).toBe(true);vi.advanceTimersByTime(900);expect(root.querySelector('.pulse')).toBeNull();expect(played.current).toBe(true);dispose();
});
test.each(['pointerdown','focusin','hidden','preference','dispose'])('service attention stops after %s and does not replay',event=>{
 const root=document.createElement('div');root.innerHTML='<article class="service-card"></article><article class="service-card"></article>';const played={current:false};const dispose=watchCardAttention(root,{played});intersections[0].fn([{isIntersecting:true}]);
 if(event==='hidden'){document.hidden=true;document.dispatchEvent(new Event('visibilitychange'));}else if(event==='preference'){media.matches=true;media.dispatchEvent(new Event('change'));}else if(event==='dispose')dispose();else root.dispatchEvent(new Event(event));
 vi.advanceTimersByTime(5000);expect(root.querySelector('.pulse')).toBeNull();dispose();
});
test('reduced, hidden, already played and one-card attention are finite',()=>{
 const root=document.createElement('div');root.innerHTML='<article class="service-card"></article>';media.matches=true;let played={current:false};watchCardAttention(root,{played})();expect(played.current).toBe(true);media.matches=false;document.hidden=true;watchCardAttention(root,{played:{current:false}})();document.hidden=false;watchCardAttention(root,{played})({});
 played={current:false};const dispose=watchCardAttention(root,{played});intersections.at(-1).fn([{isIntersecting:true}]);vi.advanceTimersByTime(1000);expect(root.querySelector('.pulse')).toBeNull();dispose();
});
test('missing optional motion observation leaves readable cards without setup work',()=>{
 expect(typeof watchCardAttention(null)).toBe('function');vi.stubGlobal('IntersectionObserver',undefined);const root=document.createElement('div');root.innerHTML='<article class="service-card">A service</article>';watchCardAttention(root,{played:{current:false}})();expect(root.textContent).toBe('A service');expect(frames.size).toBe(0);
 vi.stubGlobal('IntersectionObserver',class{constructor(){throw Error('Synthetic unavailable observation');}});const played={current:false};watchCardAttention(root,{played})();expect(played.current).toBe(true);expect(root.textContent).toBe('A service');
});
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
