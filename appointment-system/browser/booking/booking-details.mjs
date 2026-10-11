import {createTransport,RequestError} from '../transport.mjs';
import {admissionAllowed} from '../product-state.mjs';
import {checkedReceiptFacts,instant,integer,requireValue} from './protocol.mjs';

const reference=/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/;
const states=['held','expired','confirmed','cancelled','payment_review'];
const summaryKeys='appointment_state,booking_revision,ends_at,request_id,service_name,starts_at,timezone';
const factKeys='acknowledgement_state,amount_paise,appointment_state,booking_revision,captured_paise,currency,ends_at,hold_expires_at,meet_url,meeting_email_state,meeting_mode,meeting_state,order_state,payment_checked_at,payment_evidence_source,payment_state,refunded_paise,request_id,server_now,service_name,starts_at,timezone';
const exact=(value,keys)=>!!value && typeof value==='object' && !Array.isArray(value) && Object.keys(value).sort().join(',')===keys;
const validReference=value=>typeof value==='string' && reference.test(value) && value!=='00000000-0000-0000-0000-000000000000';
const timezone=value=>{try{return typeof value==='string' && value.length<=100 && !!new Intl.DateTimeFormat('en',{timeZone:value});}catch{return false;}};
const whitespace=/[\u0009-\u000d\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]/u;
export const bookingStateLabel=state=>({confirmed:'Confirmed',held:'Reserved',expired:'Reservation ended',cancelled:'Cancelled',payment_review:'Payment being checked'})[state]||'Status being checked';

function checkedList(value){
 requireValue(exact(value,'items,kind,next_cursor,server_now,version') && value.version===1 && value.kind==='list'
  && instant(value.server_now) && Array.isArray(value.items) && value.items.length<=20
  && (value.next_cursor===null || typeof value.next_cursor==='string' && /^[A-Za-z0-9_-]{1,512}$/.test(value.next_cursor))
  && new Set(value.items.map(row=>row?.request_id)).size===value.items.length);
 for(const row of value.items)requireValue(exact(row,summaryKeys) && validReference(row.request_id)
  && integer(row.booking_revision,1) && typeof row.service_name==='string' && row.service_name.length>0 && row.service_name.length<=150
  && instant(row.starts_at) && instant(row.ends_at) && Date.parse(row.ends_at)>Date.parse(row.starts_at)
  && timezone(row.timezone) && states.includes(row.appointment_state));
 return value;
}
function checkedDetail(value,id){
 requireValue(exact(value,'capabilities,kind,receipt,version') && value.version===1 && value.kind==='detail'
  && exact(value.receipt,factKeys) && exact(value.capabilities,'download_pdf,refresh') && value.capabilities.refresh===true
  && typeof value.capabilities.download_pdf==='boolean');
 const r=checkedReceiptFacts(value.receipt,id);
 requireValue(integer(r.booking_revision,1) && ['google_meet','internal'].includes(r.meeting_mode)
  && value.capabilities.download_pdf===(r.appointment_state==='confirmed'));
 return r;
}
export function lookupIdentity(input){
 const fields=[],name=input.full_name;
 if(typeof name!=='string' || Array.from(name).length>100 || Array.from(name.trim()).length<2
  || Array.from(name).some(c=>(c.codePointAt(0)<32 || c.codePointAt(0)===127)&&!whitespace.test(c)))fields.push('full_name');
 const raw=input.phone.trim();
 let phone=raw.replace(/[ ()-]/g,'');
 if(!/^[+0-9 ()-]+$/.test(raw) || raw.length>32)fields.push('phone');
 if(!phone.startsWith('+')){
  if(input.country==='international')fields.push('phone');
  else if(/^\+[1-9][0-9]{0,2}$/.test(input.country))phone=input.country+phone;
  else fields.push('phone');
 }
 if(!/^\+[1-9][0-9]{6,14}$/.test(phone))fields.push('phone');
 if(fields.length)throw new RequestError('invalid_request',{fields:[...new Set(fields)]});
 return Object.freeze({full_name:name,phone});
}

/** In-memory read-only controller. It never creates a checkout or touches storage. */
export function createBookingDetails({product,fetcher=globalThis.fetch}){
 const request=createTransport({fetcher,allowed:path=>path==='/api/booking/details',timeout:20000,maximum:32768});
 let alive=false,active=true,generation=0,query=null,abort=null,cleanup=null,lastEpoch=null,lastForeground=null;
 const initial=()=>({input:{full_name:'',phone:'',country:'+91'},items:[],nextCursor:null,receipt:null,
  status:'idle',busy:false,stale:false,error:'',fields:[],focusVersion:0,focusTarget:'form',selectedId:null});
 let state=Object.freeze(initial());const listeners=new Set();
 const emit=change=>{state=Object.freeze({...state,...change});for(const listener of listeners)listener();};
 const cancel=()=>{generation++;abort?.abort();abort=null;};
 const allowed=()=>alive && active && admissionAllowed(product.getSnapshot());
 const mark=()=>({generation,epoch:product.getSnapshot().activation_epoch});
 const current=m=>allowed() && m.generation===generation && m.epoch===product.getSnapshot().activation_epoch;
 const focus=target=>({focusVersion:state.focusVersion+1,focusTarget:target});
 function clear({inputs=false}={}){
  cancel();query=null;const reset=initial();if(!inputs)reset.input=state.input;
  emit({...reset,focusVersion:state.focusVersion});
 }
 function failure(error,m,{detail=false}={}){
  if(!current(m))return;
  const fields=(error.fields||[]).filter(value=>['full_name','phone'].includes(value));
  const messages={invalid_request:'Please check your full name and saved phone number.',invalid_name:'Please enter the full name saved when booking.',
   invalid_cursor:'This list has changed or expired. Search again for the latest bookings.',
   booking_not_found:'We could not find a booking with these details. Check the saved name and phone number.',
   please_wait:'Please wait '+Math.max(1,error.retryAfter||60)+' seconds before trying again.'};
  emit({busy:false,error:messages[error.code]||'We could not check your booking just now. Please try again.',fields,
   ...(detail?{stale:true}:{}),...(fields.length?focus(fields[0]):{})});
 }
 async function readDetail(id,m,signal){
  const r=checkedDetail(await request('/api/booking/details',{body:{...query,request_id:id},signal}),id);
  if(!current(m))throw new RequestError('request_cancelled');
  const latest=state.receipt;
  if(latest?.request_id===id && (latest.booking_revision>r.booking_revision || latest.booking_revision===r.booking_revision
   && Date.parse(latest.server_now)>Date.parse(r.server_now)))throw new RequestError('receipt_changed');
  emit({receipt:r,status:'detail',selectedId:id,stale:false,error:'',fields:[]});return r;
 }
 async function search(more=false){
  if(!allowed() || state.busy || more&&!state.nextCursor)return;
  let identity;
  try{identity=more?query:lookupIdentity(state.input);}
  catch(error){const m=mark();failure(error,m);return;}
  const cursor=more?state.nextCursor:null;cancel();query=identity;const m=mark();abort=new AbortController();
  const signal=abort.signal;
  emit({busy:true,error:'',fields:[],receipt:null,stale:false,...(!more?{items:[],nextCursor:null,selectedId:null}:{} )});
  try{
   const page=checkedList(await request('/api/booking/details',{body:{...query,...(cursor?{cursor}:{})},signal}));
   if(!current(m))return;
   const items=more?[...new Map([...state.items,...page.items].map(row=>[row.request_id,row])).values()]:page.items;
   emit({items,nextCursor:page.next_cursor,status:items.length?'list':'empty',busy:false,
    error:more&&!page.items.length?'The list changed while you were viewing it. Search again for the latest bookings.':'',...focus('results')});
   if(!more && items.length===1 && page.next_cursor===null){
    emit({busy:true});await readDetail(items[0].request_id,m,signal);
    if(current(m))emit({busy:false,...focus('results')});
   }
  }catch(error){failure(error,m,{detail:!!state.receipt});}
  finally{if(m.generation===generation){abort=null;if(state.busy)emit({busy:false});}}
 }
 async function open(id){
  if(!allowed() || state.busy || !query || !state.items.some(row=>row.request_id===id))return;
  cancel();const m=mark();abort=new AbortController();emit({busy:true,receipt:null,error:'',selectedId:id});
  try{await readDetail(id,m,abort.signal);if(current(m))emit({busy:false,...focus('results')});}
  catch(error){failure(error,m,{detail:true});}
  finally{if(m.generation===generation){abort=null;if(state.busy)emit({busy:false});}}
 }
 async function refresh({signal}={}){
  if(!allowed() || !query || !state.receipt)throw new RequestError('access_unavailable');
  if(state.busy)throw new RequestError('request_cancelled');
  const m=mark(),id=state.receipt.request_id,own=new AbortController();
  emit({busy:true});
  const parent=abort,abortRead=()=>own.abort();signal?.addEventListener('abort',abortRead,{once:true});parent?.signal.addEventListener('abort',abortRead,{once:true});
  if(signal?.aborted)own.abort();
  // Selection generation is checked even when a PDF read has its own signal.
  const stop=()=>{if(!current(m))own.abort();};listeners.add(stop);
  try{return await readDetail(id,m,own.signal);}
  catch(error){failure(error,m,{detail:true});throw error;}
  finally{listeners.delete(stop);signal?.removeEventListener('abort',abortRead);parent?.signal.removeEventListener('abort',abortRead);
   if(current(m))emit({busy:false});}
 }
 function start(windowObject=globalThis.window){
  if(alive)return cleanup;alive=true;
  const visible=product.getSnapshot();lastEpoch=visible.activation_epoch;lastForeground=visible.foreground_revision;
  const unsubscribe=product.subscribe(()=>{
   const next=product.getSnapshot();
   if(next.enabled!==true || next.activation_epoch!==lastEpoch || next.foreground_revision!==lastForeground)clear();
   lastEpoch=next.activation_epoch;lastForeground=next.foreground_revision;
  });
  const hide=()=>clear({inputs:true}),show=event=>{if(event.persisted)clear({inputs:true});};
  windowObject?.addEventListener('pagehide',hide);windowObject?.addEventListener('pageshow',show);
  cleanup=()=>{alive=false;clear({inputs:true});unsubscribe();windowObject?.removeEventListener('pagehide',hide);windowObject?.removeEventListener('pageshow',show);cleanup=null;};
  return cleanup;
 }
 return Object.freeze({getSnapshot:()=>state,subscribe:listener=>{listeners.add(listener);return()=>listeners.delete(listener);},start,
  edit:(name,value)=>{if(!['full_name','phone','country'].includes(name))return;clear();emit({input:{...state.input,[name]:value}});},
  setActive:value=>{if(active!==value){active=value;clear();}},search:()=>search(false),more:()=>search(true),open,refresh,
  back:()=>{cancel();emit({receipt:null,status:'list',busy:false,stale:false,error:'',...focus(state.selectedId||'results')});}});
}
