// @vitest-environment jsdom
import {beforeEach,afterEach,expect,test,vi} from 'vitest';
beforeEach(()=>{vi.resetModules();vi.useFakeTimers();delete window.Razorpay;document.head.innerHTML='';});
afterEach(()=>{vi.useRealTimers();});
test('script loading is shared, uses the official URL and resolves only with a constructor',async()=>{
 const {loadRazorpay}=await import('../../src/booking/razorpay.mjs');const first=loadRazorpay(),second=loadRazorpay();expect(first).toBe(second);expect(document.head.querySelectorAll('script')).toHaveLength(1);expect(document.head.querySelector('script').src).toBe('https://checkout.razorpay.com/v1/checkout.js');window.Razorpay=function(){};document.head.querySelector('script').onload();await first;await loadRazorpay();expect(document.head.querySelectorAll('script')).toHaveLength(1);
});
test.each(['error','missing','timeout'])('failed loading (%s) is bounded, removed and retryable',async mode=>{
 const {loadRazorpay}=await import('../../src/booking/razorpay.mjs');const pending=loadRazorpay();const assertion=expect(pending).rejects.toMatchObject({code:'payment_unavailable'});const script=document.head.querySelector('script');if(mode==='error')script.onerror();else if(mode==='missing')script.onload();else await vi.advanceTimersByTimeAsync(20000);await assertion;expect(document.head.querySelector('script')).toBeNull();const retry=loadRazorpay();const check=expect(retry).rejects.toHaveProperty('code','payment_unavailable');document.head.querySelector('script').onerror();await check;
});
test.each(['success','dismiss','cleanup'])('payment callback remains single-use after %s',async mode=>{
 const {openRazorpay}=await import('../../src/booking/razorpay.mjs');let options;const open=vi.fn(),close=vi.fn();window.Razorpay=function(value){options=value;this.open=open;this.close=close;};const success=vi.fn(),dismiss=vi.fn();const cleanup=openRazorpay({key_id:'rzp_live_synthetic',order_id:'order_synthetic',amount_paise:100,currency:'INR'},{onSuccess:success,onClose:dismiss});expect(open).toHaveBeenCalledOnce();expect(options).not.toHaveProperty('prefill');
 const signed={razorpay_order_id:'order_synthetic',razorpay_payment_id:'pay_synthetic',razorpay_signature:'signature',private_bank_data:'must not escape'};
 if(mode==='success')options.handler(signed);if(mode==='dismiss')options.modal.ondismiss();if(mode==='cleanup')cleanup();options.handler(signed);options.modal.ondismiss();expect(success).toHaveBeenCalledTimes(mode==='success'?1:0);expect(dismiss).toHaveBeenCalledTimes(mode==='dismiss'?1:0);if(mode==='success')expect(success.mock.calls[0][0]).toEqual({razorpay_order_id:'order_synthetic',razorpay_payment_id:'pay_synthetic',razorpay_signature:'signature'});if(mode==='cleanup')expect(close).toHaveBeenCalledOnce();
});
