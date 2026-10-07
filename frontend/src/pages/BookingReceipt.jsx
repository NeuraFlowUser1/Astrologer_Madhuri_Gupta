// Receipt access uses the common coordinator. This view has no payment action.
import {useBooking} from '../booking/useBooking.jsx';
import {ReceiptFields} from '../booking/booking-ui.jsx';
import '../booking/booking.css';
export default function BookingReceipt(){
 const flow=useBooking(),{state,check}=flow;
 return <div className="sarsa-booking"><section className="wrap section-space" aria-label="Your existing booking">
  <p>This page checks the booking saved in this browser.</p>
  <ReceiptFields flow={flow}/>
  {!state.credential&&<p role="status">This browser has no saved receipt. Contact the practice for help.</p>}
  {state.error && <p role="alert">{state.error}</p>}<button className="button" type="button" disabled={!flow.available||state.busy||!state.credential} onClick={check}>{state.busy?'Checking…':'Check status'}</button> · <a href="/booking-help">Get help with receipt access</a> · <a href="/contact">Contact the practice</a>
 </section></div>;
}
