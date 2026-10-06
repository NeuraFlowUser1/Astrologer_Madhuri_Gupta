// Receipt access uses the common coordinator. This view has no payment action.
import {useBooking} from '../booking/useBooking.jsx';
export default function BookingReceipt(){
 const {state,check}=useBooking();const receipt=state.receipt;
 return <section className="p-8" aria-labelledby="receipt-title"><h1 id="receipt-title">Your existing booking</h1>
  <p>This page checks the booking saved in this browser.</p>
  {receipt && <dl><dt>Booking reference</dt><dd>{receipt.request_id}</dd><dt>Consultation</dt><dd>{receipt.service_name}</dd><dt>Time</dt><dd>{new Date(receipt.starts_at).toLocaleString('en-IN',{timeZone:receipt.timezone})} · {receipt.timezone}</dd>
   <dt>Appointment</dt><dd>{receipt.appointment_state.replaceAll('_',' ')}</dd><dt>Payment</dt><dd>{receipt.payment_state.replaceAll('_',' ')}</dd>
   <dt>Meeting</dt><dd>{receipt.meet_url ? <a href={receipt.meet_url} rel="noreferrer">Open Google Meet</a>:receipt.meeting_state.replaceAll('_',' ')}</dd></dl>}
  {!state.credential&&<p role="status">This browser has no saved receipt. Contact the practice for help.</p>}
  {state.error && <p role="alert">{state.error}</p>}<button type="button" disabled={state.busy||!state.credential} onClick={check}>{state.busy?'Checking…':'Check status'}</button> · <a href="/booking-help">Get help with receipt access</a> · <a href="/contact">Contact the practice</a>
 </section>;
}
