import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach,afterEach,test,expect,vi} from 'vitest';
import business from '../../../appointment-settings/business-settings.json';
const mock=vi.hoisted(()=>({flow:null,go:vi.fn(),dispose:vi.fn(),header:{current:null}}));
vi.mock('../../src/booking/useBooking.jsx',()=>({useBooking:()=>mock.flow}));
vi.mock('../../src/booking/booking-layout.mjs',()=>({mountBookingLayout:()=>({go:mock.go,dispose:mock.dispose})}));
vi.mock('../../src/booking/booking-ui.jsx',()=>({
 DateField:({label,name='birth_date',value,required,onChange,disabled})=><label>{label}<input aria-label={label} name={name} value={value} required={required} disabled={disabled} onChange={e=>onChange(e.target.value)}/></label>,
 BirthTimeField:({label,value,required,onChange})=><label>{label}<input aria-label={label} value={value} required={required} onChange={e=>onChange(e.target.value)}/></label>,ReceiptFields:()=> <p>Receipt information</p>}));
import Booking from '../../src/pages/Booking.jsx';
import BookingReceipt from '../../src/pages/BookingReceipt.jsx';
let root,host;
const slot={starts_at:'2030-01-02T10:00:00+05:30',ends_at:'2030-01-02T10:30:00+05:30'};
const render=async(page=<Booking/>)=>act(async()=>root.render(<MemoryRouter>{page}</MemoryRouter>));
const click=node=>act(async()=>node.click());
const button=text=>[...host.querySelectorAll('button')].find(n=>n.textContent.includes(text));
async function change(selector,value){const node=host.querySelector(selector);Object.getOwnPropertyDescriptor(node instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:node instanceof HTMLSelectElement?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set.call(node,value);await act(async()=>node.dispatchEvent(new Event(node.tagName==='SELECT'?'change':'input',{bubbles:true})));}
beforeEach(()=>{
 globalThis.IS_REACT_ACT_ENVIRONMENT=true;window.scrollTo=vi.fn();vi.useFakeTimers();vi.setSystemTime(new Date('2030-01-01T09:00:00Z'));host=document.createElement('div');document.body.append(host);root=createRoot(host);mock.go.mockClear();mock.dispose.mockClear();
 mock.flow={available:true,viewAvailable:true,state:{service:'kundli-prediction',questions:1,day:'2030-01-02',slot:null,policy:{policy:structuredClone(business),server_now:"2030-01-01T09:00:00Z"},policyFresh:true,slotsFresh:true,slots:[slot],slotsStatus:'ready',credential:null,receipt:null,phase:'draft',error:'',busy:false,ack:false,retryAt:0,details:{full_name:'',email:'',phone:'',country:'91',notes:'',birth_date:'',birth_time:'',birth_place:''}},dispatch:vi.fn(),start:vi.fn(),resume:vi.fn(),check:vi.fn(),restart:vi.fn(),retryOriginal:vi.fn(),loadPolicy:vi.fn(),canRetryOriginal:false};
});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.useRealTimers();vi.restoreAllMocks();});
test('one frame adapter preserves optional email and blocks review before a selected time',async()=>{
 await render();expect(host.querySelectorAll('.site-header')).toHaveLength(1);expect(host.querySelectorAll('.site-footer')).toHaveLength(1);expect(host.querySelector('#email').required).toBe(false);expect(host.querySelector('#phone').required).toBe(true);await click(button('Review'));expect(mock.go).toHaveBeenLastCalledWith('appointment');await act(async()=>host.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));expect(mock.flow.dispatch).toHaveBeenCalledWith({type:'error',message:'Please choose an available time first.'});expect(mock.flow.start).not.toHaveBeenCalled();
 mock.flow.state.slot=slot;mock.flow.state.ack=true;await render();const validity=vi.spyOn(HTMLFormElement.prototype,'reportValidity').mockReturnValue(false);mock.go.mockClear();await click(button('Review'));expect(mock.go).not.toHaveBeenCalled();validity.mockReturnValue(true);await click(button('Review'));expect(mock.go).toHaveBeenLastCalledWith('review');await act(async()=>host.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));expect(mock.flow.start).toHaveBeenCalledOnce();
});
test('email-code mode, required preparation and per-question pricing retain existing contracts',async()=>{
 const p=mock.flow.state.policy.policy;p.booking_verification.email=true;p.services.find(s=>s.id==='kundli-prediction').required_preparation=['birth_date','birth_time','birth_place','notes'];const s=p.services.find(s=>s.id==='numerology');s.pricing={kind:'per_question',amount_paise:10000,maximum_questions:3};mock.flow.state.service='kundli-prediction';await render();expect(host.querySelector('#email').required).toBe(true);expect(host.textContent).toContain('Send email code');await change('input[aria-label="Birth date"]','2000-01-01');await change('input[aria-label="Birth time"]','10:00');await change('#birth_place','Agra');
 mock.flow.state.service='numerology';mock.flow.state.questions=2;await render();await change('#question-count','3');expect(mock.flow.dispatch).toHaveBeenCalledWith({type:'edit',name:'questions',value:3});expect(host.textContent).toContain('₹200');
});
test('service radio pointer and keyboard navigation dispatch once and keep browser arrow selection',async()=>{
 await render();const radio=host.querySelector('input[value="numerology"]');await click(radio);expect(mock.flow.dispatch).toHaveBeenCalledWith({type:'edit',name:'service',value:'numerology'});expect(mock.go).toHaveBeenLastCalledWith('appointment');mock.go.mockClear();await act(async()=>radio.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true})));await click(radio);expect(mock.go).not.toHaveBeenCalled();await act(async()=>radio.dispatchEvent(new KeyboardEvent('keyup',{key:'ArrowRight',bubbles:true})));await act(async()=>radio.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true})));expect(mock.go).toHaveBeenCalled();await act(async()=>radio.dispatchEvent(new Event('pointerdown',{bubbles:true})));await act(async()=>radio.dispatchEvent(new KeyboardEvent('keydown',{key:' ',repeat:true,bubbles:true,cancelable:true})));
});
test('all personal fields, acknowledgement, slot and date keep their dispatch contracts',async()=>{
 await render();for(const [id,value] of [['full_name','Test Visitor'],['email','test@example.invalid'],['phone','9876543210'],['notes','Test question']])await change('#'+id,value);await change('select','other');await change('input[name="appointmentDate"]','2030-01-03');await click(host.querySelector('input[name="time"]'));await click(host.querySelector('.acknowledgement input'));expect(mock.flow.dispatch).toHaveBeenCalledWith({type:'edit',name:'day',value:'2030-01-03'});expect(mock.flow.dispatch).toHaveBeenCalledWith({type:'ack',value:true});mock.flow.state.details.country='other';mock.flow.state.details.notes='Saved question';mock.flow.state.slot=slot;await render();expect(host.querySelector('#phone').pattern).toContain('\\+');for(const n of host.querySelectorAll('.edit-button'))await click(n);for(const word of ['Fill your details','← Service','← Date & time'])await click(button(word));
});
test.each(['loading','error','ready','idle'])('availability %s does not invent available times',async(slotsStatus)=>{
 mock.flow.state.slotsStatus=slotsStatus;mock.flow.state.slots=[];await render();expect(host.querySelectorAll('input[name="time"]')).toHaveLength(0);if(slotsStatus==='error'){await click(button('Check available times'));expect(mock.flow.loadPolicy).toHaveBeenCalled();}
});
test('missing policy, recheck and blocked modes retain a safe readable form',async()=>{
 mock.flow.state.policy=null;mock.flow.state.error='Service details unavailable';mock.flow.state.service='';await render();await click(button('Reload service details'));expect(mock.flow.loadPolicy).toHaveBeenCalled();await click(button('Review'));expect(mock.go).toHaveBeenLastCalledWith('service');mock.flow.available=false;await render();expect(host.textContent).toContain('Your details are kept');mock.flow.state.phase='blocked';await render();expect(host.querySelector('fieldset').disabled).toBe(true);
});
test.each(['held','payment_review','confirmed'])('saved %s receipt routes every navigation to review and preserves its own actions',async(appointment_state)=>{
 mock.flow.state.credential={request_id:'synthetic'};mock.flow.state.receipt={appointment_state,server_now:new Date().toISOString(),hold_expires_at:new Date(Date.now()+600000).toISOString(),next_actions:['resume_payment','choose_new_time']};mock.flow.canRetryOriginal=true;await render();await click(button('Service'));expect(mock.go).toHaveBeenLastCalledWith('review');for(const text of ['Check booking status','Continue to payment','Choose a new time','Retry the same'])await click(button(text));expect(mock.flow.check).toHaveBeenCalled();if(appointment_state==='held'){await act(async()=>vi.advanceTimersByTimeAsync(1000));expect(host.textContent).toContain('9:59');}mock.flow.state.phase='payment';await render();expect(host.textContent).toContain('secure payment window');mock.flow.state.credential=null;await render();
});
test('receipt pending view has no invented status; separate receipt page preserves access help and busy state',async()=>{
 mock.flow.state.credential={request_id:'synthetic'};await render();expect(host.textContent).toContain('Checking your saved booking');mock.flow.state.credential=null;mock.flow.state.error='Unavailable';await render(<BookingReceipt/>);expect(host.textContent).toContain('no saved receipt');expect(button('Check status').disabled).toBe(true);mock.flow.state.credential={request_id:'synthetic'};await render(<BookingReceipt/>);await click(button('Check status'));expect(mock.flow.check).toHaveBeenCalled();mock.flow.state.busy=true;await render(<BookingReceipt/>);expect(button('Checking').disabled).toBe(true);
});
