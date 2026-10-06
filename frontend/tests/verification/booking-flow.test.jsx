// @vitest-environment jsdom
import React, {act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach,beforeEach,expect,test,vi} from 'vitest';
import {policy as samplePolicy,installation_id,epoch} from '../../../appointment-system/tests/booking-browser-fixture.mjs';
import {createReceiptStore} from '../../../appointment-system/browser/booking/credentials.mjs';
const policy=samplePolicy();policy.server_now='2030-01-01T09:00:00Z';
policy.policy.services=[{...policy.policy.services[0],id:'kundli-prediction',name:'Kundli Prediction',pricing:{kind:'fixed',amount_paise:250000,maximum_questions:1}}];
const receipts=createReceiptStore({installation_id,environment:'test'});
const STORAGE_KEY=receipts.storageKey,prepareReceipt=storage=>receipts.prepareReceipt(storage,policy);
const mocks=vi.hoisted(()=>({api:vi.fn(),load:vi.fn(),open:vi.fn(),close:vi.fn()}));
// Test-only API/provider doubles exercise the unchanged shared coordinator.
vi.mock('../../src/booking/browser.mjs',async()=>{
 const {createBookingController}=await import('../../../appointment-system/browser/booking/controller.mjs');
 const {createReceiptStore}=await import('../../../appointment-system/browser/booking/credentials.mjs');
 const {createPaymentRecovery}=await import('../../../appointment-system/browser/booking/payment-recovery.mjs');
 const {installation_id,epoch}=await import('../../../appointment-system/tests/booking-browser-fixture.mjs');
 const receipts=createReceiptStore({installation_id,environment:'test'}),storage=()=>sessionStorage;
 const product={getSnapshot:()=>({enabled:true,activation_epoch:epoch}),subscribe:()=>()=>{}};
 const recovery=createPaymentRecovery({installation_id,environment:'test',receipts,storage,api:mocks.api,enabled:()=>true});
 return {bookingBrowser:{controller:initialService=>createBookingController({api:mocks.api,receipts,storage,product,initialService,
  payment:{load:mocks.load,open:mocks.open,rememberAndSubmit:recovery.rememberAndSubmit}})}};
});
import {useBooking} from '../../src/booking/useBooking.jsx';
import {RequestError as BookingError} from '../../../appointment-system/browser/transport.mjs';

let current,root,host;
const slot={starts_at:'2030-01-02T10:00:00+05:30',ends_at:'2030-01-02T10:30:00+05:30'};
const receipt=(id,changes={})=>({request_id:id,appointment_state:'held',order_state:'ready',payment_state:'unobserved',
 service_name:'Kundli Prediction',currency:'INR',timezone:'Asia/Kolkata',amount_paise:250000,captured_paise:0,refunded_paise:0,
 ...slot,server_now:'2030-01-01T09:00:00Z',hold_expires_at:'2030-01-01T09:10:00Z',next_actions:['resume_payment'],meeting_state:'not_created',meet_url:null,...changes});
const result=(id,checkout=true,changes={})=>({receipt:receipt(id,changes),checkout:checkout?{key_id:'rzp_live_synthetic',order_id:'order_synthetic',amount_paise:250000,currency:'INR'}:null});
async function settle(){await act(async()=>{for(let i=0;i<8;i++)await Promise.resolve();});}
async function mount(service='kundli-prediction'){function Probe(){current=useBooking(service);return null;}await act(async()=>root.render(<Probe/>));await settle();}
async function edit(type,name,value){await act(async()=>current.dispatch({type,name,value}));await settle();}
async function ready(){await edit('edit','day','2030-01-02');await edit('edit','slot',slot);
 for(const [name,value]of Object.entries({full_name:' Synthetic Visitor ',email:' test@example.invalid ',phone:'98765 43210',notes:' Synthetic note '}))await edit('details',name,value);
 await act(async()=>current.dispatch({type:'ack',value:true}));}
beforeEach(()=>{
 globalThis.IS_REACT_ACT_ENVIRONMENT=true;vi.useFakeTimers();vi.setSystemTime(new Date('2030-01-01T09:00:00Z'));
 sessionStorage.clear();host=document.createElement('div');document.body.append(host);root=createRoot(host);current=null;
 mocks.api.mockReset().mockImplementation(async(path,options={})=>{
  if(path==='/api/booking-policy')return structuredClone(policy);
  if(path.startsWith('/api/availability'))return {date:new URL(path,'https://example.invalid').searchParams.get('day'),service:{...policy.policy.services[0],id:current.state.service,questions:1,amount_paise:250000,currency:'INR',quote_version:policy.quote_version,timezone:'Asia/Kolkata'},server_now:'2030-01-01T09:00:00Z',slots:[slot]};
  if(path==='/api/checkout-context')return {ready:true};
  if(path==='/api/checkout'||path==='/api/checkout/resume')return result(options.credential.request_id);
  if(path==='/api/checkout/status')return receipt(options.credential.request_id);
  if(path==='/api/checkout/verify-payment')return result(options.credential.request_id,false,{appointment_state:'confirmed',payment_state:'captured',captured_paise:250000,meeting_state:'ready',meet_url:'https://meet.google.com/abc-defg-hij',next_actions:['check_status']});
  throw Error('Unexpected transport');
 });
 mocks.load.mockReset().mockResolvedValue();mocks.open.mockReset().mockReturnValue(mocks.close);mocks.close.mockReset();
});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.useRealTimers();});

test('checkout normalises details, locks one identity, ignores double clicks and trusts only signed verification',async()=>{
 await mount();await act(async()=>current.start());expect(mocks.open).not.toHaveBeenCalled();await ready();
 await act(async()=>{await Promise.all([current.start(),current.start()]);});await settle();
 const requests=mocks.api.mock.calls.filter(([path])=>path==='/api/checkout');expect(requests).toHaveLength(1);
 expect(requests[0][1].body).toMatchObject({full_name:'Synthetic Visitor',email:'test@example.invalid',phone:'+919876543210',notes:'Synthetic note'});
 expect(current.state.phase).toBe('payment');expect(JSON.parse(sessionStorage.getItem(STORAGE_KEY))).not.toHaveProperty('email');
 await edit('details','email','changed@example.invalid');expect(current.state.details.email).toBe(' test@example.invalid ');
 const signed={razorpay_order_id:'order_synthetic',razorpay_payment_id:'pay_synthetic',razorpay_signature:'a'.repeat(64)};
 await act(async()=>mocks.open.mock.calls[0][1].onSuccess(signed));await settle();
 expect(current.state.receipt.appointment_state).toBe('confirmed');expect(mocks.api.mock.calls.find(([p])=>p.endsWith('verify-payment'))[1].body).toMatchObject(signed);
 await act(async()=>vi.advanceTimersByTimeAsync(15000));expect(mocks.api.mock.calls.filter(([p])=>p.endsWith('/status'))).toHaveLength(0);
});
test('a lost checkout response retries the exact identity and original details',async()=>{
 await mount();await ready();const normal=mocks.api.getMockImplementation();let first=true;
 mocks.api.mockImplementation(async(p,o)=>{if(p==='/api/checkout'&&first){first=false;throw new BookingError('temporarily_unavailable');}return normal(p,o);});
 await act(async()=>current.start());expect(current.canRetryOriginal).toBe(true);const firstCall=mocks.api.mock.calls.find(([p])=>p==='/api/checkout')[1];
 await act(async()=>current.retryOriginal());const calls=mocks.api.mock.calls.filter(([p])=>p==='/api/checkout');expect(calls[1][1].credential).toEqual(firstCall.credential);expect(calls[1][1].body).toEqual(firstCall.body);expect(calls[1][1].signal).not.toBe(firstCall.signal);expect(calls[1][1].signal.aborted).toBe(false);expect(current.state.phase).toBe('payment');
});
test.each(['start','retry'])('a proven price rejection during %s releases only the saved attempt and reloads prices',async phase=>{
 await mount();await ready();const normal=mocks.api.getMockImplementation();let attempts=0;
 mocks.api.mockImplementation(async(p,o)=>{if(p==='/api/checkout'){attempts++;throw new BookingError(phase==='retry'&&attempts===1?'temporarily_unavailable':'quote_changed',{status:phase==='retry'&&attempts===1?503:409});}return normal(p,o);});
 await act(async()=>current.start());if(phase==='retry')await act(async()=>current.retryOriginal());await settle();
 expect(current.state.credential).toBeNull();expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();expect(mocks.api.mock.calls.filter(([p])=>p==='/api/booking-policy')).toHaveLength(2);
});
test('unknown retry errors preserve the receipt; rate advice prevents rapid repeated calls',async()=>{
 vi.spyOn(document,'visibilityState','get').mockReturnValue('hidden');
 await mount();await ready();const normal=mocks.api.getMockImplementation();mocks.api.mockImplementation(async(p,o)=>{if(p==='/api/checkout')throw new BookingError('please_wait',{status:429,retryAfter:15});return normal(p,o);});
 await act(async()=>current.start());const saved=sessionStorage.getItem(STORAGE_KEY);await act(async()=>current.retryOriginal());expect(mocks.api.mock.calls.filter(([p])=>p==='/api/checkout')).toHaveLength(1);
 expect(current.state.error).toContain('wait');expect(current.state.retryAt).toBe(Date.now()+15000);await act(async()=>vi.advanceTimersByTimeAsync(15000));await act(async()=>current.retryOriginal());expect(mocks.api.mock.calls.filter(([p])=>p==='/api/checkout')).toHaveLength(2);expect(sessionStorage.getItem(STORAGE_KEY)).toBe(saved);
});
test('script failure and dismissal retain the booking and check existing payment',async()=>{
 await mount();await ready();mocks.load.mockRejectedValueOnce(Error('blocked script'));await act(async()=>current.start());expect(current.state.phase).toBe('receipt');expect(current.state.error).toContain('payment window');
 await act(async()=>current.resume());expect(current.state.phase).toBe('payment');await act(async()=>mocks.open.mock.calls[0][1].onClose());await act(async()=>vi.advanceTimersByTimeAsync(0));expect(current.state.phase).toBe('receipt');expect(mocks.api.mock.calls.some(([p])=>p.endsWith('/status'))).toBe(true);
});
test('verification failure never confirms locally or replaces the saved receipt',async()=>{
 await mount();await ready();await act(async()=>current.start());const saved=sessionStorage.getItem(STORAGE_KEY);const normal=mocks.api.getMockImplementation();mocks.api.mockImplementation(async(p,o)=>{if(p.endsWith('verify-payment'))throw new BookingError();return normal(p,o);});
 await act(async()=>mocks.open.mock.calls[0][1].onSuccess({razorpay_signature:'synthetic'}));expect(current.state.receipt.appointment_state).toBe('held');expect(sessionStorage.getItem(STORAGE_KEY)).toBe(saved);expect(current.state.busy).toBe(false);
});
test('restored payment checks do not create a new context; restart requires fresh server permission',async()=>{
 const credential=prepareReceipt(sessionStorage);await mount('unknown');expect(current.state.service).toBe('kundli-prediction');expect(current.state.credential).toEqual(credential);expect(mocks.api.mock.calls.some(([p])=>p==='/api/checkout-context')).toBe(false);
 await act(async()=>current.restart());expect(current.state.credential).toEqual(credential);
 const normal=mocks.api.getMockImplementation();mocks.api.mockImplementation(async(p,o)=>p.endsWith('/status')?receipt(credential.request_id,{appointment_state:'expired',next_actions:['choose_new_time']}):normal(p,o));await act(async()=>current.check());
 mocks.api.mockImplementation(async(p,o)=>p.endsWith('/status')?receipt(credential.request_id,{next_actions:['check_payment']}):normal(p,o));await act(async()=>current.restart());expect(current.state.credential).toEqual(credential);
 mocks.api.mockImplementation(async(p,o)=>p.endsWith('/status')?receipt(credential.request_id,{appointment_state:'expired',next_actions:['choose_new_time']}):normal(p,o));await act(async()=>current.check());await act(async()=>current.restart());await settle();expect(current.state.credential).toBeNull();expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
});
test('polling is bounded, skips hidden pages and stops on terminal states',async()=>{
 prepareReceipt(sessionStorage);await mount();mocks.api.mockClear();vi.spyOn(document,'visibilityState','get').mockReturnValue('hidden');await act(async()=>vi.advanceTimersByTimeAsync(10000));expect(mocks.api).not.toHaveBeenCalled();vi.restoreAllMocks();
 await act(async()=>vi.advanceTimersByTimeAsync(150000));expect(mocks.api.mock.calls.filter(([p])=>p.endsWith('/status'))).toHaveLength(24);
});
test('corrupted saved access blocks new payments, and invalid policy/context never launches checkout',async()=>{
 sessionStorage.setItem(STORAGE_KEY,'{broken');await mount();await act(async()=>current.start());expect(current.state.phase).toBe('blocked');expect(mocks.open).not.toHaveBeenCalled();
 await act(async()=>root.unmount());root=createRoot(host);sessionStorage.clear();mocks.api.mockRejectedValue(new BookingError());await mount();expect(current.state.loadingPolicy).toBe(false);expect(current.state.error).not.toBe('');
});
test('availability failures are visible and an invalid checkout context leaves no saved attempt',async()=>{
 const normal=mocks.api.getMockImplementation();mocks.api.mockImplementation(async(p,o)=>p.startsWith('/api/availability')?Promise.reject(new BookingError()):normal(p,o));await mount();expect(current.state.slotsStatus).toBe('error');await ready();mocks.api.mockImplementation(async(p,o)=>p==='/api/checkout-context'?{ready:false}:normal(p,o));await act(async()=>current.start());expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();expect(mocks.open).not.toHaveBeenCalled();
});
