import {checkedReceipt,appointmentLabel,money} from './protocol.mjs';

/** Only the facts printed in the document participate in its freshness check. */
export const pdfFacts=receipt=>JSON.stringify(['request_id','booking_revision','appointment_state','service_name',
 'starts_at','ends_at','timezone','amount_paise','captured_paise','refunded_paise','currency','meeting_mode','meeting_state','meet_url']
 .map(key=>receipt[key]??null));

export async function buildAppointmentPDF(receipt,{brand,load,generatedAt=new Date()}){
 const r=checkedReceipt(receipt,receipt.request_id);
 if(r.appointment_state!=='confirmed' || !r.booking_revision || !r.meeting_mode)throw Error('receipt_changed');
 if(typeof brand!=='string' || !brand.trim() || brand.length>150)throw Error('pdf_unavailable');
 const {PDFDocument,PDFName,PDFString,fontkit,fontBytes}=await load();
 if(!(fontBytes instanceof Uint8Array) || !fontBytes.length || fontBytes.length>1048576)throw Error('pdf_unavailable');
 const document=await PDFDocument.create();document.registerFontkit(fontkit);
 const font=await document.embedFont(fontBytes,{subset:true});
 const supported=new Set(font.getCharacterSet());
 const lines=[['Appointment details',20],[brand,16],[r.service_name,16],
  ['Appointment: '+appointmentLabel(r.starts_at,r.timezone),12],['Time zone: '+r.timezone,12],
  ['Duration: '+Math.round((Date.parse(r.ends_at)-Date.parse(r.starts_at))/60000)+' minutes',12],
  ['Agreed fee: '+money(r.amount_paise),12],['Payment recorded: '+money(r.captured_paise),12],
  ['Refund recorded: '+money(r.refunded_paise),12],['Booking reference: '+r.request_id,10],
  [r.meeting_mode==='internal'?'Meeting: contact the practice for the arrangements.':r.meet_url?
   'Google Meet: '+r.meet_url:r.meeting_state==='needs_attention'?
   'Meeting link needs attention. Please contact the practice.':'Meeting link is being prepared. Download again later for the link.',12],
  ['Generated: '+generatedAt.toISOString(),10],['Appointment details only. This document is not a tax invoice.',10]];
 for(const [line] of lines)for(const character of line)if(!supported.has(character.codePointAt(0)))throw Error('pdf_font_unavailable');
 let page,y;const margin=40,width=595.28,height=841.89,available=width-margin*2;
 function newPage(){page=document.addPage([width,height]);y=height-margin;}
 function wrap(text,size){
  const result=[];let current='';
  for(const word of text.split(/\s+/)){
   const candidate=current?current+' '+word:word;
   if(font.widthOfTextAtSize(candidate,size)<=available){current=candidate;continue;}
   if(current){result.push(current);current='';}
   for(const character of word){if(current && font.widthOfTextAtSize(current+character,size)>available){result.push(current);current='';}current+=character;}
  }
  if(current)result.push(current);return result;
 }
 newPage();
 for(const [line,size] of lines){
  for(const part of wrap(line,size)){
   if(y-size*1.45<margin)newPage();y-=size*1.45;
   page.drawText(part,{x:margin,y,size,font});
   if(r.meet_url && part.includes(r.meet_url)){
    const start=part.indexOf(r.meet_url),x=margin+font.widthOfTextAtSize(part.slice(0,start),size);
    const annotation=document.context.register(document.context.obj({Type:'Annot',Subtype:'Link',
     Rect:[x,y-2,x+font.widthOfTextAtSize(r.meet_url,size),y+size],Border:[0,0,0],
     A:{Type:'Action',S:'URI',URI:PDFString.of(r.meet_url)}}));
    // This module owns each page, so there are no pre-existing annotations.
    page.node.set(PDFName.of('Annots'),document.context.obj([annotation]));
   }
  }
  y-=8;
 }
 const bytes=await document.save();
 return {bytes,filename:'appointment-'+r.request_id+'.pdf'};
}
