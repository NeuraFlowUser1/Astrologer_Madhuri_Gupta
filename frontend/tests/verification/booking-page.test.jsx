// @vitest-environment jsdom
import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {MemoryRouter} from 'react-router-dom';
import {afterEach,beforeEach,expect,test,vi} from 'vitest';
import policy from '../booking/policy.json';
const mock=vi.hoisted(()=>({flow:null,motion:vi.fn(()=>()=>{})}));
vi.mock('../../src/booking/useBooking.jsx',()=>({useBooking:()=>mock.flow}));
vi.mock('../../src/booking/motion.mjs',()=>({mountBookingMotion:mock.motion}));
import Booking from '../../src/pages/Booking.jsx';

const id='11111111-1111-4111-8111-111111111111';
const slot={starts_at:'2030-01-02T10:00:00+05:30',ends_at:'2030-01-02T10:30:00+05:30'};
let root,host;
const receipt=(changes={})=>({request_id:id,appointment_state:'held',order_state:'ready',payment_state:'unobserved',service_name:'Kundli Prediction',currency:'INR',timezone:'Asia/Kolkata',amount_paise:250000,captured_paise:0,refunded_paise:0,...slot,server_now:'2030-01-01T09:00:00Z',hold_expires_at:'2030-01-01T09:10:00Z',next_actions:['resume_payment'],meeting_state:'not_created',meet_url:null,...changes});
async function render(changes={}){Object.assign(mock.flow.state,changes);await act(async()=>root.render(<MemoryRouter><Booking/></MemoryRouter>));}
const $=selector=>host.querySelector(selector);
async function click(element){await act(async()=>element.click());}
function button(text){return [...host.querySelectorAll('button')].find(el=>el.textContent.includes(text));}
async function change(selector,value){const el=$(selector),prototype=Object.getPrototypeOf(el);Object.getOwnPropertyDescriptor(prototype,'value').set.call(el,value);await act(async()=>el.dispatchEvent(new Event('input',{bubbles:true})));}
beforeEach(()=>{
 globalThis.IS_REACT_ACT_ENVIRONMENT=true;vi.useFakeTimers();vi.setSystemTime(new Date('2030-01-01T09:00:00Z'));
 vi.stubGlobal('matchMedia',()=>({matches:true}));window.scrollTo=vi.fn();Element.prototype.scrollIntoView=vi.fn();
 host=document.createElement('div');document.body.append(host);root=createRoot(host);
 mock.flow={state:{service:'kundli-prediction',day:'2030-01-02',slot:null,policy:structuredClone(policy),loadingPolicy:false,slots:[slot],slotsStatus:'ready',credential:null,receipt:null,phase:'draft',error:'',busy:false,ack:false,retryAt:0,details:{full_name:'',email:'',phone:'',country:'91',notes:''}},dispatch:vi.fn(),start:vi.fn(),resume:vi.fn(),check:vi.fn(),restart:vi.fn(),retryOriginal:vi.fn(),loadPolicy:vi.fn(),canRetryOriginal:false};
});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.useRealTimers();vi.unstubAllGlobals();});

test('booking form requires name, email, mobile, a selected time and acknowledgement',async()=>{
 await render();expect($('#full_name').required).toBe(true);expect($('#email').required).toBe(true);expect($('#phone').required).toBe(true);expect($('button[type="submit"]').disabled).toBe(true);expect(host.textContent).toContain('No email verification code');
 await act(async()=>host.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));expect(mock.flow.dispatch).toHaveBeenCalledWith(expect.objectContaining({type:'error'}));expect(mock.flow.start).not.toHaveBeenCalled();
 await render({slot,ack:true,details:{full_name:'Synthetic Visitor',email:'case@example.com',phone:'9876543210',country:'91',notes:'Synthetic question'}});expect($('button[type="submit"]').disabled).toBe(false);
 await act(async()=>host.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));expect(mock.flow.start).toHaveBeenCalledOnce();expect(host.textContent).toContain('Synthetic question');
});
test('available controls dispatch edits and navigation validates the existing form',async()=>{
 await render();await click($('input[name="service"][value="numerology"]'));expect(mock.flow.dispatch).toHaveBeenCalledWith({type:'edit',name:'service',value:'numerology'});
 await click($('input[name="time"]'));expect(mock.flow.dispatch).toHaveBeenCalledWith({type:'edit',name:'slot',value:slot});
 await change('#full_name','New visitor');await change('#email','correct@example.com');await change('#phone','9876543210');await change('#notes','Question');expect(mock.flow.dispatch).toHaveBeenCalledWith({type:'details',name:'notes',value:'Question'});
 await change('#appointment-date','2030-01-03');expect(mock.flow.dispatch).toHaveBeenCalledWith({type:'edit',name:'day',value:'2030-01-03'});
 const country=$('select');country.value='other';await act(async()=>country.dispatchEvent(new Event('change',{bubbles:true})));expect(mock.flow.dispatch).toHaveBeenCalledWith({type:'details',name:'country',value:'other'});
 await click($('.acknowledgement input'));expect(mock.flow.dispatch).toHaveBeenCalledWith({type:'ack',value:true});
 const validity=vi.spyOn(HTMLFormElement.prototype,'reportValidity').mockReturnValue(false);await click(button('Review your booking'));expect(validity).toHaveBeenCalledOnce();expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
 validity.mockReturnValue(true);await click(button('Review your booking'));expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
 for(const link of host.querySelectorAll('.journey-nav a'))await click(link);for(const el of host.querySelectorAll('.edit-button'))await click(el);
 await render({slot});await click(button('Your details'));await click(button('Choose a consultation'));await click(button('Choose a time'));await click(button('← Consultation'));await click(button('← Date & time'));
});
test.each([
 ['loading',[], 'Checking available times'],['error',[],'cannot check'],['ready',[],'no available times'],['idle',[],'Choose a date'],
])('availability %s offers no invented appointment times',async(slotsStatus,slots,wording)=>{
 await render({slotsStatus,slots});expect($('#availability-message').textContent).toContain(wording);expect(host.querySelectorAll('input[name="time"]')).toHaveLength(0);expect(button('Your details').disabled).toBe(true);
});
test('policy failure offers reload; loading, blocked and busy states cannot submit',async()=>{
 await render({policy:null,loadingPolicy:true});expect(host.textContent).toContain('Loading consultation details');expect($('#appointment-date').disabled).toBe(true);
 await render({loadingPolicy:false,error:'Details unavailable'});expect(host.textContent).toContain('Consultation details unavailable');await click(button('Reload consultation details'));expect(mock.flow.loadPolicy).toHaveBeenCalledOnce();
 await render({phase:'blocked'});expect(host.querySelector('fieldset').disabled).toBe(true);await render({phase:'draft',busy:true,slot,ack:true});expect($('button[type="submit"]').disabled).toBe(true);expect(host.textContent).toContain('Preparing your booking');
 await render({policy:structuredClone(policy),busy:false,details:{full_name:'',email:'',phone:'+442079460018',country:'other',notes:''}});expect($('#phone').pattern).toContain('\\+');expect(host.textContent).toContain('Include +');
});
test.each([
 ['held','not_created','unobserved','Your time is reserved.'],['expired','not_created','unobserved','Let’s check the payment.'],
 ['confirmed','waiting','captured','Your appointment is confirmed.'],['cancelled','cancelled','captured','Your appointment is cancelled.'],
 ['payment_review','needs_attention','needs_attention','Your payment needs a closer look.'],
])('receipt %s distinguishes appointment, payment, meeting and email status',async(appointment_state,meeting_state,payment_state,title)=>{
 await render({credential:{request_id:id},receipt:receipt({appointment_state,meeting_state,payment_state,captured_paise:payment_state==='unobserved'?0:250000,acknowledgement_state:'delivered',meeting_email_state:'pending'}),phase:'receipt'});
 expect($('#receipt-title').textContent).toBe(title);expect(host.textContent).toContain(id);expect($('#receipt-facts').textContent).toContain('Delivered');await click(button('Check booking status'));expect(mock.flow.check).toHaveBeenCalledOnce();
 if(appointment_state==='held'){expect($('#hold-clock').textContent).toContain('10:00');await click(button('Continue to payment'));expect(mock.flow.resume).toHaveBeenCalledOnce();}
 if(appointment_state==='confirmed')expect(host.textContent).toContain('meeting link is being prepared');
 if(payment_state==='needs_attention')expect(host.textContent).toContain('before making another payment');
});
test('saved receipt access persists across pending, refunded, ready and cooling-down displays',async()=>{
 mock.flow.canRetryOriginal=true;await render({credential:{request_id:id},receipt:null,phase:'checking'});expect($('#receipt-title').textContent).toContain('Checking');await click(button('Retry the same'));expect(mock.flow.retryOriginal).toHaveBeenCalledOnce();await click(button('Check your booking'));
 await render({receipt:receipt({appointment_state:'confirmed',captured_paise:250000,refunded_paise:250000,meet_url:'https://meet.google.com/abc-defg-hij',meeting_state:'ready',next_actions:['choose_new_time']}),phase:'receipt'});expect(host.textContent).toContain('Refunded');expect($('a[href="https://meet.google.com/abc-defg-hij"]').rel).toContain('noopener');await click(button('Choose a new time'));expect(mock.flow.restart).toHaveBeenCalledOnce();
 await render({busy:true});expect(button('Checking…').disabled).toBe(true);await render({busy:false,phase:'payment'});expect(button('Check booking status').disabled).toBe(true);expect(host.textContent).toContain('payment window is open');
 await render({phase:'receipt',retryAt:Date.now()+15000});expect(host.textContent).toContain('wait 15 seconds');expect(button('Check booking status').disabled).toBe(true);await act(async()=>vi.advanceTimersByTimeAsync(15000));expect(button('Check booking status').disabled).toBe(false);
 await render({receipt:receipt({hold_expires_at:'2030-01-01T08:00:00Z'})});expect($('#hold-clock')).toBeNull();expect(button('Continue to payment').disabled).toBe(true);
 await render({credential:null,receipt:null,phase:'draft'});expect($('#receipt')).toBeNull();
});
