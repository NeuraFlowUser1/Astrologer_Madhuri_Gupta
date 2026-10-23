import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {renderToStaticMarkup} from 'react-dom/server';
import {test,expect,vi,beforeEach,afterEach} from 'vitest';
const owner=vi.hoisted(()=>({definitions:[],stop:vi.fn()}));
vi.mock('../../src/site/scenes.mjs',()=>({mountScenes:(_root,definitions)=>{owner.definitions=definitions;return owner.stop;}}));
import {VastuHero,VastuTopics,VastuPrinciples} from '../../src/site/VastuDetails.jsx';
import ServiceVisualStory from '../../src/site/ServiceVisualStory.jsx';
import {mountServiceMotion} from '../../src/site/service-motion.mjs';
import {createVastuPrinciplesScene} from '../../src/site/vastu-motion.mjs';
import {vastuConcepts} from '../../src/site/vastu-content.mjs';
let host,root,probes,reduce;
const click=node=>act(async()=>node.dispatchEvent(new MouseEvent('click',{bubbles:true})));
const render=node=>act(async()=>root.render(node));
beforeEach(()=>{
 globalThis.IS_REACT_ACT_ENVIRONMENT=true;reduce=false;probes=[];
 vi.stubGlobal('matchMedia',()=>({get matches(){return reduce;},addEventListener:vi.fn(),removeEventListener:vi.fn()}));
 vi.stubGlobal('Image',class{decode(){return new Promise((resolve,reject)=>{probes.push({resolve,reject});});}});
 host=document.createElement('main');document.body.append(host);root=createRoot(host);owner.stop.mockClear();
});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.unstubAllGlobals();vi.useRealTimers();});

test('principles expose one selected explanation and the matching accessible diagram, with a real 81-pada grid',async()=>{
 await render(<VastuPrinciples/>);
 expect(host.querySelectorAll('[data-grid-line]')).toHaveLength(16);
 expect(host.querySelector('.principles-centre rect').getAttribute('width')).toBe('108');
 for(const [i,key] of ['mandala','centre','elements'].entries()){
  const button=host.querySelectorAll('button')[i];await click(button);
  expect(host.querySelector('[data-principle]').dataset.principle).toBe(key);
  expect(host.querySelectorAll('[aria-pressed=true]')).toHaveLength(1);
  expect(host.querySelector('svg title').textContent).toBe(vastuConcepts[key].name);
  expect(host.querySelector('svg desc').textContent).toBe(vastuConcepts[key].description);
  expect(host.querySelector('.principles-body-stack>p').textContent).toBe(vastuConcepts[key].body);
  expect(host.querySelector('figcaption').textContent).toBe(vastuConcepts[key].caption);
 }
 expect(host.querySelectorAll('.principles-measure[aria-hidden=true]')).toHaveLength(6);
});

test('the new scene joins the original owner, stages paper/grid/plan/emphasis, and settles every line',async()=>{
 expect(createVastuPrinciplesScene(host)).toEqual([]);
 await render(<VastuPrinciples/>);const [scene]=createVastuPrinciplesScene(host);
 scene.render(0);expect(host.querySelector('[data-principles-stage=paper]').style.opacity).toBe('0');
 scene.render(.45);expect(Number(host.querySelector('[data-principles-stage=grid]').style.opacity)).toBeGreaterThan(0);
 expect(host.querySelector('[data-principles-stage=emphasis]').style.opacity).toBe('0');
 scene.render(1);
 for(const layer of host.querySelectorAll('[data-principles-stage],[data-grid-line]'))expect(layer.style.opacity).toBe('1');
 expect(host.querySelector('[data-grid-line=row]').style.transform).toBe('scaleX(1)');
 expect(host.querySelector('[data-grid-line=column]').style.transform).toBe('scaleY(1)');
});

test.each(['matching','vastu','numerology'])('the %s hero and all original scenes keep their single clock and final positions',async(art)=>{
 await render(<>{art==='vastu'?<section data-service-scene="hero"><VastuHero/></section>:<section data-service-scene="hero"><i data-layer/><i data-layer/><i data-layer/></section>}<section data-service-scene="topics"><VastuTopics/><p data-copy/></section>{art==='vastu'&&<VastuPrinciples/>}<section data-service-scene="prepare"><div data-layer/><p data-copy/></section><section data-service-scene="book"><p data-copy/></section></>);
 for(const width of [390,1440]){
  vi.stubGlobal('innerWidth',width);const stop=mountServiceMotion(host,art);
  expect(owner.definitions).toHaveLength(art==='vastu'?5:4);
  for(const p of [0,.3,.65,1])for(const scene of owner.definitions)scene.render(p);
  expect(host.querySelector('[data-layer]').style.opacity).toBe('1');
  stop();expect(owner.stop).toHaveBeenCalled();
 }
 if(art==='vastu'){
  const img=host.querySelector('img');expect(img.getAttribute('width')).toBe('1200');expect(img.getAttribute('srcset')).toContain('480w');
  expect(host.textContent).toContain('Your priorities');
 }
});

test('Vastu has four manual topics, one correctly positioned marker, and decoded forward/back transitions',async()=>{
 await render(<ServiceVisualStory serviceId="vastu-consultation" name="Vastu Consultation"/>);
 const buttons=()=>host.querySelectorAll('.story-choices button');expect(buttons()).toHaveLength(4);
 for(const [i,point] of [[0,[48,47]],[1,[49,23]],[2,[38,33]],[3,[63,40]]]){
  await click(buttons()[i]);const marker=host.querySelector('.story-marker');
  expect(host.querySelectorAll('.story-marker')).toHaveLength(1);expect(marker.textContent).toBe(String(i+1));expect(marker.style.left).toBe(point[0]+'%');
 }
 const next=host.querySelector('.story-controls button:last-child'),prev=host.querySelector('.story-controls button:first-child');
 await click(prev);expect(probes).toHaveLength(0);
 await click(next);expect(host.querySelector('[aria-busy=true]')).not.toBeNull();
 await act(async()=>probes[0].resolve());expect(host.querySelector('.story-controls span').textContent).toBe('2 of 2');
 expect(host.querySelector('.story-marker').style.left).toBe('36%');expect(host.querySelector('.story-outgoing')).not.toBeNull();
 await click(next);expect(probes).toHaveLength(1);
 await act(async()=>new Promise(resolve=>setTimeout(resolve,260)));expect(host.querySelector('.story-outgoing')).toBeNull();
 reduce=true;await click(prev);await act(async()=>probes[1].resolve());expect(host.querySelector('.story-controls span').textContent).toBe('1 of 2');expect(host.querySelector('.story-outgoing')).toBeNull();
});

test('decode failure keeps the current picture, retry works, and a failed displayed picture can be reloaded',async()=>{
 await render(<ServiceVisualStory serviceId="vastu-consultation" name="Vastu Consultation"/>);
 await click(host.querySelector('.story-controls button:last-child'));
 await act(async()=>probes[0].reject(Error('synthetic image failure')));
 expect(host.querySelector('.story-controls span').textContent).toBe('1 of 2');expect(host.querySelector('[role=status]').textContent).toContain('could not load');
 await click(host.querySelector('.story-image-status button'));await act(async()=>probes[1].resolve());
 expect(host.querySelector('.story-controls span').textContent).toBe('2 of 2');
 await act(async()=>host.querySelector('.story-picture>.service-media:not(.story-outgoing) img').dispatchEvent(new Event('error')));
 expect(host.querySelector('.service-media-fallback')).not.toBeNull();await click(host.querySelector('.story-image-status button'));await act(async()=>probes[2].resolve());
 expect(host.querySelector('.service-media-fallback')).toBeNull();
});

test('stale image completions and failures cannot overwrite a newer request or a detached page',async()=>{
 await render(<ServiceVisualStory serviceId="vastu-consultation" name="Vastu Consultation"/>);
 const next=host.querySelector('.story-controls button:last-child'),prev=host.querySelector('.story-controls button:first-child');
 await click(next);await click(prev);await act(async()=>probes[0].resolve());expect(host.querySelector('.story-controls span').textContent).toBe('1 of 2');
 await click(next);await click(prev);await act(async()=>probes[1].reject(Error('stale failure')));expect(host.querySelector('[role=status]').textContent).toBe('');
 await click(next);await render(null);await act(async()=>probes[2].resolve());expect(host.textContent).toBe('');
 await render(<ServiceVisualStory serviceId="vastu-consultation" name="Vastu Consultation"/>);await click(host.querySelector('.story-controls button:last-child'));await render(null);await act(async()=>probes[3].reject(Error('detached failure')));expect(host.textContent).toBe('');
});

test.each(['kundli-matching','kundli-prediction','numerology'])('other service %s retains three markers and its own decorative layer',async(serviceId)=>{
 await render(<ServiceVisualStory serviceId={serviceId} name={serviceId}/>);
 expect(host.querySelectorAll('.story-marker')).toHaveLength(3);expect(host.querySelectorAll('.story-choices button')).toHaveLength(3);expect(host.querySelector('[data-visual-ambient]')).not.toBeNull();
 expect(renderToStaticMarkup(<VastuHero/>)).toContain('A home, considered as a whole.');
});
