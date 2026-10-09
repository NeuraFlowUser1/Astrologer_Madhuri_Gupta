import {beforeEach,afterEach,test,expect,vi} from 'vitest';
import {mountBookingLayout} from '../../src/booking/booking-layout.mjs';
let root,header,media,fonts,resize,intersection;
const rect=(left,top,width,height)=>({left,top,width,height,right:left+width,bottom:top+height});
beforeEach(()=>{
 media=new EventTarget();media.matches=true;fonts=new EventTarget();Object.defineProperty(document,'fonts',{value:fonts,configurable:true});vi.stubGlobal('matchMedia',()=>media);
 vi.stubGlobal('ResizeObserver',class{constructor(fn){resize=fn;}observe(){}disconnect(){}});vi.stubGlobal('IntersectionObserver',class{constructor(fn){intersection=fn;}observe(){}disconnect(){}});
 Object.defineProperty(window,'innerWidth',{value:390,writable:true,configurable:true});Object.defineProperty(window,'innerHeight',{value:844,writable:true,configurable:true});Object.defineProperty(window,'scrollY',{value:0,writable:true,configurable:true});Object.defineProperty(document.documentElement,'scrollHeight',{value:4000,configurable:true});window.scrollTo=vi.fn();
 root=document.createElement('div');root.innerHTML='<nav class="journey-nav"><svg class="booking-step-connectors"><path/></svg>'+Array.from({length:4},()=>'<span class="step-medallion"></span>').join('')+'</nav>'+['service','appointment','details','review'].map(id=>`<section id="${id}"><h2 tabindex="-1">${id}</h2></section>`).join('');header=document.createElement('header');document.body.append(header,root);header.getBoundingClientRect=()=>rect(0,0,390,80);root.querySelector('nav').getBoundingClientRect=()=>rect(20,80,350,120);root.querySelectorAll('.step-medallion').forEach((node,i)=>{node.getBoundingClientRect=()=>rect(26+(i%2)*175,92+Math.floor(i/2)*56,34,34);});root.querySelectorAll('section').forEach((node,i)=>{node.getBoundingClientRect=()=>rect(20,220+i*500,350,480);});
});
afterEach(()=>{document.body.replaceChildren();vi.restoreAllMocks();vi.unstubAllGlobals();delete document.fonts;});
test.each(['missing','throws'])('missing observation (%s) still measures, tracks steps, moves once and cleans up',kind=>{
 vi.stubGlobal('ResizeObserver',kind==='missing'?undefined:class{constructor(){throw Error('synthetic unavailable');}});vi.stubGlobal('IntersectionObserver',kind==='missing'?undefined:class{constructor(){throw Error('synthetic unavailable');}});
 const onStep=vi.fn(),layout=mountBookingLayout(root,onStep,{headerBar:header});expect(root.style.getPropertyValue('--booking-header-height')).toBe('80px');expect(onStep).toHaveBeenLastCalledWith('service');
 header.getBoundingClientRect=()=>rect(0,0,390,96);fonts.dispatchEvent(new Event('loadingdone'));expect(root.style.getPropertyValue('--booking-header-height')).toBe('96px');root.querySelector('#appointment').getBoundingClientRect=()=>rect(20,230,350,480);window.dispatchEvent(new Event('scroll'));expect(onStep).toHaveBeenLastCalledWith('appointment');layout.go('details');expect(window.scrollTo).toHaveBeenLastCalledWith({top:988,behavior:'instant'});expect(document.activeElement.textContent).toBe('details');
 layout.dispose();onStep.mockClear();fonts.dispatchEvent(new Event('loadingdone'));window.dispatchEvent(new Event('scroll'));layout.go('review');expect(onStep).not.toHaveBeenCalled();
});
test('missing animation frames uses instant real-section focus rather than losing navigation',()=>{
 vi.stubGlobal('requestAnimationFrame',undefined);media.matches=false;const layout=mountBookingLayout(root,vi.fn(),{headerBar:header});layout.go('appointment');expect(window.scrollTo).toHaveBeenCalledOnce();expect(document.activeElement.textContent).toBe('appointment');layout.dispose();
});
test('zero-size strip or missing decorative element never prevents functional section navigation',()=>{
 root.querySelector('nav').getBoundingClientRect=()=>rect(20,80,0,0);let layout=mountBookingLayout(root,vi.fn(),{headerBar:header});layout.go('details');expect(document.activeElement.textContent).toBe('details');layout.dispose();root.querySelector('.step-medallion').remove();layout=mountBookingLayout(root,vi.fn(),{headerBar:header});layout.go('review');expect(document.activeElement.textContent).toBe('review');layout.dispose();
});

test.each(['missing','throws'])('unavailable device-motion preference (%s) keeps navigation functional and instant',kind=>{
 vi.stubGlobal('matchMedia',kind==='missing'?undefined:()=>{throw Error('synthetic preference unavailable');});const layout=mountBookingLayout(root,vi.fn(),{headerBar:header});layout.go('appointment');expect(window.scrollTo).toHaveBeenCalledOnce();expect(window.scrollTo.mock.calls[0][0].behavior).toBe('instant');expect(document.activeElement.textContent).toBe('appointment');layout.dispose();
});

test('replaced and disposed observation callbacks cannot update a later booking view',()=>{
 const onStep=vi.fn(),layout=mountBookingLayout(root,onStep,{headerBar:header}),old=intersection;header.getBoundingClientRect=()=>rect(0,0,390,96);resize();const current=intersection;expect(current).not.toBe(old);old([{target:root.querySelector('#details'),isIntersecting:true}]);expect(onStep).not.toHaveBeenCalled();current([{target:root.querySelector('#appointment'),isIntersecting:true}]);expect(onStep).toHaveBeenLastCalledWith('appointment');layout.dispose();onStep.mockClear();current([{target:root.querySelector('#review'),isIntersecting:true}]);expect(onStep).not.toHaveBeenCalled();
});

test.each([
 ['legacy-only',{matches:false,addListener(){},removeListener(){}}],
 ['missing add',{matches:false,removeEventListener(){}}],
 ['missing remove',{matches:false,addEventListener(){}}],
 ['text matches',{matches:'false',addEventListener(){},removeEventListener(){}}],
 ['number matches',{matches:0,addEventListener(){},removeEventListener(){}}],
 ['empty',{}],['null',null]
])('incomplete motion preference (%s) uses immediate real-section navigation',(_name,value)=>{
 const frame=vi.fn();vi.stubGlobal('matchMedia',()=>value);vi.stubGlobal('requestAnimationFrame',frame);
 const layout=mountBookingLayout(root,vi.fn(),{headerBar:header});layout.go('appointment');expect(frame).not.toHaveBeenCalled();expect(window.scrollTo).toHaveBeenCalledOnce();expect(document.activeElement.textContent).toBe('appointment');expect(()=>layout.dispose()).not.toThrow();
});

test('partly added media subscription and throwing removal choose instant navigation and leave inert callbacks',()=>{
 media.matches=false;const add=media.addEventListener.bind(media),frame=vi.fn();vi.stubGlobal('requestAnimationFrame',frame);
 vi.spyOn(media,'addEventListener').mockImplementation((...args)=>{add(...args);throw Error('partial media add');});const remove=vi.spyOn(media,'removeEventListener').mockImplementation(()=>{throw Error('media remove');});
 let layout;expect(()=>{layout=mountBookingLayout(root,vi.fn(),{headerBar:header});}).not.toThrow();layout.go('details');expect(frame).not.toHaveBeenCalled();expect(document.activeElement.textContent).toBe('details');expect(remove).toHaveBeenCalledOnce();expect(()=>layout.dispose()).not.toThrow();expect(()=>media.dispatchEvent(new Event('change'))).not.toThrow();expect(frame).not.toHaveBeenCalled();
});

test('failed partial observation and throwing disconnect retain fallback geometry without live abandoned callbacks',()=>{
 let resizeCallback,intersectionCallback;
 vi.stubGlobal('ResizeObserver',class{constructor(fn){resizeCallback=fn;this.count=0;}observe(){if(++this.count===2)throw Error('partial resize observe');}disconnect(){throw Error('resize disconnect');}});
 vi.stubGlobal('IntersectionObserver',class{constructor(fn){intersectionCallback=fn;this.count=0;}observe(){if(++this.count===2)throw Error('partial intersection observe');}disconnect(){throw Error('intersection disconnect');}});
 const onStep=vi.fn();let layout;expect(()=>{layout=mountBookingLayout(root,onStep,{headerBar:header});}).not.toThrow();expect(onStep).toHaveBeenLastCalledWith('service');onStep.mockClear();header.getBoundingClientRect=()=>rect(0,0,390,96);
 resizeCallback();intersectionCallback([{target:root.querySelector('#review'),isIntersecting:true}]);expect(onStep).not.toHaveBeenCalled();expect(root.style.getPropertyValue('--booking-header-height')).toBe('80px');
 window.dispatchEvent(new Event('resize'));expect(root.style.getPropertyValue('--booking-header-height')).toBe('96px');expect(onStep).toHaveBeenLastCalledWith('service');expect(()=>layout.dispose()).not.toThrow();onStep.mockClear();resizeCallback();intersectionCallback([{target:root.querySelector('#review'),isIntersecting:true}]);expect(onStep).not.toHaveBeenCalled();
});

test('throwing native teardown still deactivates observers and every event listener',()=>{
 vi.stubGlobal('ResizeObserver',class{constructor(fn){resize=fn;}observe(){}disconnect(){throw Error('resize disconnect');}});vi.stubGlobal('IntersectionObserver',class{constructor(fn){intersection=fn;}observe(){}disconnect(){throw Error('intersection disconnect');}});
 const onStep=vi.fn(),layout=mountBookingLayout(root,onStep,{headerBar:header}),nativeRemove=window.removeEventListener.bind(window),fontRemove=vi.spyOn(fonts,'removeEventListener'),mediaRemove=vi.spyOn(media,'removeEventListener');
 const remove=vi.spyOn(window,'removeEventListener').mockImplementation((...args)=>{if(args[0]==='wheel')throw Error('window remove');nativeRemove(...args);});
 expect(()=>layout.dispose()).not.toThrow();expect(fontRemove).toHaveBeenCalledOnce();expect(mediaRemove).toHaveBeenCalledOnce();expect(remove.mock.calls.some(([event])=>event==='keydown')).toBe(true);onStep.mockClear();
 resize();intersection([{target:root.querySelector('#review'),isIntersecting:true}]);window.dispatchEvent(new Event('wheel'));window.dispatchEvent(new Event('resize'));window.dispatchEvent(new Event('scroll'));fonts.dispatchEvent(new Event('loadingdone'));media.dispatchEvent(new Event('change'));layout.go('review');expect(onStep).not.toHaveBeenCalled();
 const calls=remove.mock.calls.length;layout.dispose();expect(remove.mock.calls).toHaveLength(calls);nativeRemove(...remove.mock.calls.find(([event])=>event==='wheel'));
});

test('throwing native frame cancellation cannot revive an interrupted scroll or cancel its replacement',()=>{
 media.matches=false;const frames=[];vi.spyOn(performance,'now').mockReturnValue(0);vi.stubGlobal('requestAnimationFrame',fn=>{frames.push(fn);return frames.length;});vi.stubGlobal('cancelAnimationFrame',()=>{throw Error('cancel unavailable');});
 const layout=mountBookingLayout(root,vi.fn(),{headerBar:header});layout.go('appointment');window.dispatchEvent(new Event('pointerdown'));layout.go('review');frames[0](220);expect(window.scrollTo).not.toHaveBeenCalled();frames[1](220);expect(window.scrollTo).toHaveBeenCalledOnce();expect(document.activeElement.textContent).toBe('review');
 layout.go('details');expect(()=>layout.dispose()).not.toThrow();window.scrollTo.mockClear();frames[2](220);expect(window.scrollTo).not.toHaveBeenCalled();
});

test('failed optional font subscription is contained and cannot leave an animated scroll without all interruption support',()=>{
 media.matches=false;const add=fonts.addEventListener.bind(fonts),remove=vi.spyOn(fonts,'removeEventListener'),frame=vi.fn();vi.stubGlobal('requestAnimationFrame',frame);vi.spyOn(fonts,'addEventListener').mockImplementation((...args)=>{add(...args);throw Error('font event add');});
 const layout=mountBookingLayout(root,vi.fn(),{headerBar:header});layout.go('appointment');expect(frame).not.toHaveBeenCalled();expect(remove).toHaveBeenCalledOnce();layout.dispose();expect(()=>fonts.dispatchEvent(new Event('loadingdone'))).not.toThrow();
});
