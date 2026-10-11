import {createBookingDetails,bookingStateLabel} from './booking-details.mjs';
import {createBookingDetailsPDF} from './booking-details-pdf.mjs';
import {createReceiptFacts} from './receipt-fields.mjs';
import {admissionAllowed} from '../product-state.mjs';
import {appointmentLabel} from '../display-formatting.mjs';

export function createBookingDetailsFields(React,{browser,brand,loadPDF,theme=''}){
 const {createElement:h,useEffect,useRef,useSyncExternalStore,useId}=React,ReceiptFacts=createReceiptFacts(React);
 return function BookingDetailsFields({active=true,introduction=null}){
  const instance=useRef(null);if(!instance.current)instance.current=createBookingDetails({product:browser.product});
  const controller=instance.current,state=useSyncExternalStore(controller.subscribe,controller.getSnapshot,controller.getSnapshot);
  const product=useSyncExternalStore(browser.product.subscribe,browser.product.getSnapshot,browser.product.getSnapshot);
  const pdfRef=useRef(null);if(!pdfRef.current)pdfRef.current=createBookingDetailsPDF({controller,product:browser.product,brand,loadPDF});
  const pdf=pdfRef.current,file=useSyncExternalStore(pdf.subscribe,pdf.getSnapshot,pdf.getSnapshot);
  const refs=useRef(new Map()),prefix=useId(),id=name=>prefix+'-'+name;
  const ref=name=>node=>{if(node)refs.current.set(name,node);else refs.current.delete(name);};
  useEffect(()=>controller.start(),[controller]);
  useEffect(()=>pdf.start(),[pdf]);
  useEffect(()=>controller.setActive(active),[controller,active]);
  useEffect(()=>{if(active&&state.focusVersion)refs.current.get(state.focusTarget)?.focus();},[active,state.focusVersion,state.focusTarget]);
  const enabled=active && admissionAllowed(product),r=state.receipt,invalid=name=>state.fields.includes(name);
  const field=(name,label,properties)=>h('div',{className:'abs-lookup-field',key:name},
   h('label',{htmlFor:id(name)},label),h('input',{id:id(name),ref:ref(name),name,value:state.input[name],required:true,
    'aria-invalid':invalid(name),'aria-describedby':id(name+'-hint'),...properties,onChange:event=>controller.edit(name,event.target.value)}),
   h('p',{id:id(name+'-hint'),className:invalid(name)?'abs-action-error':'abs-lookup-hint'},name==='full_name'?
    'Use the full name entered when booking.':'Use the phone number entered when booking.'));
  const refresh=async()=>{try{await controller.refresh();}catch{/* The controller displays the safe read error. */}};
  const linkProps={href:file.pdfURL,download:file.filename,onClick:event=>{if(!pdf.canOpen())event.preventDefault();}};
  return h('div',{className:'abs-booking-details abs-receipt '+theme,hidden:!active},
   h('div',{className:'abs-lookup-opening'},active&&introduction?h('div',{className:'abs-lookup-introduction'},introduction):null,
   h('form',{method:'post',action:'/api/booking/details',className:'abs-lookup-form','aria-busy':state.busy,onSubmit:event=>{event.preventDefault();void controller.search();}},
    !introduction?h('p',{className:'abs-lookup-intro'},'Enter your saved full name and phone number to view your appointments and meeting details.'):null,
    h('div',{className:'abs-lookup-inputs'},field('full_name','Full name',{autoComplete:'name',maxLength:100}),
     h('div',{className:'abs-lookup-phone'},h('label',{htmlFor:id('country')},'Country'),
      h('select',{id:id('country'),value:state.input.country,onChange:event=>controller.edit('country',event.target.value)},
       ...[['+91','India (+91)'],['international','Other country — include +code']].map(([value,label])=>h('option',{key:value,value},label))),
      field('phone','Phone number',{type:'tel',inputMode:'tel',autoComplete:'tel',maxLength:32,placeholder:state.input.country==='+91'?'Your saved mobile number':'+country code and number'}))),
    h('button',{type:'submit',disabled:!enabled||state.busy},state.busy?'Finding your booking…':'View my bookings ↗'))),
   h('p',{role:'status','aria-live':'polite',className:'abs-lookup-status'},state.busy?'Checking the saved booking details…':''),
   state.error?h('p',{role:'alert',className:'abs-action-error'},state.error):null,
   state.status!=='idle'?h('section',{className:'abs-lookup-results','aria-labelledby':id('results')},
    h('h2',{id:id('results'),ref:ref('results'),tabIndex:-1},r?'Your appointment details':state.status==='empty'?'No bookings found':'Your bookings'),
    r?h(React.Fragment,null,
     h('p',{className:'abs-lookup-state'},bookingStateLabel(r.appointment_state)),
     state.stale?h('p',{className:'abs-lookup-stale',role:'status'},'These are the last details we could read. Refresh before using a meeting link or downloading a PDF.'):null,
     h(ReceiptFacts,{receipt:r,stale:state.stale||!enabled}),
     h('div',{className:'abs-receipt-actions'},
      h('button',{type:'button',disabled:!enabled||state.busy||file.busy,onClick:refresh},'Refresh details'),
      r.appointment_state==='confirmed'?h('button',{type:'button',disabled:!enabled||state.busy||state.stale||file.busy,onClick:()=>void pdf.pdf()},file.busy?'Preparing PDF…':'Download appointment PDF'):null,
      file.pdfURL?h(React.Fragment,null,h('a',{...linkProps,className:'abs-download'},'Download PDF'),
       h('a',{...linkProps,download:undefined,target:'_blank',rel:'noopener noreferrer',className:'abs-download'},'Open PDF')):null,
      h('button',{type:'button',className:'abs-lookup-back',onClick:controller.back},'Back to my bookings'),
      file.message?h('p',{role:'status'},file.message):null,file.error?h('p',{role:'alert',className:'abs-action-error'},file.error):null)):
     state.status==='empty'?h('p',null,'Check the name and phone number entered when booking, then search again.'):
     h(React.Fragment,null,h('p',null,'Upcoming appointments appear first, followed by earlier appointments.'),
      h('ul',{className:'abs-lookup-list'},...state.items.map(row=>h('li',{key:row.request_id},
       h('button',{type:'button',ref:ref(row.request_id),disabled:!enabled||state.busy,onClick:()=>void controller.open(row.request_id)},
        h('span',{className:'abs-lookup-service'},row.service_name),h('span',{className:'abs-lookup-date'},appointmentLabel(row.starts_at,row.timezone)+' · '+row.timezone),
        h('span',{className:'abs-lookup-state'},bookingStateLabel(row.appointment_state)),h('span',{'aria-hidden':true},'↗'))))),
      state.nextCursor?h('button',{type:'button',disabled:!enabled||state.busy,onClick:()=>void controller.more()},'Show more bookings'):null)):
    null);
 };
}
