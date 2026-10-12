import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {beforeEach,afterEach,test,expect,vi} from 'vitest';
import TestimonialReader from '../../src/site/TestimonialReader.jsx';
import {testimonialStories} from '../fixtures/testimonial-stories.mjs';
let root,frame,host,opener,heading,methods;
beforeEach(()=>{
  globalThis.IS_REACT_ACT_ENVIRONMENT=true;
  frame=document.createElement('main');frame.className='sarsa-testimonials';
  frame.innerHTML='<h2 id="stories-title" tabindex="-1">Client reviews</h2><button>Read story</button><div></div>';
  document.body.append(frame);opener=frame.querySelector('button');heading=frame.querySelector('h2');host=frame.querySelector('div');root=createRoot(host);
  methods=Object.fromEntries(['showModal','close'].map(name=>[name,Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype,name)]));
  Object.defineProperty(HTMLDialogElement.prototype,'showModal',{configurable:true,value:function(){this.setAttribute('open','');}});
  Object.defineProperty(HTMLDialogElement.prototype,'close',{configurable:true,value:function(){this.removeAttribute('open');}});
});
afterEach(async()=>{await act(async()=>root.unmount());frame.remove();document.body.style.overflow='';for(const [name,descriptor] of Object.entries(methods)){if(descriptor)Object.defineProperty(HTMLDialogElement.prototype,name,descriptor);else delete HTMLDialogElement.prototype[name];}vi.restoreAllMocks();});
async function render(native=true){await act(async()=>root.render(<TestimonialReader story={testimonialStories[0]} opener={opener} native={native} onClose={()=>root.render(null)}/>));}
async function key(target,key,shiftKey=false){let event;await act(async()=>{event=new KeyboardEvent('keydown',{key,shiftKey,bubbles:true,cancelable:true});target.dispatchEvent(event);});return event;}
test('Close falls back to the collection heading if its opening action was removed',async()=>{
  await render();opener.remove();await act(async()=>host.querySelector('#dialog-close').click());expect(document.activeElement).toBe(heading);
});
test('closing remains safe if both the opening action and collection were removed',async()=>{
  await render(false);opener.remove();heading.remove();await act(async()=>host.querySelector('#dialog-close').click());expect(host.querySelector('dialog')).toBeNull();
});
test('native Tab wraps on Close in both directions; ordinary keys keep their default behaviour',async()=>{
  await render();const close=host.querySelector('#dialog-close');close.focus();
  for(const shifted of [false,true]){const event=await key(close,'Tab',shifted);expect(event.defaultPrevented).toBe(true);expect(document.activeElement).toBe(close);}
  expect((await key(close,'Enter')).defaultPrevented).toBe(false);
  const event=await key(close,'Escape');expect(event.defaultPrevented).toBe(true);expect(host.querySelector('dialog')).toBeNull();expect(document.activeElement).toBe(opener);
});
test('an inline reader never traps Tab or locks page scrolling',async()=>{
  await render(false);expect((await key(host.querySelector('#dialog-title'),'Tab')).defaultPrevented).toBe(false);expect(document.body.style.overflow).toBe('');
});
