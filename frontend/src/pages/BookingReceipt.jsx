import {useState} from 'react';
import BookingOrnament from '../site/BookingOrnament.jsx';
import {useBooking} from '../booking/useBooking.jsx';
import {ReceiptFields,BookingDetailsFields} from '../booking/booking-ui.jsx';
import {bookingBrowser} from '../booking/browser.mjs';
import '../booking/booking.css';

function SavedReceipt({onFind}){
 const flow=useBooking(),{state,check}=flow;
 return <div className="booking-saved-access">
  <p>This checks the booking saved in this browser.</p><ReceiptFields flow={flow}/>
  {!state.credential&&<p role="status">No receipt is saved here. Use your full name and phone number to find your booking.</p>}
  {state.error&&<p role="alert">{state.error}</p>}
  <div className="booking-access-actions"><button type="button" disabled={!flow.available||state.busy||!state.credential} onClick={check}>{state.busy?'Checking…':'Refresh saved booking'}</button>
   <button type="button" onClick={onFind}>Find my bookings</button></div>
 </div>;
}
export default function BookingReceipt(){
 const [hasSaved]=useState(()=>{try{return !!bookingBrowser.receipts.readReceipt(window.sessionStorage);}catch{return false;}});
 const [mode,setMode]=useState(hasSaved?'saved':'find');
 return <div className="sarsa-booking booking-access-shell"><section className="sarsa-booking-receipt booking-access-page" aria-labelledby="booking-access-title">
  {mode==='saved'&&<><p className="booking-access-eyebrow">Your appointments</p><h1 id="booking-access-title">View my booking</h1></>}
  {hasSaved&&<div className="booking-access-selector" role="group" aria-label="How to open your booking">
   <button type="button" aria-pressed={mode==='saved'} onClick={()=>setMode('saved')}>Saved in this browser</button>
   <button type="button" aria-pressed={mode==='find'} onClick={()=>setMode('find')}>Find with name & phone</button>
  </div>}
  {mode==='saved'&&<SavedReceipt onFind={()=>setMode('find')}/>}
  <BookingDetailsFields active={mode==='find'} introduction={<><p className="booking-access-eyebrow">Your appointments</p><h1 id="booking-access-title">View my booking</h1><p>Apni booking ki jaankari, yahin.</p><p>Use the same full name and phone number you entered when booking. Your appointments and meeting details will appear here.</p><BookingOrnament/></>}/>
 </section></div>;
}
