import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {MemoryRouter,Routes,Route} from 'react-router-dom';
import {beforeEach,afterEach,test,expect,vi} from 'vitest';
const mock=vi.hoisted(()=>({pdf:null,restore:vi.fn(),start:vi.fn(()=>()=>{}),state:{reference:'',restored:false,busy:false,blocked:false,error:''},notify:null}));
vi.mock('../../src/booking/browser.mjs',()=>({bookingBrowser:{receiptRecovery:()=>({getSnapshot:()=>mock.state,subscribe:fn=>{mock.notify=fn;return()=>{};},start:mock.start,restore:mock.restore})}}));
vi.mock('../../../appointment-system/browser/booking/receipt-fields.mjs',()=>({createReceiptFields:(_React,options)=>{mock.pdf=options.loadPDF;return()=>null;}}));
vi.mock('pdf-lib',()=>({PDFDocument:'synthetic-pdf-library'}));
vi.mock('@pdf-lib/fontkit',()=>({default:'synthetic-font-loader'}));
import BookingAccess from '../../src/pages/BookingAccess.jsx';
import {DateField} from '../../src/booking/booking-ui.jsx';
let root,host;
beforeEach(()=>{globalThis.IS_REACT_ACT_ENVIRONMENT=true;mock.state={reference:'',restored:false,busy:false,blocked:false,error:''};mock.restore.mockClear();mock.start.mockClear();host=document.createElement('div');document.body.append(host);root=createRoot(host);vi.stubGlobal('ResizeObserver',class{observe(){}disconnect(){}});vi.stubGlobal('matchMedia',()=>({matches:false,addEventListener(){},removeEventListener(){}}));});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.unstubAllGlobals();});
async function change(node,value){Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(node,value);await act(async()=>node.dispatchEvent(new Event('input',{bubbles:true})));}
test('receipt restoration keeps the saved reference, clears the entered code and redirects only on confirmed success',async()=>{
 await act(async()=>root.render(<MemoryRouter initialEntries={['/booking-help']}><Routes><Route path="/booking-help" element={<BookingAccess/>}/><Route path="/booking/receipt" element={<h1>Existing receipt</h1>}/></Routes></MemoryRouter>));
 const [reference,code]=host.querySelectorAll('input');await change(reference,'11111111-1111-4111-8111-111111111111');await change(code,'12345678');await act(async()=>host.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));expect(mock.restore).toHaveBeenCalledWith(reference.value,'12345678');expect(code.value).toBe('');mock.state={...mock.state,busy:true,error:'Synthetic unavailable'};await act(async()=>mock.notify());expect(host.querySelector('button').disabled).toBe(true);expect(host.textContent).toContain('Synthetic unavailable');mock.state={...mock.state,busy:false,blocked:true};await act(async()=>mock.notify());expect(reference.disabled).toBe(true);mock.state={...mock.state,restored:true};await act(async()=>mock.notify());expect(host.textContent).toContain('Existing receipt');
});
test('date field remains readable during a product recheck',async()=>{
 await act(async()=>root.render(<DateField label="Appointment date" name="appointmentDate" value="2030-01-02" min="2030-01-01" max="2030-01-10" available checking disabled onChange={vi.fn()}/>));expect(host.textContent).toContain('Appointment date');expect(host.querySelector('[data-disabled]')).toBeNull();
});
test('PDF dependencies reject failed, empty and oversized font responses; success is cached',async()=>{
 for(const response of [{ok:false},{ok:true,arrayBuffer:async()=>new ArrayBuffer(0)},{ok:true,arrayBuffer:async()=>new ArrayBuffer(1048577)}]){vi.stubGlobal('fetch',vi.fn(async()=>response));await expect(mock.pdf()).rejects.toThrow('pdf_unavailable');}
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,arrayBuffer:async()=>new Uint8Array([1,2,3]).buffer})));const result=await mock.pdf();expect(result.fontBytes).toEqual(new Uint8Array([1,2,3]));expect(result.PDFDocument).toBe('synthetic-pdf-library');expect(await mock.pdf()).toBe(result);expect(fetch).toHaveBeenCalledOnce();
});
