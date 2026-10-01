import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {runInContext} from 'node:vm';
import {JSDOM,VirtualConsole} from 'jsdom';
import {createInstrumenter} from 'istanbul-lib-instrument';
import {createCoverageMap} from 'istanbul-lib-coverage';
import {afterEach,expect,test} from 'vitest';

const assets=new URL('../../../backend/booking_engine/studio_assets/',import.meta.url);
const id='11111111-1111-4111-8111-111111111111',claim='22222222-2222-4222-8222-222222222222',key='payment:'+id;
const instant='2030-01-02T10:00:00+05:30';let open=[];
const snapshot=()=>({code:'ok',claim_id:claim,reference:id,revision:1,name:'<script>synthetic</script>',service:'Kundli Prediction',state:'confirmed',starts_at:instant,can_cancel:true,can_reschedule:true,policy_guidance:'staff_review',email:'test@example.invalid',phone:'+919876543210',unresolved_payments:0,payments:[{payment_id:'pay_synthetic',status:'captured',amount_paise:100,refunded_paise:0,observed_at:instant}]});
const issue=(category='payment')=>({item_key:category==='enquiry'?'enquiry:'+id:key,category,review_revision:0,state:'needs_attention',created_at:instant,reference:id,subject:'Synthetic question',reviews:[],...(category==='enquiry'?{enquiry:{name:'<img src=x onerror=bad()>',email:'test@example.invalid',phone:'',subject:'General enquiry',message:'Synthetic only'}}:{})});
async function settle(){for(let i=0;i<6;i++){await new Promise(resolve=>setTimeout(resolve,0));}}
async function boot({role='client',signed=true,recovery=false,status={},handler,setup,url}={}){
 const errors=[],virtualConsole=new VirtualConsole();virtualConsole.on('jsdomError',error=>{if(error.type==='not-implemented'&&error.message.includes('navigation'))return;errors.push(error.message);});
 const dom=new JSDOM(readFileSync(new URL(recovery?'recovery.html':'index.html',assets),'utf8'),{url:url||'https://www.sarsajyotishsansthan.com/'+(recovery?'booking-help':'studio'),runScripts:'outside-only',virtualConsole});dom.verificationErrors=errors;open.push(dom);
 const w=dom.window,calls=[],state={items:[],inbox:[issue()],snapshot:snapshot(),status:{signed_in:signed,role,email:role==='client'?'sarsajyotish@gmail.com':'neuraflowindia@gmail.com',authorization_saved:true,reconnect_required:false,workbook_url:'https://docs.google.com/spreadsheets/d/synthetic',...status}};
 w.AbortSignal=globalThis.AbortSignal;w.AbortController=globalThis.AbortController;w.TextDecoder=globalThis.TextDecoder;w.HTMLElement.prototype.scrollIntoView=function(){};
 w.fetch=async(path,options={})=>{
  const body=options.body?JSON.parse(options.body):null;calls.push({path,body,options});
  const custom=await handler?.(path,body,state,calls);if(custom instanceof Response)return custom;if(custom!==undefined)return Response.json(custom);
  if(path==='/api/studio/status')return Response.json(state.status);
  if(path==='/api/studio/calendar/list')return Response.json({code:'ok',day:body.day,timezone:'Asia/Kolkata',items:state.items,next_cursor:null});
  if(path==='/api/studio/inbox/list')return Response.json({code:'ok',view:body.view,items:state.inbox,next_cursor:null});
  if(path==='/api/studio/inbox/detail')return Response.json({code:'ok',item:state.inbox.find(i=>i.item_key===body.item_key)});
  if(path.endsWith('/appointments/detail')||path.endsWith('/appointments/lookup'))return Response.json(state.snapshot);
  if(path.endsWith('/appointments/cancel'))return Response.json({code:'cancelled',revision:body.expected_revision+1});
  if(path.endsWith('/appointments/reschedule'))return Response.json({code:'rescheduled',revision:body.expected_revision+1,starts_at:body.starts_at});
  if(path.endsWith('/appointments/support'))return Response.json({code:'support_saved',revision:body.expected_revision+(body.action==='contact_correction'?1:0),active:true,expires_at:instant,activation_code:'12345678'});
  if(path.endsWith('/calendar/close'))return Response.json({code:'closed',active:true});
  if(path.endsWith('/calendar/reopen'))return Response.json({code:'reopened'});
  if(path.endsWith('/inbox/review')||path.endsWith('/inbox/retry')||path.endsWith('/inbox/refund-verified'))return Response.json({code:path.endsWith('/review')?'review_saved':path.endsWith('/retry')?'retry_queued':'refund_verified',revision:body.expected_revision+1});
  if(path.endsWith('recover-receipt'))return Response.json({code:'receipt_restored'});
  if(path.endsWith('/checkout/status'))return Response.json({request_id:body.request_id,appointment_state:'confirmed'});
  if(path.endsWith('/logout')){state.status={signed_in:false};return Response.json({code:'ok'});}
  if(path.endsWith('/prepare'))return Response.json({code:'ok'});
  return Response.json({authorization_url:'https://evil.invalid/o/oauth2/v2/auth'});
 };
 setup?.(w,state);const scripts=recovery?['recovery.js']:['interface.js','calendar.js','inbox.js','appointments.js'];
 for(const file of scripts){const filename=fileURLToPath(new URL(file,assets));const instrumenter=createInstrumenter({compact:false,coverageVariable:'__VITEST_COVERAGE__'});const source=instrumenter.instrumentSync(readFileSync(new URL(file,assets),'utf8'),filename);runInContext(source,dom.getInternalVMContext(),{filename});}
 await settle();const $=selector=>w.document.querySelector(/^[#[.]/.test(selector)?selector:'#'+selector);
 async function fire(id,type='click'){const el=$(id);el.dispatchEvent(new w.Event(type,{bubbles:true,cancelable:true}));await settle();}
 async function event(name,detail){w.document.dispatchEvent(new w.CustomEvent(name,{detail}));await settle();}
 return {w,$,calls,state,fire,event};
}
afterEach(()=>{const coverage=createCoverageMap(globalThis.__VITEST_COVERAGE__||{});const errors=[];for(const dom of open){coverage.merge(dom.window.__VITEST_COVERAGE__||{});errors.push(...dom.verificationErrors);dom.window.close();}globalThis.__VITEST_COVERAGE__=coverage.toJSON();open=[];expect(errors).toEqual([]);});

test('staff signed-out, expired and separate agency permissions produce distinct visible controls',async()=>{
 const out=await boot({signed:false,handler:p=>p==='/api/studio/status'?new Response('',{status:401}):undefined});expect(out.$('signin-panel').hidden).toBe(false);expect(out.calls.some(c=>c.path.includes('/calendar/'))).toBe(false);
 const agency=await boot({role:'agency',status:{reconnect_required:true}});expect(agency.$('calendar-panel').hidden).toBe(true);expect(agency.$('prepare-workbook').hidden).toBe(true);expect(agency.$('inbox-enquiries').hidden).toBe(true);expect(agency.$('connection-status').textContent).toContain('expired');
});
test('spreadsheet destinations and sign-in destinations reject unsafe origins without rendering private markup',async()=>{
 const s=await boot({status:{workbook_url:'https://evil.invalid/spreadsheets/d/private'}});expect(s.$('retry').hidden).toBe(false);expect(s.$('open-workbook').hidden).toBe(true);await s.fire('connect');expect(s.$('status').textContent).toContain('could not start');
 const good=await boot({url:'https://www.sarsajyotishsansthan.com/studio?connection=failed',status:{workbook_url:null,authorization_saved:false}});expect(good.$('status').textContent).toContain('not completed');expect(good.$('workbook-status').textContent).toContain('Connect Google');expect(good.w.location.search).toBe('');
});
test('workbook preparation, retry and sign-out use the existing private operations',async()=>{
 let fail=true;const s=await boot({status:{workbook_url:null},handler:p=>p.endsWith('/prepare')&&fail?Promise.reject(Error('interrupted')):undefined});expect(s.$('prepare-workbook').hidden).toBe(false);await s.fire('prepare-workbook');expect(s.$('status').textContent).toContain('existing spreadsheet');fail=false;await s.fire('retry');await s.fire('prepare-workbook');await s.fire('logout');expect(s.$('signin-panel').hidden).toBe(false);expect(s.$('calendar-panel').hidden).toBe(true);
});
test('calendar lists safely render appointments and closures, paginate and reopen a selected closure',async()=>{
 const s=await boot({setup:(_w,state)=>state.items=[{kind:'closure',id:claim,starts_at:instant,ends_at:'2030-01-02T10:30:00+05:30',reason:'<img src=x>'},{kind:'appointment',id:claim,starts_at:instant,ends_at:'2030-01-02T11:00:00+05:30',service:'Kundli Prediction',name:'Synthetic',state:'confirmed'}]});expect(s.$('calendar-items').children).toHaveLength(2);expect(s.$('calendar-items').querySelector('img')).toBeNull();
 await s.fire('calendar-items button');expect(s.$('calendar-reopen').hidden).toBe(false);await s.fire('reopen-cancel');expect(s.$('calendar-reopen').hidden).toBe(true);await s.fire('calendar-items button');s.$('reopen-reason').value='Synthetic check';await s.fire('calendar-reopen','submit');expect(s.$('calendar-action-status').textContent).toContain('open again');expect(s.calls.find(c=>c.path.endsWith('/reopen')).body.claim_id).toBe(claim);
});
test('an interrupted closure retains one operation; explicit rejection releases it',async()=>{
 let fail=true;const s=await boot({handler:p=>p.endsWith('/close')&&fail?Promise.reject(Error('lost response')):undefined});await s.fire('calendar-close','submit');expect(s.$('calendar-action-status').textContent).toContain('end time');s.$('closure-start').value='2030-01-02T11:00';s.$('closure-end').value='2030-01-02T11:30';s.$('closure-reason').value='Synthetic';await s.fire('calendar-close','submit');expect(s.$('calendar-pending').hidden).toBe(false);const first=s.calls.find(c=>c.path.endsWith('/close')).body;fail=false;await s.fire('calendar-repeat');expect(s.calls.filter(c=>c.path.endsWith('/close'))[1].body).toEqual(first);expect(s.$('calendar-pending').hidden).toBe(true);
});
test('calendar rejects malformed responses and does not load an invalid date',async()=>{
 const s=await boot({handler:(p,b)=>p.endsWith('/calendar/list')?{code:'ok',day:b.day,timezone:'Asia/Kolkata',items:[{kind:'foreign'}]}:undefined});expect(s.$('calendar-status').textContent).toContain('cannot load');s.$('calendar-day').value='';const before=s.calls.length;await s.fire('calendar-view','submit');expect(s.calls).toHaveLength(before);
});
test.each(['cancel','reschedule'])('appointment %s retains an uncertain mutation then commits the same request',async action=>{
 let fail=true;const s=await boot({handler:p=>p.endsWith('/appointments/'+action)&&fail?Promise.reject(Error('lost')):undefined});await s.event('studio-appointment',claim);expect(s.$('appointment-title')).toBe(s.w.document.activeElement);expect(s.$('appointment-summary').querySelector('script')).toBeNull();
 s.$('appointment-ack').checked=true;s.$('appointment-reason').value='Synthetic cancel';s.$('appointment-start').value='2030-01-02T11:00';s.$('appointment-move-reason').value='Synthetic move';await s.fire('appointment-'+action,'submit');const first=s.calls.find(c=>c.path.endsWith('/appointments/'+action)).body;expect(s.$('appointment-repeat').hidden).toBe(false);fail=false;await s.fire('appointment-repeat');expect(s.calls.filter(c=>c.path.endsWith('/appointments/'+action))[1].body).toEqual(first);expect(s.$('appointment-status').textContent).toContain(action==='cancel'?'No refund':'No extra payment');
});
test('stale appointment revisions release the rejected mutation and require new details',async()=>{
 const s=await boot({handler:p=>p.endsWith('/appointments/cancel')?Response.json({code:'revision_changed'},{status:409}):undefined});await s.event('studio-appointment',claim);s.$('appointment-ack').checked=true;await s.fire('appointment-cancel','submit');expect(s.$('appointment-repeat').hidden).toBe(true);expect(s.$('appointment-status').textContent).toContain('latest details');expect(s.$('appointment-cancel').hidden).toBe(true);
});
test.each(['receipt_recovery','contact_correction'])('verified support %s shows its access code without browser persistence',async action=>{
 const s=await boot();s.$('booking-reference').value='invalid';await s.fire('booking-lookup','submit');expect(s.$('booking-support-status').textContent).toContain('complete');s.$('booking-reference').value=id;await s.fire('booking-lookup','submit');expect(s.$('booking-support-change').hidden).toBe(false);s.$('support-action').value=action;await s.fire('support-action','change');expect(s.$('support-contacts').hidden).toBe(action!=='contact_correction');
 s.$('support-verified').checked=true;s.$('support-payment').value='pay_synthetic';s.$('support-reason').value='Approved synthetic support';s.$('support-email').value='corrected@example.invalid';s.$('support-phone').value='+919876543211';await s.fire('booking-support-change','submit');expect(s.$('support-code').textContent).toBe('12345678');expect(s.w.sessionStorage.length).toBe(0);expect(s.w.localStorage.length).toBe(0);expect(s.calls.find(c=>c.path.endsWith('/support')).body).toMatchObject({verification_confirmed:true,action});
});
test.each(['review','retry','refund-verified'])('inbox %s is separately acknowledged and a lost response repeats the same note',async action=>{
 let fail=true;const s=await boot({handler:p=>p.endsWith('/inbox/'+action)&&fail?Promise.reject(Error('lost')):undefined});await s.fire('inbox-issues');await s.fire('inbox-items button');expect(s.$('inbox-detail').hidden).toBe(false);s.$('review-note').value='Checked synthetic evidence';const target=action==='review'?'inbox-review':action==='retry'?'inbox-action-retry':'inbox-action-refund';await s.fire(target,action==='review'?'submit':'click');expect(s.$('inbox-retry-review').hidden).toBe(false);const first=s.calls.find(c=>c.path.endsWith('/inbox/'+action)).body;fail=false;await s.fire('inbox-retry-review');expect(s.calls.filter(c=>c.path.endsWith('/inbox/'+action))[1].body).toEqual(first);expect((action==='review'?s.$('inbox-review-status'):s.$('inbox-status')).textContent).toContain(action==='review'?'not been changed':action==='retry'?'does not confirm':'did not send money');
});
test('verified enquiry content remains text, note validation stops empty writes and access loss clears records',async()=>{
 let denied=false;const s=await boot({setup:(_w,state)=>state.inbox=[issue('enquiry')],handler:p=>denied&&p.endsWith('/inbox/list')?Response.json({code:'access_unavailable'},{status:403}):undefined});await s.fire('inbox-items button');expect(s.$('inbox-content').querySelector('img')).toBeNull();expect(s.$('inbox-action-retry').hidden).toBe(true);s.$('review-note').value='\n';await s.fire('inbox-review','submit');expect(s.$('inbox-review-status').textContent).toContain('single-line');denied=true;await s.fire('inbox-refresh');expect(s.$('inbox-panel').hidden).toBe(true);expect(s.$('inbox-content').children).toHaveLength(0);
});
test('receipt recovery reuses staged access after a lost response and never stores the activation code',async()=>{
 let fail=true;const s=await boot({recovery:true,handler:p=>p.endsWith('recover-receipt')&&fail?Promise.reject(Error('lost')):undefined});s.$('recovery-reference').value=id;s.$('recovery-code').value='12345678';await s.fire('recovery-form','submit');expect(s.$('recovery-status').textContent).toContain('same code');const staged=JSON.parse(s.w.sessionStorage.getItem('sarsa:004:receipt-recovery:v1'));expect(staged).not.toHaveProperty('code');fail=false;await s.fire('recovery-form','submit');expect(s.$('recovery-open').hidden).toBe(false);expect(JSON.parse(s.w.sessionStorage.getItem('sarsa:004:booking-receipt:v1'))).toEqual(staged);expect(s.calls.filter(c=>c.path.endsWith('recover-receipt'))).toHaveLength(1);
});
test.each([403,429,503])('receipt recovery explains status %s without losing the saved identity',async status=>{
 const s=await boot({recovery:true,handler:p=>p.endsWith('recover-receipt')?Response.json({code:'unavailable'},{status}):undefined});s.$('recovery-reference').value=id;s.$('recovery-code').value='12345678';await s.fire('recovery-form','submit');expect(s.$('recovery-open').hidden).toBe(true);expect(s.$('recovery-status').textContent).toContain(status===403?'could not use':status===429?'wait a minute':'same code');expect(s.w.sessionStorage.getItem('sarsa:004:receipt-recovery:v1')).toBeTruthy();
});
test('receipt recovery rejects conflicting saved bookings and corrupt access before sending',async()=>{
 for(const raw of ['{broken',JSON.stringify({version:1,request_id:claim,secret:'a'.repeat(43)})]){const s=await boot({recovery:true,setup:w=>w.sessionStorage.setItem('sarsa:004:booking-receipt:v1',raw)});s.$('recovery-reference').value=id;s.$('recovery-code').value='12345678';await s.fire('recovery-form','submit');expect(s.calls).toHaveLength(0);expect(s.$('recovery-status').textContent).toContain(raw.startsWith('{broken')?'storage':'Another booking');}
});

test('staff setup handles a rejected status, interrupted connection and trusted Google destination',async()=>{
 for(const status of [{signed_in:true,role:'unknown'},{signed_in:null},{signed_in:false}]){
  const s=await boot({status});expect(s.$('calendar-panel').hidden).toBe(true);
  expect(s.$('status').textContent).toContain(status.signed_in===false?'signing in':'cannot check');
 }
 const s=await boot({url:'https://www.sarsajyotishsansthan.com/studio?connection=check',handler:p=>p.endsWith('/logout')?Promise.reject(Error('lost')):p.endsWith('/sign-in/start')?{authorization_url:'https://accounts.google.com/o/oauth2/v2/auth?client_id=synthetic'}:undefined});
 expect(s.$('status').textContent).toContain('interrupted');await s.fire('logout');expect(s.$('status').textContent).toContain('could not be confirmed');
 await s.fire('[data-role="client"]');expect(s.calls.at(-1).body).toEqual({role:'client'});expect(s.$('status').textContent).toContain('Opening Google');
 const before=s.calls.length;await s.fire('connect');await s.fire('logout');await s.fire('retry');await s.fire('prepare-workbook');expect(s.calls).toHaveLength(before);
});
test('calendar pagination reuses the cursor and safely renders unnamed reservations',async()=>{
 let page=0;const s=await boot({handler:(p,b)=>p.endsWith('/calendar/list')?{code:'ok',day:b.day,timezone:'Asia/Kolkata',items:[{kind:'appointment',id:claim,state:'held',starts_at:instant,ends_at:instant}],next_cursor:page++===0?'cursor':null}:undefined});
 expect(s.$('calendar-items').textContent).toContain('Appointment · Customer');await s.fire('calendar-more');expect(s.calls.filter(c=>c.path.endsWith('/calendar/list'))[1].body.after).toBe('cursor');expect(s.$('calendar-items').children).toHaveLength(2);expect(s.$('calendar-more').hidden).toBe(true);
});
test.each([
 {code:'not_ok'}, {timezone:'UTC'}, {day:'1999-01-01'}, {items:[] , code:'wrong'}, {items:Array(51).fill({})}, {items:[{kind:'closure',starts_at:'bad',ends_at:instant}]},
])('calendar rejects an inconsistent saved response %j',async change=>{
 const s=await boot({handler:(p,b)=>p.endsWith('/calendar/list')?{code:'ok',day:b.day,timezone:'Asia/Kolkata',items:[],...change}:undefined});
 expect(s.$('calendar-items').children).toHaveLength(0);expect(s.$('calendar-status').textContent).toContain('cannot load');
});
test('calendar rejects known closure conflicts, retains malformed replies and acknowledges already reopened periods',async()=>{
 for(const response of [Response.json({code:'time_already_reserved'},{status:409}),Response.json({code:'closed',active:'yes'}),Response.json({code:'wrong'})]){
  const s=await boot({handler:p=>p.endsWith('/close')?response.clone():undefined});
  s.$('closure-start').value='2030-01-02T11:00';s.$('closure-end').value='2030-01-02T12:00';await s.fire('calendar-close','submit');
  expect(s.$('calendar-pending').hidden).toBe(response.status===409);expect(s.$('calendar-action-status').textContent).toContain(response.status===409?'overlaps':'could not confirm');
  const before=s.calls.filter(c=>c.path.endsWith('/close')).length;await s.fire('calendar-close','submit');expect(s.calls.filter(c=>c.path.endsWith('/close'))).toHaveLength(before+(response.status===409?1:0));
 }
 const s=await boot({handler:p=>p.endsWith('/close')?{code:'existing',active:false}:undefined});s.$('closure-start').value='2030-01-02T11:00';s.$('closure-end').value='2030-01-02T12:00';await s.fire('calendar-close','submit');expect(s.$('calendar-action-status').textContent).toContain('already been reopened');
 await s.fire('calendar-repeat');await s.fire('calendar-reopen','submit');expect(s.calls.some(c=>c.path.endsWith('/reopen'))).toBe(false);
});
test.each([{revision:0},{claim_id:id},{can_cancel:'yes'},{starts_at:'bad'},{policy_guidance:'unknown'},{code:'not_ok'}])('appointment detail rejects unsafe or stale shape %j',async change=>{
 const s=await boot({handler:p=>p.endsWith('/appointments/detail')?{...snapshot(),...change}:undefined});await s.event('studio-appointment',claim);expect(s.$('appointment-cancel').hidden).toBe(true);expect(s.$('appointment-status').textContent).toContain('could not confirm');
});
test('appointment mutations require acknowledgement, time and current role and reject expired permission',async()=>{
 const s=await boot();await s.fire('appointment-cancel','submit');await s.fire('appointment-reschedule','submit');await s.fire('booking-support-change','submit');expect(s.calls.some(c=>/\/appointments\/(cancel|reschedule|support)$/.test(c.path))).toBe(false);
 await s.event('studio-appointment',claim);await s.fire('appointment-cancel','submit');await s.fire('appointment-reschedule','submit');expect(s.calls.some(c=>c.path.endsWith('/cancel')||c.path.endsWith('/reschedule'))).toBe(false);
 await s.event('studio-role','agency');await s.event('studio-appointment',claim);expect(s.$('appointment-detail').hidden).toBe(true);
 const denied=await boot({handler:p=>p.endsWith('/appointments/detail')?Response.json({code:'access_unavailable'},{status:401}):undefined});await denied.event('studio-appointment',claim);expect(denied.$('appointment-detail').hidden).toBe(true);expect(denied.$('status').textContent).toContain('Sign in again');
});
test('support lookup handles no payments, a held booking, malformed results and missing permission',async()=>{
 for(const change of [{payments:[],claim_id:null,state:'held'},{reference:claim},{payments:Array(21).fill({})},{payments:null}]){
  const s=await boot({setup:(_w,state)=>state.snapshot={...snapshot(),...change}});s.$('booking-reference').value=id;await s.fire('booking-lookup','submit');
  if(change.state==='held'){expect(s.$('booking-support-change').hidden).toBe(true);expect(s.$('booking-support-manage').hidden).toBe(true);expect(s.$('booking-support-content').textContent).toContain('No payment evidence');}
  else expect(s.$('booking-support-status').textContent).toContain('could not load');
 }
 const denied=await boot({handler:p=>p.endsWith('/appointments/lookup')?Response.json({code:'access_unavailable'},{status:403}):undefined});denied.$('booking-reference').value=id;await denied.fire('booking-lookup','submit');expect(denied.$('booking-support').hidden).toBe(true);expect(denied.$('status').textContent).toContain('Sign in again');
});
test('support retry preserves identity and handles inactive codes or explicit rejection',async()=>{
 for(const outcome of ['inactive','reject','invalid']){
  let lost=true;const s=await boot({handler:p=>p.endsWith('/appointments/support')?(lost?Promise.reject(Error('lost')):outcome==='reject'?Response.json({code:'support_wait'},{status:409}):{code:'support_saved',revision:1,active:outcome==='invalid',expires_at:instant,activation_code:'bad'}):undefined});
  s.$('booking-reference').value=id;await s.fire('booking-lookup','submit');await s.fire('booking-support-manage');expect(s.$('appointment-detail').hidden).toBe(false);s.$('support-verified').checked=true;s.$('support-payment').value='pay_synthetic';await s.fire('booking-support-change','submit');
  const first=s.calls.find(c=>c.path.endsWith('/support')).body;const before=s.calls.length;await s.fire('booking-lookup','submit');await s.event('studio-appointment',claim);expect(s.calls).toHaveLength(before);
  lost=false;await s.fire('support-repeat');expect(s.calls.filter(c=>c.path.endsWith('/support'))[1].body).toEqual(first);
  expect(s.$('booking-support-status').textContent).toContain(outcome==='inactive'?'no longer active':outcome==='reject'?'wait':'same support action');
 }
});
test('obsolete appointment and lookup responses cannot repopulate signed-out records',async()=>{
 for(const target of ['detail','lookup','cancel','support']){
  let resolve;const held=new Promise(r=>resolve=r);const s=await boot({handler:p=>p.endsWith('/appointments/'+target)?held:undefined});
  if(['detail','cancel'].includes(target)){const opening=s.event('studio-appointment',claim);if(target==='detail'){await settle();await s.event('studio-role',null);resolve(snapshot());await opening;}else{await opening;s.$('appointment-ack').checked=true;const saving=s.fire('appointment-cancel','submit');await settle();await s.event('studio-role',null);resolve({code:'cancelled',revision:2});await saving;}}
  else {s.$('booking-reference').value=id;const lookup=s.fire('booking-lookup','submit');if(target==='lookup'){await settle();await s.event('studio-role',null);resolve(snapshot());await lookup;}else{await lookup;s.$('support-verified').checked=true;const saving=s.fire('booking-support-change','submit');await settle();await s.event('studio-role',null);resolve({code:'support_saved',revision:1,active:false,expires_at:instant});await saving;}}
  expect(s.$('appointment-detail').hidden).toBe(true);expect(s.$('booking-support').hidden).toBe(true);expect(s.$('support-code').textContent).toBe('');
 }
});
test('inbox shows saved reviews, opens booking support, paginates and keeps agency-only work separate',async()=>{
 const item={...issue(),review_revision:1,reviews:[{note:'Checked',role:'agency',created_at:instant},{note:'Checked by practice',role:'client',created_at:instant}]};let page=0;
 const s=await boot({setup:(_w,state)=>state.inbox=[item],handler:(p,b)=>p.endsWith('/inbox/list')?{code:'ok',view:b.view,items:[item],next_cursor:page++===0?item.item_key:null}:undefined});
 expect(s.$('inbox-items').textContent).toContain('review recorded');await s.fire('inbox-more');expect(s.calls.filter(c=>c.path.endsWith('/inbox/list'))[1].body.after).toBe(item.item_key);await s.fire('inbox-items button');expect(s.$('inbox-reviews').children).toHaveLength(2);await s.fire('inbox-content button');expect(s.$('booking-support').hidden).toBe(false);
 const agency=await boot({role:'agency',setup:(_w,state)=>state.inbox=[{...issue(),category:'agency_records',item_key:'delivery:'+id,reference:null,subject:null}]});await agency.fire('inbox-items button');expect(agency.$('inbox-action-refund').hidden).toBe(true);expect(agency.$('inbox-content').textContent).toContain('NeuraFlow');expect(agency.$('inbox-content').querySelector('button')).toBeNull();
});
test.each([{code:'wrong'},{view:'wrong'},{items:[] ,next_cursor:'bad'},{items:[null]},{items:[{...issue(),review_revision:-1}]},{items:Array(51).fill(issue())}])('inbox rejects malformed list %j',async change=>{
 const s=await boot({handler:(p,b)=>p.endsWith('/inbox/list')?{code:'ok',view:b.view,items:[issue()],next_cursor:null,...change}:undefined});expect(s.$('inbox-items').children).toHaveLength(0);expect(s.$('inbox-status').textContent).toContain('could not confirm');
});
test('inbox handles empty views, rejected notes, oversized bodies and malformed details without writes',async()=>{
 const empty=await boot({setup:(_w,state)=>state.inbox=[]});expect(empty.$('inbox-status').textContent).toContain('No verified');await empty.fire('inbox-issues');expect(empty.$('inbox-status').textContent).toContain('No recorded');await empty.fire('inbox-action-refund');await empty.fire('inbox-action-retry');await empty.fire('inbox-review','submit');expect(empty.calls.some(c=>c.path.endsWith('/review'))).toBe(false);
 for(const response of [()=>new Response('not JSON',{headers:{'content-type':'text/plain'}}),()=>new Response('x'.repeat(65537),{headers:{'content-type':'application/json'}}),()=>Response.json({code:'ok',item:{...issue('enquiry'),enquiry:{}}}),()=>Response.json({code:'ok',item:{...issue(),reviews:[{note:3,created_at:instant}]}})]){
  const s=await boot({handler:p=>p.endsWith('/inbox/detail')?response():undefined});await s.fire('inbox-items button');expect(s.$('inbox-detail').hidden).toBe(true);await expect.poll(()=>s.$('inbox-status').textContent).toContain('could not confirm');
 }
 const s=await boot();await s.fire('inbox-items button');await s.fire('inbox-action-retry');expect(s.$('inbox-review-status').textContent).toContain('First write');await s.fire('inbox-action-refund');expect(s.$('inbox-review-status').textContent).toContain('First write');
});
test.each(['review','retry','refund-verified'])('inbox %s rejection discards only an explicitly rejected operation',async action=>{
 const s=await boot({handler:p=>p.endsWith('/inbox/'+action)?Response.json({code:'revision_changed'},{status:409}):undefined});await s.fire('inbox-items button');s.$('review-note').value='Checked';await s.fire(action==='review'?'inbox-review':action==='retry'?'inbox-action-retry':'inbox-action-refund',action==='review'?'submit':'click');expect(s.$('inbox-retry-review').hidden).toBe(true);expect(s.$('inbox-review-status').textContent).toContain('Another review');
});
test('late inbox list, detail and mutation replies cannot restore data after role loss',async()=>{
 for(const target of ['list','detail','review']){
  let resolve,active=false;const held=new Promise(r=>resolve=r);const s=await boot({handler:p=>active&&p.endsWith('/inbox/'+target)?held:undefined});active=true;
  let operation;if(target==='list')operation=s.fire('inbox-refresh');else if(target==='detail')operation=s.fire('inbox-items button');else{await s.fire('inbox-items button');s.$('review-note').value='Checked';operation=s.fire('inbox-review','submit');}
  await settle();await s.event('studio-role',null);resolve(target==='list'?{code:'ok',view:'enquiries',items:[issue()],next_cursor:null}:target==='detail'?{code:'ok',item:issue()}:{code:'review_saved',revision:1});await operation;expect(s.$('inbox-panel').hidden).toBe(true);expect(s.$('inbox-content').children).toHaveLength(0);expect(s.$('inbox-items').children).toHaveLength(0);
 }
});
test('receipt recovery restores after reload, replaces rejected staging and rejects bad status or blocked storage',async()=>{
 const saved={version:1,request_id:id,secret:'a'.repeat(43)},stage='sarsa:004:receipt-recovery:v1',receipt='sarsa:004:booking-receipt:v1';
 const restored=await boot({recovery:true,setup:w=>w.sessionStorage.setItem(stage,JSON.stringify(saved))});expect(restored.$('recovery-open').hidden).toBe(false);expect(JSON.parse(restored.w.sessionStorage.getItem(receipt))).toEqual(saved);expect(restored.calls).toHaveLength(1);
 const replace=await boot({recovery:true,setup:w=>w.sessionStorage.setItem(stage,JSON.stringify({...saved,request_id:claim})),handler:p=>p.endsWith('/checkout/status')?Response.json({code:'access_unavailable'},{status:403}):undefined});replace.$('recovery-reference').value=id;replace.$('recovery-code').value='12345678';await replace.fire('recovery-form','submit');expect(replace.calls.find(c=>c.path.endsWith('recover-receipt')).body.request_id).toBe(id);
 const bad=await boot({recovery:true,setup:w=>w.sessionStorage.setItem(stage,JSON.stringify(saved)),handler:p=>p.endsWith('/checkout/status')?{request_id:claim,appointment_state:'confirmed'}:undefined});expect(bad.$('recovery-open').hidden).toBe(true);expect(bad.$('recovery-status').textContent).toContain('same code');
 const blocked=await boot({recovery:true,setup:w=>Object.defineProperty(w,'sessionStorage',{value:{getItem:()=>null,setItem:()=>{throw Error('blocked');}}})});blocked.$('recovery-reference').value=id;blocked.$('recovery-code').value='12345678';await blocked.fire('recovery-form','submit');expect(blocked.calls).toHaveLength(0);expect(blocked.$('recovery-status').textContent).toContain('storage');
 const invalid=await boot({recovery:true});await invalid.fire('recovery-form','submit');expect(invalid.$('recovery-status').textContent).toContain('eight-digit');expect(invalid.calls).toHaveLength(0);
});
