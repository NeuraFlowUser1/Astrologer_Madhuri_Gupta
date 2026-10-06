// @vitest-environment jsdom
import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {beforeEach,afterEach,expect,test,vi} from 'vitest';
const mocks=vi.hoisted(()=>({api:vi.fn()}));
// Test-only provider doubles exercise the actual shared React hook/controller.
vi.mock('../../../appointment-system/browser/enquiry/index.mjs',async original=>{
 const actual=await original();
 const {createEnquiryController}=await import('../../../appointment-system/browser/enquiry/controller.mjs');
 const {createEnquiryStore}=await import('../../../appointment-system/browser/enquiry/credentials.mjs');
 const {installation_id}=await import('../../../appointment-system/tests/booking-browser-fixture.mjs');
 return {...actual,createEnquiryBrowser:()=>({controller:channel=>createEnquiryController({
  api:{policy:async()=>({version:1,receipt_key_id:'current'}),send:mocks.api},
  receipts:createEnquiryStore({installation_id,environment:'test',channel}),storage:()=>sessionStorage,monotonic:Date.now})})};
});
vi.mock('../../src/site/BookingProduct.jsx',()=>({useBookingProduct:()=>({enabled:true})}));
import {useEnquiry} from '../../src/contact/useEnquiry.jsx';
import ContactForm from '../../src/contact/ContactForm.jsx';
import {createEnquiryStore} from '../../../appointment-system/browser/enquiry/credentials.mjs';
import {installation_id} from '../../../appointment-system/tests/booking-browser-fixture.mjs';
import {RequestError as ContactError} from '../../../appointment-system/browser/transport.mjs';
const receipts=createEnquiryStore({installation_id,environment:'test',channel:'contact'});
const STORAGE_KEY=receipts.storageKey,createAccess=storage=>receipts.create(storage,{version:1,receipt_key_id:'current'});
let current,root,host,server;
const draft={name:'Synthetic Visitor',email:'test@example.invalid',phone:'',subject:'Before booking',message:'A synthetic question'};
const answer=(access,changes={})=>({code:'ok',request_id:access.request_id,state:'awaiting_verification',generation:1,sends_remaining:2,verification_delivery:'queued',server_now:'2030-01-01T00:00:00Z',code_expires_at:'2030-01-01T00:10:00Z',resend_after:'2030-01-01T00:00:00Z',...changes});
async function settle(){await act(async()=>{for(let i=0;i<8;i++)await Promise.resolve();});}
async function mount(form=false,props={}){function Probe(){current=useEnquiry();return null;}await act(async()=>root.render(form?<ContactForm {...props}/>:<Probe/>));await settle();}
async function input(name,value){const element=host.querySelector(`[name="${name}"]`);const setter=Object.getOwnPropertyDescriptor(element instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:element instanceof HTMLSelectElement?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set;await act(async()=>{setter.call(element,value);element.dispatchEvent(new Event(element.tagName==='SELECT'?'change':'input',{bubbles:true}));});}
async function submit(){await act(async()=>host.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));await settle();}
beforeEach(()=>{globalThis.IS_REACT_ACT_ENVIRONMENT=true;vi.useFakeTimers();vi.setSystemTime(new Date('2030-01-01T00:00:00Z'));sessionStorage.clear();host=document.createElement('div');document.body.append(host);root=createRoot(host);server={};mocks.api.mockReset().mockImplementation(async(action,access)=>{if(action==='verify'){server={...server,state:'received'};return answer(access,server);}if(action==='resend')return answer(access,{generation:2,sends_remaining:1});return answer(access,server);});});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.useRealTimers();});

test('enquiry persists only access, verifies once, focuses the result and permits another enquiry',async()=>{
 await mount(true,{topicRequest:{topic:'Existing booking'}});expect(host.querySelector('select').value).toBe('Existing booking');
 await input('name','  Synthetic Visitor  ');await input('email','test@example.invalid');await input('message','A synthetic question');await input('reference',' synthetic-reference ');await submit();
 expect(mocks.api.mock.calls[0][2]).toMatchObject({name:'Synthetic Visitor',message:'Booking reference: synthetic-reference\n\nA synthetic question'});expect(sessionStorage.getItem(STORAGE_KEY)).not.toContain('question');
 await input('code','123');await submit();expect(host.querySelector('#form-status').textContent).toContain('six-digit');expect(mocks.api.mock.calls.some(([a])=>a==='verify')).toBe(false);
 await input('code','123456');await submit();expect(host.querySelector('#outcome')).toBe(document.activeElement);expect(sessionStorage.getItem(STORAGE_KEY)).not.toContain('123456');
 const restart=[...host.querySelectorAll('button')].find(e=>e.textContent==='Write another enquiry');await act(async()=>restart.click());expect(host.querySelector('[name=name]').value).toBe('');expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
});
test('uncertain submission retries the same request and never stores its message',async()=>{
 await mount();mocks.api.mockRejectedValueOnce(new ContactError());await act(async()=>current.start(draft));expect(current.retry).toBe('start');const first=mocks.api.mock.calls[0];await act(async()=>current.retryRequest());expect(mocks.api.mock.calls[1].slice(0,3)).toEqual(first.slice(0,3));expect(JSON.parse(sessionStorage.getItem(STORAGE_KEY))).not.toHaveProperty('message');
});
test('a failed code is not replayed; the retry checks status and resend keeps one operation identity',async()=>{
 await mount();await act(async()=>current.start(draft));mocks.api.mockRejectedValueOnce(new ContactError('verification_incorrect'));await act(async()=>current.verify('123456'));expect(current.retry).toBe('status');await act(async()=>current.retryRequest());expect(mocks.api.mock.calls.at(-1)[0]).toBe('status');
 mocks.api.mockRejectedValueOnce(new ContactError());await act(async()=>current.resend());const identity=JSON.parse(sessionStorage.getItem(STORAGE_KEY)).resend_id;expect(identity).toBeTruthy();await act(async()=>current.retryRequest());expect(mocks.api.mock.calls.at(-1)[2].operation_id).toBe(identity);expect(JSON.parse(sessionStorage.getItem(STORAGE_KEY))).not.toHaveProperty('resend_id');
});
test('restored resend access can resolve its lost response without creating a new enquiry',async()=>{
 const access=createAccess(sessionStorage);receipts.save(sessionStorage,{...access,resend_id:crypto.randomUUID(),resend_generation:1});await mount();expect(mocks.api.mock.calls[0][0]).toBe('status');await act(async()=>current.retryRequest());expect(mocks.api.mock.calls.at(-1)[0]).toBe('resend');
});
test('duplicate calls, cooldown, resend limits and restart permissions are enforced',async()=>{
 await mount();let release;mocks.api.mockImplementationOnce(()=>new Promise(resolve=>release=resolve));let pending;await act(async()=>{pending=current.start(draft);current.start(draft);current.check();});expect(mocks.api).toHaveBeenCalledTimes(1);await act(async()=>{release(answer(mocks.api.mock.calls[0][1]));await pending;});
 await act(async()=>current.restart());expect(current.started).toBe(true);mocks.api.mockRejectedValueOnce(new ContactError('please_wait',{status:429,retryAfter:20}));await act(async()=>current.check());const count=mocks.api.mock.calls.length;await act(async()=>current.check());expect(mocks.api).toHaveBeenCalledTimes(count);expect(current.waiting).toBe(20);await act(async()=>vi.advanceTimersByTimeAsync(20000));
 server={generation:3,sends_remaining:0};await act(async()=>current.check());const before=mocks.api.mock.calls.length;await act(async()=>current.resend());expect(mocks.api).toHaveBeenCalledTimes(before);
});
test('polling is read-only, bounded and paused when the tab is hidden',async()=>{
 await mount();await act(async()=>current.start(draft));mocks.api.mockClear();vi.spyOn(document,'hidden','get').mockReturnValue(true);await act(async()=>vi.advanceTimersByTimeAsync(20000));expect(mocks.api).not.toHaveBeenCalled();vi.restoreAllMocks();await act(async()=>vi.advanceTimersByTimeAsync(80000));expect(mocks.api).toHaveBeenCalledTimes(6);expect(mocks.api.mock.calls.every(([a])=>a==='status')).toBe(true);
});
test('invalid submission clears only that request; corrupt or unwritable storage blocks unsafe continuation',async()=>{
 await mount();mocks.api.mockRejectedValueOnce(new ContactError('invalid_request',{status:422}));await act(async()=>current.start(draft));expect(current.started).toBe(false);expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
 vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw Error();});await act(async()=>current.start(draft));expect(current.error).toContain('storage');vi.restoreAllMocks();
 await act(async()=>root.unmount());root=createRoot(host);sessionStorage.setItem(STORAGE_KEY,'{broken');await mount();expect(current.blocked).toBe(true);expect(current.error).toContain('saved enquiry');
});
test('expired and failed delivery states offer status and available resends without a code submission',async()=>{
 createAccess(sessionStorage);server={state:'expired',verification_delivery:'failed',code_expires_at:'2029-12-31T00:00:00Z',resend_after:'2030-01-01T00:01:00Z'};await mount(true);expect(host.textContent).toContain('could not send');expect(host.textContent).toContain('no longer usable');expect(host.querySelector('#code')).toBeNull();const resend=[...host.querySelectorAll('button')].find(e=>e.textContent.startsWith('Resend in'));expect(resend.disabled).toBe(true);
});
test('short questions and reference overflow are rejected before sending',async()=>{
 await mount(true,{topicRequest:{topic:'Payment question'}});await input('name','A');await input('message','Hi');await submit();expect(host.querySelector('#form-status').textContent).toContain('five characters');expect(mocks.api).not.toHaveBeenCalled();await input('name','Synthetic');await input('reference','reference');await input('message','x'.repeat(3995));await submit();expect(host.querySelector('#form-status').textContent).toContain('shorten');expect(mocks.api).not.toHaveBeenCalled();
});
test('unmount aborts an in-flight enquiry and ignores its late response',async()=>{
 await mount();let release;mocks.api.mockImplementationOnce(()=>new Promise(resolve=>release=resolve));let pending;await act(async()=>{pending=current.start(draft);});const signal=mocks.api.mock.calls[0][3];await act(async()=>root.unmount());expect(signal.aborted).toBe(true);release(answer(mocks.api.mock.calls[0][1]));await pending;root=createRoot(host);
});
