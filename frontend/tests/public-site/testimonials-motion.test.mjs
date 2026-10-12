import {beforeEach,afterEach,test,expect,vi} from 'vitest';
import {mountTestimonialsMotion} from '../../src/site/testimonials-motion.mjs';
let root,media,observed,created,controls,oldAnimate;
beforeEach(()=>{
  root=document.createElement('div');root.innerHTML=`
    <section data-scene="opening"><div data-ambient></div><svg><path class="thread-draw"/><path class="opening-star"/></svg><div data-paper="back"></div><div data-paper="main"></div><div data-paper="front"></div><button>Opening action</button></section>
    <section data-scene="featured"><div data-enter="photo"></div><div data-enter="quote" id="featured-story"></div></section>
    <section data-scene="collection"><div id="story-grid"><article class="story-card"></article><article class="story-card"></article></div></section>
    <section data-scene="echoes"><svg class="echo-line"><path/></svg><div data-enter="echo" class="echo-content"></div></section>
    <section data-scene="invitation"><svg><path class="invitation-path"/><g class="sun-lines"></g></svg></section>`;
  document.body.append(root);observed=[];created=[];controls=[];
  media=new EventTarget();media.matches=false;vi.stubGlobal('matchMedia',()=>media);
  vi.stubGlobal('IntersectionObserver',class{
    constructor(callback){this.callback=callback;this.disconnect=vi.fn();observed.push(this);}
    observe=vi.fn();publish(target,isIntersecting=true){this.callback([{target,isIntersecting}]);}
  });
  oldAnimate=Object.getOwnPropertyDescriptor(Element.prototype,'animate');
  Object.defineProperty(Element.prototype,'animate',{configurable:true,writable:true,value:vi.fn(function(frames,options){
    let resolve,reject;const animation={effect:{target:this},frames,options,playState:'running',finished:new Promise((yes,no)=>{resolve=yes;reject=no;})};
    animation.finish=()=>{animation.playState='finished';resolve();};
    animation.cancel=vi.fn(()=>{animation.playState='idle';reject(Error('cancelled'));});
    animation.pause=vi.fn(()=>{animation.playState='paused';});animation.play=vi.fn(()=>{animation.playState='running';});created.push(animation);return animation;
  })});
});
afterEach(async()=>{controls.forEach(control=>control.dispose());await Promise.resolve();root.remove();if(oldAnimate)Object.defineProperty(Element.prototype,'animate',oldAnimate);else delete Element.prototype.animate;vi.restoreAllMocks();vi.unstubAllGlobals();});
function mount(){const control=mountTestimonialsMotion(root);controls.push(control);return control;}
function scene(name){return root.querySelector(`[data-scene=${name}]`);}
async function flush(){await Promise.resolve();await Promise.resolve();}
test('all five accepted assemblies keep their order and timing, and each scene enters once',async()=>{
  const control=mount(),observer=observed[0],ambient=root.querySelector('[data-ambient]');
  observer.publish(ambient);for(const name of ['opening','featured','collection','echoes','invitation'])observer.publish(scene(name));
  expect(created.map(animation=>[animation.options.duration,animation.options.delay||0])).toEqual([[700,0],[750,150],[750,270],[750,390],[500,900],[650,0],[700,350],[450,0],[450,70],[800,0],[650,300],[950,0],[750,0]]);
  expect(ambient.classList.contains('is-running')).toBe(false);created[4].finish();await flush();expect(ambient.classList.contains('is-running')).toBe(true);
  const count=created.length;observer.publish(scene('opening'));expect(created).toHaveLength(count);
  control.setReaderOpen(true);expect(ambient.classList.contains('is-running')).toBe(false);control.setReaderOpen(false);expect(ambient.classList.contains('is-running')).toBe(true);
  observer.publish(ambient,false);expect(ambient.classList.contains('is-running')).toBe(false);
});
test('selection motion replaces only its own channel and never writes text or changes the existing paths',async()=>{
  const control=mount(),before=root.innerHTML;control.updateFeature();control.updateFeature();expect(created[0].cancel).toHaveBeenCalledOnce();
  control.updateTheme();control.updateTheme();expect(created[2].cancel).toHaveBeenCalledOnce();
  control.updateGrid();control.updateGrid();expect(created[4].cancel).toHaveBeenCalledOnce();expect(created[5].cancel).toHaveBeenCalledOnce();expect(root.innerHTML).toBe(before);
  created.forEach(animation=>animation.finish());await flush();control.dispose();
});
test('focused scenes settle before reading; their decorations resume only after focus leaves',async()=>{
  const control=mount(),observer=observed[0],ambient=root.querySelector('[data-ambient]'),button=root.querySelector('button');
  observer.publish(ambient);observer.publish(scene('opening'));button.focus();expect(created.every(animation=>animation.cancel.mock.calls.length===1)).toBe(true);await flush();expect(ambient.classList.contains('is-running')).toBe(false);
  button.blur();await flush();expect(ambient.classList.contains('is-running')).toBe(true);
  control.dispose();await flush();expect(ambient.classList.contains('is-running')).toBe(false);
});
test('a scene already focused when observed never animates the reading content',async()=>{
  root.querySelector('button').focus();mount();observed[0].publish(root.querySelector('[data-ambient]'));observed[0].publish(scene('opening'));expect(created).toHaveLength(0);
  root.querySelector('button').blur();await flush();expect(root.querySelector('[data-ambient]').classList.contains('is-running')).toBe(true);
});
test('hidden tabs pause pending animations and visibility resumes them; reduced motion cancels them',async()=>{
  const control=mount(),observer=observed[0];observer.publish(scene('opening'));
  const hidden=vi.spyOn(document,'hidden','get').mockReturnValue(true);document.dispatchEvent(new Event('visibilitychange'));expect(created.every(animation=>animation.playState==='paused')).toBe(true);
  control.updateTheme();expect(created.at(-1).pause).toHaveBeenCalledOnce();
  hidden.mockReturnValue(false);document.dispatchEvent(new Event('visibilitychange'));expect(created.every(animation=>animation.playState==='running')).toBe(true);
  media.matches=true;media.dispatchEvent(new Event('change'));expect(created.every(animation=>animation.cancel.mock.calls.length===1)).toBe(true);await flush();
  const count=created.length;control.updateFeature();expect(created).toHaveLength(count);
});
test('initial reduced motion, missing animation support and missing/failed observers keep all content visible',()=>{
  media.matches=true;mount();observed[0].publish(scene('opening'));expect(created).toHaveLength(0);controls.pop().dispose();
  media.matches=false;Element.prototype.animate=undefined;mount();observed[1].publish(scene('opening'));expect(created).toHaveLength(0);controls.pop().dispose();
  vi.stubGlobal('IntersectionObserver',undefined);mount();expect(root.textContent).toContain('Opening action');controls.pop().dispose();
  const disconnect=vi.fn();vi.stubGlobal('IntersectionObserver',class{disconnect=disconnect;observe(){throw Error('unsupported observation');}});mount();expect(disconnect).toHaveBeenCalledOnce();expect(root.textContent).toContain('Opening action');
});
test('dispose removes listeners and fences late completions, queued focus work and observer callbacks',async()=>{
  const control=mount(),observer=observed[0],ambient=root.querySelector('[data-ambient]');observer.publish(ambient);observer.publish(scene('opening'));
  root.dispatchEvent(new FocusEvent('focusout',{bubbles:true}));control.dispose();expect(observer.disconnect).toHaveBeenCalledOnce();
  observer.publish(scene('featured'));observer.publish(ambient);created[4].finish();await flush();expect(ambient.classList.contains('is-running')).toBe(false);
  const count=created.length;control.updateFeature();document.dispatchEvent(new Event('visibilitychange'));media.dispatchEvent(new Event('change'));expect(created).toHaveLength(count);
});
