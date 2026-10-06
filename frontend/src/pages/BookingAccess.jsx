import {useEffect,useMemo,useState,useSyncExternalStore} from 'react';
import {useNavigate} from 'react-router-dom';
import {bookingBrowser} from '../booking/browser.mjs';
export default function BookingAccess(){
 const controller=useMemo(()=>bookingBrowser.receiptRecovery(),[]),navigate=useNavigate();
 const state=useSyncExternalStore(controller.subscribe,controller.getSnapshot,controller.getSnapshot);
 const [reference,setReference]=useState(state.reference),[code,setCode]=useState('');
 useEffect(()=>controller.start(),[controller]);
 useEffect(()=>{if(state.restored)navigate('/booking/receipt',{replace:true});},[state.restored,navigate]);
 return <section className="p-8"><h1>Open your existing booking</h1><p>Use the reference and access code provided by the practice.</p>
  <form onSubmit={event=>{event.preventDefault();const saved=code;setCode('');void controller.restore(reference,saved);}}>
   <label>Booking request reference<input required value={reference} disabled={state.busy||state.blocked} onChange={event=>setReference(event.target.value)} autoComplete="off"/></label>
   <label>Eight-digit access code<input required value={code} disabled={state.busy||state.blocked} onChange={event=>setCode(event.target.value)} pattern="[0-9]{8}" maxLength={8} inputMode="numeric" autoComplete="one-time-code"/></label>
   <button type="submit" disabled={state.busy||state.blocked}>{state.busy?'Checking…':'Open my booking'}</button>
  </form><p role="status">{state.error}</p><a href="/contact">Contact the practice</a>
 </section>;
}
