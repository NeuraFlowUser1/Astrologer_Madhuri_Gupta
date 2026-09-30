import { reducer } from './state.mjs';
import { useCallback, useEffect, useReducer, useRef } from 'react';
import { api, checkedPolicy, checkedAvailability, checkedReceipt, checkedCheckout, readReceipt, prepareReceipt,
  clearReceipt, indiaDate, messageFor, rejectedWithoutBooking, SERVICE_IDS, BookingError } from './protocol.mjs';
import { loadRazorpay, openRazorpay } from './razorpay.mjs';

function initial(service) {
  let credential = null, error = '', blocked = false;
  try { credential = readReceipt(window.sessionStorage); }
  catch { error = messageFor(new BookingError('receipt_unavailable')); blocked = true; }
  return { service:SERVICE_IDS.includes(service) ? service : 'kundli-prediction', day:indiaDate(), slot:null,
    policy:null, loadingPolicy:true, slots:[], slotsStatus:'idle', credential, receipt:null,
    phase:blocked ? 'blocked' : credential ? 'checking' : 'draft', error, busy:false, ack:false, retryAt:0,
    details:{full_name:'',email:'',phone:'',country:'91',notes:''} };
}
export function useBooking(initialService) {
  const [state, dispatch] = useReducer(reducer, initialService, initial);
  const stateRef = useRef(state); stateRef.current = state;
  const busy = useRef(false), attempt = useRef(null), mounted = useRef(true), closePayment = useRef(null);
  const pollCount = useRef(0);
  const send = useCallback(action => { if (mounted.current) dispatch(action); }, []);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; closePayment.current?.(); }; }, []);
  useEffect(() => {
    if (SERVICE_IDS.includes(initialService)) send({type:'edit',name:'service',value:initialService});
  }, [initialService,send]);
  const fail = useCallback(error => send({type:'error',message:messageFor(error), retryAt:Date.now()+(error.retryAfter || 0)*1000}), [send]);
  const loadPolicy = useCallback(async () => {
    try { send({type:'policy',value:checkedPolicy(await api('/api/booking-policy'))}); }
    catch (error) { send({type:'policy-error',message:messageFor(error)}); }
  }, [send]);
  useEffect(() => { loadPolicy(); }, [loadPolicy]);
  useEffect(() => {
    if (!state.policy || state.credential || !state.day || state.phase === 'blocked') return;
    const controller = new AbortController(); const {service,day,policy} = state;
    dispatch({type:'slots-loading'});
    api(`/api/availability?service_id=${encodeURIComponent(service)}&day=${encodeURIComponent(day)}`, {signal:controller.signal})
      .then(value => { if (!controller.signal.aborted) send({type:'slots',service,day,
        value:checkedAvailability(value,service,day,policy.quote_version)}); })
      .catch(error => { if (!controller.signal.aborted) send({type:'slots-error',service,day,message:messageFor(error)}); });
    return () => controller.abort();
  }, [state.service,state.day,state.policy,state.credential,state.phase === 'blocked',send]);

  const operation = useCallback(async work => {
    if (busy.current || stateRef.current.phase === 'payment' || Date.now() < stateRef.current.retryAt) return;
    busy.current = true; send({type:'busy',value:true});
    try { await work(); } catch (error) { fail(error); }
    finally { busy.current = false; send({type:'busy',value:false}); }
  }, [send,fail]);
  const accept = useCallback((value, credential) => {
    const receipt = checkedReceipt(value,credential.request_id);
    send({type:'receipt',value:receipt}); return receipt;
  }, [send]);
  const check = useCallback(() => operation(async () => {
    const c = stateRef.current.credential; if (!c) return;
    accept(await api('/api/checkout/status',{body:{request_id:c.request_id},credential:c}),c);
  }), [operation,accept]);
  // Restored receipts never need a fresh context cookie or another reservation.
  useEffect(() => { if (state.credential) check(); }, []); // intentionally once per page visit
  useEffect(() => {
    if (!state.credential || state.phase === 'blocked') return;
    const timer = setInterval(() => {
      const current = stateRef.current;
      if (document.visibilityState !== 'visible' || busy.current || current.phase === 'payment' || pollCount.current >= 24) return;
      const r = current.receipt;
      if (r && (['cancelled','payment_review','expired'].includes(r.appointment_state)
          || (r.appointment_state === 'confirmed' && r.meeting_state === 'ready'))) return;
      if (Date.now() < current.retryAt) return;
      pollCount.current += 1; check();
    },5000);
    return () => clearInterval(timer);
  },[state.credential,check]);

  const showPayment = useCallback(async (result, credential) => {
    checkedCheckout(result,credential.request_id); accept(result.receipt,credential);
    if (!result.checkout || !mounted.current) return;
    try {
      await loadRazorpay();
      if (!mounted.current) return;
      send({type:'modal'});
      closePayment.current = openRazorpay(result.checkout, {
        onSuccess: async signed => {
          // Do not let polling/dismissal race the explicit signed callback.
          busy.current = true; send({type:'busy',value:true}); send({type:'receipt',value:result.receipt});
          try { const response = await api('/api/checkout/verify-payment',{
            credential,body:{request_id:credential.request_id,...signed}}); accept(response.receipt,credential); }
          catch (error) { fail(error); }
          finally { busy.current = false; send({type:'busy',value:false}); }
        },
        onClose: () => { send({type:'receipt',value:result.receipt});
          // React commits the closed state before starting the read-only check.
          setTimeout(() => { if (mounted.current) check(); },0); },
      });
    } catch { send({type:'receipt',value:result.receipt}); throw new BookingError('payment_unavailable'); }
  },[accept,send,fail,check]);
  const start = useCallback(() => operation(async () => {
    const s = stateRef.current;
    if (s.credential || !s.policy || !s.slot || !s.ack || s.phase === 'blocked') return;
    if (!mounted.current) return;
    const context = await api('/api/checkout-context',{body:{}});
    if (context?.ready !== true) throw new BookingError('invalid_response');
    if (!mounted.current) return;
    const c = prepareReceipt(window.sessionStorage);
    const phone = s.details.country === 'other' ? s.details.phone.trim()
      : '+'+s.details.country+s.details.phone.replace(/[\s()-]/g,'');
    const payload = {request_id:c.request_id,normalization_version:2,full_name:s.details.full_name.trim(),
      email:s.details.email.trim(),phone,service_id:s.service,quote_version:s.policy.quote_version,
      starts_at:s.slot.starts_at,notes:s.details.notes.trim()};
    attempt.current = {credential:c,payload}; send({type:'lock',value:c});
    try { await showPayment(await api('/api/checkout',{body:payload,credential:c}),c); }
    catch (error) {
      if (rejectedWithoutBooking(error.code)) {
        clearReceipt(window.sessionStorage,c); attempt.current = null;
        send({type:'rejected',message:messageFor(error)});
        if (error.code === 'quote_changed') await loadPolicy();
      } else throw error;
    }
  }),[operation,send,showPayment,loadPolicy]);
  const retryOriginal = useCallback(() => operation(async () => {
    const saved = attempt.current; if (!saved) return;
    if (!mounted.current) return;
    try { await showPayment(await api('/api/checkout',{credential:saved.credential,body:saved.payload}),saved.credential); }
    catch(error) {
      if(!rejectedWithoutBooking(error.code))throw error;
      clearReceipt(window.sessionStorage,saved.credential);attempt.current=null;
      send({type:'rejected',message:messageFor(error)});
      if(error.code==='quote_changed')await loadPolicy();
    }
  }),[operation,showPayment,send,loadPolicy]);
  const resume = useCallback(() => operation(async () => {
    const s = stateRef.current, c = s.credential;
    if (!c || !s.receipt?.next_actions.some(a => ['check_payment','resume_payment'].includes(a))) return;
    if (!mounted.current) return;
    const result = await api('/api/checkout/resume',{body:{request_id:c.request_id},credential:c});
    await showPayment(result,c);
    if (result.retry_after) send({type:'error',message:'We are checking the existing payment. Please wait a moment before continuing.',retryAt:Date.now()+15000});
  }),[operation,showPayment,send]);
  const restart = useCallback(() => operation(async () => {
    const s = stateRef.current;
    if (!s.receipt?.next_actions.includes('choose_new_time')) return;
    // Recheck the server permission at the action, not only at render time.
    const current = accept(await api('/api/checkout/status',{
      body:{request_id:s.credential.request_id},credential:s.credential}),s.credential);
    if (!current.next_actions.includes('choose_new_time')) return;
    clearReceipt(window.sessionStorage,s.credential); attempt.current = null; pollCount.current = 0;
    send({type:'reset'});
  }),[operation,accept,send]);
  return {state,dispatch,start,resume,check,restart,retryOriginal,loadPolicy,
    canRetryOriginal:!!attempt.current && !state.receipt};
}
