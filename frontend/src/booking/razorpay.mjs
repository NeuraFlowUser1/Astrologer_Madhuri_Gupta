/** The only browser payment integration is Razorpay's own checkout. */
import { BookingError } from './protocol.mjs';
let loading;
export function loadRazorpay() {
  if (typeof window.Razorpay === 'function') return Promise.resolve();
  if (loading) return loading;
  loading = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';
    script.async = true;
    const fail = () => { clearTimeout(timer); script.remove(); loading = undefined; reject(new BookingError('payment_unavailable')); };
    const timer = setTimeout(fail, 20000);
    script.onerror = fail;
    script.onload = () => { if (typeof window.Razorpay !== 'function') return fail(); clearTimeout(timer); resolve(); };
    document.head.append(script);
  });
  return loading;
}
export function openRazorpay(checkout, { onSuccess, onClose }) {
  let finished = false;
  const payment = new window.Razorpay({ key:checkout.key_id, order_id:checkout.order_id,
    amount:checkout.amount_paise, currency:checkout.currency, name:'Sarsa Jyotish Sansthan',
    description:'Personal consultation with Madhuri Gupta', theme:{color:'#26483d'},
    handler(result) { if (finished) return; finished = true; onSuccess({
      razorpay_order_id:result.razorpay_order_id, razorpay_payment_id:result.razorpay_payment_id,
      razorpay_signature:result.razorpay_signature }); },
    modal:{ondismiss() { if (!finished) { finished = true; onClose(); } }},
  });
  payment.open();
  return () => { finished = true; payment.close(); };
}
