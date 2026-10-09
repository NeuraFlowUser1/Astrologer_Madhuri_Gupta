import {useBookingProduct,BookingNavigationLink} from '../site/BookingProduct.jsx';
import {Link} from 'react-router-dom';
import '../site/public-pages.css';
const policies={
 privacy:{title:'Your information, handled with care.',sections:[
 ['What we collect','When you book or send an enquiry, we collect the details you provide, such as your name, email address, mobile number, selected consultation, appointment time and message. Please avoid including sensitive personal information in an initial enquiry.'],
 ['How we use it','We use these details to arrange and manage consultations, respond to enquiries, handle payment or appointment issues, and maintain booking records. Booking emails are service messages.'],
 ['The services involved','The website is hosted on Vercel. Booking records are stored in Neon. Google services support staff sign-in, calendars, Google Meet and record copies. The Contact page uses a Google Maps embed. Loading or using the map contacts Google. Resend delivers service emails, and Cloudflare supports background processing. Razorpay processes appointment payments and refunds. Card and bank credentials are entered with the payment provider, not in this website’s booking form.'],
 ['Practice and agency records','The practice maintains its client records through sarsajyotish@gmail.com. NeuraFlow supports the website and maintains a separate agency record copy through neuraflowindia@gmail.com. These records identify Sarsa Jyotish Sansthan separately from other clients. Access is restricted to the relevant authorised roles.'],
 ['Cookies and saved access','Essential cookies support secure requests and staff sign-in. Your browser’s session storage holds private access credentials for your current booking or enquiry so you can check its progress without creating another request. Do not share those credentials or a device with an open session. A booking email address is required when the email-code check is enabled. When that check is disabled, it is optional. Mobile number remains required for a booking. Enquiry forms require an email address for verification.'],
 ['Encrypted backups','An encrypted copy of the website’s booking database is backed up daily to a dedicated folder in the practice’s Google Drive. Backups support recovery if records are lost or damaged. Access to the copies and the separately held recovery key is restricted. Removing a live record does not immediately remove it from previously created backups; contact the practice about retention and deletion requests.'],
 ['Corrections and privacy requests','Contact sarsajyotish@gmail.com to request a correction or ask about the information held about you. Staff may verify your identity before changing booking details or restoring access. Some payment, security and audit records may need to be retained to resolve transactions or meet applicable obligations. Contact the practice about retention and deletion requests.']
 ]},
 terms:{title:'A clear understanding, before we begin.',sections:[
 ['The consultation','Sarsa Jyotish Sansthan offers consultations with Madhuri Gupta. Please select the service that matches your questions and review its price and duration before payment. Online consultations use Google Meet.'],
 ['Your details','Provide an accurate mobile number. A booking email address is required when the email-code check is enabled and optional when it is disabled. Check your details carefully so the practice can contact you about your appointment.'],
 ['Booking and payment','A selected time is not a confirmed appointment. Confirmation depends on the system verifying the payment and securing the appointment. If payment is interrupted or its outcome is unclear, check your saved booking before starting again. An email or meeting link may arrive after confirmation; the booking status and delivery status are shown separately.'],
 ['What a consultation can offer','Consultations provide a perspective for personal consideration. They do not guarantee any particular outcome and do not replace qualified medical, legal or financial advice. Your decisions remain your own.'],
 ['Changes and support','The booking policy explains cancellation, rescheduling and refund requests. Contact sarsajyotish@gmail.com with your booking reference if you need help. Do not send payment passwords, verification codes or card details.']
 ]},
 'booking-policy':{title:'Plans can change. Here is how we help.',sections:[
 ['Appointment times','Appointment times are shown in India time (Asia/Kolkata). The booking page shows the available times, consultation fee and duration. Online appointments take place on Google Meet.'],
 ['Cancellation','Cancellation requests made at least 24 hours before the appointment qualify for a full refund. For requests made closer to the appointment, contact the practice for review. Cancelling an appointment and completing a refund are separate steps.'],
 ['Rescheduling','Please request a change at least 12 hours before your appointment where possible. For a request made less than 12 hours before the appointment, one complimentary move within 14 days is available, subject to availability. Further changes and cases requiring an exception are reviewed by staff.'],
 ['Refund timing','Approved refunds are expected to take 5–7 business days to process; the time funds reach your account depends on the payment provider and bank. Completed consultations and delivered Prashna services are not refundable. No Prashna service is offered in this website’s current booking catalogue.'],
 ['How to request help','Email sarsajyotish@gmail.com with your booking reference and the change you need. Staff will review the booking and payment record. To change contact details or restore lost booking access, staff first call the mobile number already saved with the booking and verify payment details. If that number is inaccessible, the request stays with staff for manual review.']
 ]}
};
const offlinePolicies={
 privacy:{title:'Your information. Handled with care.',sections:[
  ['Information you share','When you send an enquiry, the practice receives your name, contact details and message. An emailed code confirms your address before your enquiry reaches the practice.'],
  ['Google Maps','The Contact page uses a Google Maps embed. Loading or using the map contacts Google.'],
  ['How it is used','The practice uses your enquiry to respond and provide support. Its records and a separate NeuraFlow record copy support operation and recovery.'],
  ['Saved information','Information from earlier consultations may remain in protected records and encrypted backups. Contact the practice to request a correction or ask about retention and deletion.'],
  ['Contact','Email sarsajyotish@gmail.com with questions about your information. Do not send payment passwords, verification codes or card details.']
 ]},
 terms:{title:'Terms for the practice and this website.',sections:[
  ['Consultations','Contact Sarsa Jyotish Sansthan directly to discuss a consultation with Madhuri Gupta, including its fee, time and arrangements.'],
  ['Enquiries','Provide accurate contact details so the practice can respond. Sending an enquiry does not reserve an appointment.'],
  policies.terms.sections.find(([title])=>title==='What a consultation can offer'),
  ['Changes and support','Contact sarsajyotish@gmail.com about an existing consultation, cancellation or refund request. The practice will review its records.']
 ]}
};
export default function PolicyPage({policy}){const {enabled}=useBookingProduct();const page=enabled?policies[policy]:(offlinePolicies[policy]||policies[policy]);return <article className="sarsa-public sarsa-policy"><header><p className="eyebrow">{policy.replaceAll('-',' ').toUpperCase()}</p><h1>{page.title}</h1></header>{page.sections.map(([title,text])=><section key={title}><h2>{title}</h2><p>{text}</p></section>)}<nav aria-label="Related policies"><Link to="/privacy">Privacy</Link> · <Link to="/terms">Terms</Link> · <BookingNavigationLink to="/booking-policy">Booking policy</BookingNavigationLink></nav><p>Questions? <a href="mailto:sarsajyotish@gmail.com">Contact the practice</a>.</p></article>;}
