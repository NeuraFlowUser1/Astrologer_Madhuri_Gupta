/** Real PDF library and contained font; no payment, message or provider call. */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {resolve} from 'node:path';
import {randomUUID} from 'node:crypto';
import {buildAppointmentPDF,pdfFacts} from '../browser/booking/receipt-pdf.mjs';
import {receipt} from './booking-browser-fixture.mjs';
const available=!!process.env.BOOKING_BROWSER_NODE_MODULES;
let dependencies;
async function libraries(){
 if(dependencies)return dependencies;
 const require=createRequire(resolve(process.env.BOOKING_BROWSER_NODE_MODULES,'fixture.cjs'));
 const pdf=require('pdf-lib'),fontkit=require('@pdf-lib/fontkit');
 const fontBytes=new Uint8Array(await readFile(new URL('../browser/booking/receipt-assets/source-sans-3-regular.ttf',import.meta.url)));
 return dependencies={...pdf,fontkit,fontBytes};
}
const confirmed=(change={})=>({...receipt(randomUUID()),appointment_state:'confirmed',payment_state:'captured',captured_paise:210000,
 booking_revision:1,meeting_mode:'google_meet',meeting_state:'ready',meet_url:'https://meet.google.com/abc-defg-hij',...change});
async function inspect(bytes){
 const {PDFDocument,PDFName,PDFRawStream,decodePDFRawStream}=await libraries();const doc=await PDFDocument.load(bytes),unicode=new Map(),streams=[];
 for(const [,object] of doc.context.enumerateIndirectObjects())if(object instanceof PDFRawStream){
  const text=Buffer.from(decodePDFRawStream(object).decode()).toString('utf8');streams.push(text);
  for(const section of text.matchAll(/beginbfchar([\s\S]*?)endbfchar/g))for(const pair of section[1].matchAll(/<([0-9A-F]+)>\s*<([0-9A-F]+)>/gi)){
   const value=pair[2].match(/.{4}/g).map(code=>String.fromCharCode(parseInt(code,16))).join('');unicode.set(pair[1].toUpperCase(),value);
  }
 }
 const lines=[];for(const stream of streams)for(const match of stream.matchAll(/<([0-9A-F]+)>\s*Tj/gi))
  lines.push(match[1].match(/.{4}/g).map(code=>unicode.get(code.toUpperCase())||'').join(''));
 const links=[];for(const page of doc.getPages()){
  const annotations=page.node.lookupMaybe(PDFName.of('Annots'),(await libraries()).PDFArray);
  if(annotations)for(let i=0;i<annotations.size();i++){
   const action=doc.context.lookup(annotations.get(i)).lookup(PDFName.of('A'));links.push(action.lookup(PDFName.of('URI')).decodeText());
  }
 }
 return {doc,lines,links,streams};
}
test('real A4 PDF independently decodes the rupee amounts, reference and safe Meet annotation',{skip:!available},async()=>{
 const r=confirmed(),file=await buildAppointmentPDF(r,{brand:'Synthetic Practice',load:libraries,generatedAt:new Date('2026-10-07T12:00:00Z')}),proof=await inspect(file.bytes);
 assert.equal(proof.doc.getPageCount(),1);const size=proof.doc.getPages()[0].getSize();assert.equal(size.width,595.28);assert.equal(size.height,841.89);
 const text=proof.lines.join('\n');assert.match(text,/Agreed fee: ₹2,100/);assert.match(text,/Payment recorded: ₹2,100/);assert.match(text,/Refund recorded: ₹0/);
 assert.ok(text.includes(r.request_id));assert.ok(text.includes('This document is not a tax invoice.'));
 assert.deepEqual(proof.links,[r.meet_url]);assert.equal(file.filename,'appointment-'+r.request_id+'.pdf');
 for(const forbidden of ['customer@example','r1.current.','razorpay_secret','staff note'])assert.ok(!text.includes(forbidden));
});
test('PDF truth distinguishes practice-arranged, pending and attention meetings without inventing a link',{skip:!available},async()=>{
 for(const [change,wording] of [[{meeting_mode:'internal',meeting_state:'not_created',meet_url:null},'contact the practice for the arrangements'],
  [{meeting_state:'preparing',meet_url:null},'Meeting link is being prepared'],[{meeting_state:'needs_attention',meet_url:null},'Meeting link needs attention']]){
  const file=await buildAppointmentPDF(confirmed(change),{brand:'Synthetic Practice',load:libraries}),proof=await inspect(file.bytes);
  assert.ok(proof.lines.join('\n').includes(wording));assert.deepEqual(proof.links,[]);
 }
});
test('document facts ignore delivery-only changes but include changed appointment, fee, revision and meeting',{skip:!available},()=>{
 const r=confirmed(),original=pdfFacts(r);assert.equal(pdfFacts({...r,acknowledgement_state:'delivered',server_now:'2031-01-01T00:00:00Z'}),original);
 for(const change of [{booking_revision:2},{refunded_paise:100},{amount_paise:100},{meet_url:null},{service_name:'Different consultation'},{starts_at:'2031-04-05T10:00:00Z'}])assert.notEqual(pdfFacts({...r,...change}),original);
});
test('PDF rejects unconfirmed facts, unsupported text and invalid bounded font loads',{skip:!available},async()=>{
 for(const r of [confirmed({appointment_state:'held'}),confirmed({booking_revision:null}),confirmed({meeting_mode:null})])
  await assert.rejects(buildAppointmentPDF(r,{brand:'Synthetic Practice',load:libraries}));
 for(const brand of ['', 'x'.repeat(151)])await assert.rejects(buildAppointmentPDF(confirmed(),{brand,load:libraries}),/pdf_unavailable/);
 for(const fontBytes of [null,new Uint8Array(),new Uint8Array(1048577)])
  await assert.rejects(buildAppointmentPDF(confirmed(),{brand:'Synthetic Practice',load:async()=>({...await libraries(),fontBytes})}),/pdf_unavailable/);
 await assert.rejects(buildAppointmentPDF(confirmed(),{brand:'Synthetic 🚀 Practice',load:libraries}),/pdf_font_unavailable/);
});
test('long bounded text wraps inside the page instead of clipping and keeps appointment facts',{skip:!available},async()=>{
 const r=confirmed({service_name:'A'.repeat(150)}),file=await buildAppointmentPDF(r,{brand:('Synthetic practice with descriptive wording ').repeat(3),load:libraries});
 const proof=await inspect(file.bytes);assert.ok(proof.doc.getPageCount()>=1);
 assert.ok(proof.lines.join('').includes(r.service_name));assert.ok(proof.lines.join('\n').includes(r.request_id));
 for(const stream of proof.streams)for(const position of stream.matchAll(/1 0 0 1 ([\d.]+) ([\d.]+) Tm/g)){
  assert.ok(Number(position[1])>=40&&Number(position[1])<555.28);assert.ok(Number(position[2])>=40&&Number(position[2])<801.89);
 }
});
