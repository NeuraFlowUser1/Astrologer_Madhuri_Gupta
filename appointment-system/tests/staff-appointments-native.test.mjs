import {test} from 'node:test';
import assert from 'node:assert/strict';
import {staffFixture,available,id,other,waitText,within} from './staff-page-fixture.mjs';
const record=()=>({code:'ok',reference:id,claim_id:other,revision:2,name:'Fixture Person',service:'Synthetic consultation',state:'confirmed',starts_at:'2031-04-04T10:30:00Z',can_cancel:true,can_reschedule:true,policy_guidance:'staff_review',email:'fixture@example.test',phone:'+919999999999',unresolved_payments:0,payments:[{payment_id:'pay_fixture',status:'captured',amount_paise:100,refunded_paise:0,observed_at:'2031-04-01T10:30:00Z'}]});
async function lookup(page,state,row=record()){
 state.handlers.set('/api/studio/appointments/lookup',({reply})=>reply(row));state.handlers.set('/api/studio/appointments/detail',({reply})=>reply(row));
 await page.fill('#booking-reference',id);await page.locator('#booking-lookup button').click();await page.locator('#booking-support').waitFor();
}
async function open(page,state,row=record()){await lookup(page,state,row);await page.click('#booking-support-manage');await page.locator('#appointment-cancel').waitFor();}
async function cancel(page){await page.fill('#appointment-reason','Synthetic cancellation');await page.check('#appointment-ack');await page.locator('#appointment-cancel button').click();}
test('staff cancellation and reschedule preserve revision, practice time, and separate refund handling',{skip:!available},()=>staffFixture(async(page,state)=>{
 await open(page,state);state.handlers.set('/api/studio/appointments/reschedule',({body,reply})=>reply({code:'rescheduled',revision:3,starts_at:body.starts_at}));
 await page.fill('#appointment-start','2031-04-05T17:00');await page.fill('#appointment-move-reason','Synthetic time change');await page.locator('#appointment-reschedule button').click();await waitText(page,'#appointment-status','No extra payment');
 const moved=state.calls.find(x=>x.path.endsWith('/appointments/reschedule'));assert.equal(moved.body.starts_at,'2031-04-05T11:30:00.000Z');assert.equal(moved.body.expected_revision,2);assert.equal(moved.body.claim_id,other);
 await open(page,state);state.handlers.set('/api/studio/appointments/cancel',({reply})=>reply({code:'cancelled',revision:3}));await cancel(page);await waitText(page,'#appointment-status','No refund has been issued');assert.match(await page.locator('#appointment-summary').textContent(),/Status: cancelled/);
 assert.equal(await page.evaluate(()=>window.PracticeStaffActions('client').get().length),0);
}));
test('saved support code and contact correction only follow verified staff evidence and are never persisted',{skip:!available},()=>staffFixture(async(page,state)=>{
 for(const action of ['receipt_recovery','contact_correction']){
  await lookup(page,state);await page.selectOption('#support-action',action);if(action==='contact_correction'){await page.fill('#support-email','corrected@example.test');await page.fill('#support-phone','+918888888888');}
  await page.fill('#support-payment','pay_fixture');await page.fill('#support-reason','Synthetic verified evidence');await page.check('#support-verified');
  state.handlers.set('/api/studio/appointments/support',({body,reply})=>reply({code:'support_saved',revision:body.expected_revision+(body.action==='contact_correction'?1:0),active:true,activation_code:'12345678',expires_at:'2031-04-04T10:45:00Z'}));
  await page.locator('#booking-support-change button').click();await page.locator('#support-code-result').waitFor();assert.equal(await page.locator('#support-code').textContent(),'12345678');
  const saved=state.calls.filter(x=>x.path.endsWith('/appointments/support')).at(-1);assert.equal(saved.body.verification_confirmed,true);assert.equal(saved.body.reference,id);
  assert.equal(Object.hasOwn(saved.body,'email'),action==='contact_correction');
  const stored=await page.evaluate(()=>JSON.stringify(localStorage));for(const privateValue of ['12345678','corrected@example.test','Synthetic verified evidence'])assert.equal(stored.includes(privateValue),false);
 }
 assert.match(await page.locator('#booking-support-status').textContent(),/Old receipt access is revoked/);
}));
test('lost staff change reply remains pending when the returned result belongs to another action',{skip:!available},()=>staffFixture(async(page,state)=>{
 await open(page,state);let operation;
 state.handlers.set('/api/studio/appointments/cancel',({body,reply})=>{operation=body.operation_id;reply({code:'uncertain'},503);});await cancel(page);await waitText(page,'#appointment-status','could not confirm');
 await page.reload();await page.locator('#appointment-repeat').waitFor();
 state.handlers.set('/api/studio/appointments/action-result',({reply})=>reply({code:'cancelled',operation_id:id}));await page.click('#appointment-repeat');await page.waitForFunction(()=>!document.querySelector('#appointment-repeat').disabled);
 assert.equal(await page.evaluate(()=>window.PracticeStaffActions('client').get().length),1,'A reply for a different action must not clear the saved operation');
 state.handlers.set('/api/studio/appointments/action-result',({body,reply})=>reply({code:'cancelled',operation_id:body.operation_id}));await page.click('#appointment-repeat');await waitText(page,'#appointment-status','Earlier actions checked');
 assert.equal(state.calls.filter(x=>x.path.endsWith('/appointments/cancel')).length,1);assert.ok(state.calls.filter(x=>x.path.endsWith('/appointments/action-result')).every(x=>x.body.operation_id===operation));
}));
test('rejected move preserves the booking and clears the rejected operation without another submission',{skip:!available},()=>staffFixture(async(page,state)=>{
 await open(page,state);state.handlers.set('/api/studio/appointments/reschedule',({reply})=>reply({code:'time_already_reserved'},409));
 await page.fill('#appointment-start','2031-04-05T17:00');await page.fill('#appointment-move-reason','Synthetic unavailable time');await page.locator('#appointment-reschedule button').click();await waitText(page,'#appointment-status','original appointment has not moved');
 assert.equal(await page.evaluate(()=>window.PracticeStaffActions('client').get().length),0);assert.match(await page.locator('#appointment-summary').textContent(),/Status: confirmed/);assert.equal(await page.locator('#appointment-reschedule').isVisible(),false);
}));
test('invalid lookup and wrong booking identity never expose support controls',{skip:!available},()=>staffFixture(async(page,state)=>{
 await page.fill('#booking-reference','invalid');await page.locator('#booking-lookup').evaluate(form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));await waitText(page,'#booking-support-status','complete booking reference');assert.equal(state.calls.filter(x=>x.path.endsWith('/lookup')).length,0);
 state.handlers.set('/api/studio/appointments/lookup',({reply})=>reply({...record(),reference:other}));await page.fill('#booking-reference',id);await page.locator('#booking-lookup button').click();await waitText(page,'#booking-support-status','could not load');assert.equal(await page.locator('#booking-support-change').isVisible(),false);
 await lookup(page,state,{...record(),state:'held',payments:[],claim_id:null});assert.equal(await page.locator('#booking-support-change').isVisible(),false);assert.equal(await page.locator('#booking-support-manage').isVisible(),false);assert.match(await page.locator('#booking-support-content').textContent(),/No payment evidence/);
}));
test('invalid appointment detail and permission loss hide the saved customer information',{skip:!available},()=>staffFixture(async(page,state)=>{
 await lookup(page,state);state.handlers.set('/api/studio/appointments/detail',({reply})=>reply({...record(),claim_id:id}));await page.click('#booking-support-manage');await waitText(page,'#appointment-status','could not confirm');assert.equal(await page.locator('#appointment-cancel').isVisible(),false);
 state.handlers.set('/api/studio/appointments/lookup',({reply})=>reply({code:'access_unavailable'},403));await page.locator('#booking-lookup button').click();await waitText(page,'#status','Sign in again');assert.equal(await page.locator('#booking-support').isVisible(),false);assert.equal(await page.locator('#booking-support-content').textContent(),'');
}));
test('unconfirmed cancellation checks the saved result without sending another cancellation',{skip:!available},()=>staffFixture(async(page,state)=>{
 await open(page,state);state.handlers.set('/api/studio/appointments/cancel',({reply})=>reply({code:'cancelled',revision:99}));await cancel(page);await waitText(page,'#appointment-status','could not confirm');
 const submitted=state.calls.find(x=>x.path.endsWith('/cancel')).body;
 state.handlers.set('/api/studio/appointments/action-result',({body,reply})=>reply({code:'operation_not_found',operation_id:body.operation_id}));await page.click('#appointment-repeat');await page.waitForFunction(()=>!document.querySelector('#appointment-repeat').disabled);
 assert.equal(await page.evaluate(()=>window.PracticeStaffActions('client').get().length),1,'A fresh missing result can still be in flight');
 for(const code of ['operation_conflict','unexpected']){state.handlers.set('/api/studio/appointments/action-result',({body,reply})=>reply({code,operation_id:body.operation_id}));await page.click('#appointment-repeat');await page.waitForFunction(()=>!document.querySelector('#appointment-repeat').disabled);assert.equal(await page.evaluate(()=>window.PracticeStaffActions('client').get().length),1);}
 state.handlers.set('/api/studio/appointments/action-result',({body,reply})=>reply({code:'cancelled',operation_id:body.operation_id}));await page.click('#appointment-repeat');await waitText(page,'#appointment-status','Earlier actions checked');
 assert.equal(state.calls.filter(x=>x.path.endsWith('/cancel')).length,1);assert.equal(submitted.expected_revision,2);
}));
test('support result validation preserves uncertain work and recovers only its matching saved code',{skip:!available},()=>staffFixture(async(page,state)=>{
 await lookup(page,state);await page.fill('#support-payment','pay_fixture');await page.fill('#support-reason','Synthetic saved evidence');await page.check('#support-verified');
 state.handlers.set('/api/studio/appointments/support',({reply})=>reply({code:'support_saved',revision:2,active:true,expires_at:'invalid',activation_code:'12345678'}));
 await page.locator('#booking-support-change button').click();await waitText(page,'#booking-support-status','could not confirm');assert.equal(await page.locator('#support-code-result').isVisible(),false);
 state.handlers.set('/api/studio/appointments/action-result',({body,reply})=>reply({code:'support_saved',operation_id:body.operation_id,active:true,activation_code:'12345678'}));await page.click('#support-repeat');await waitText(page,'#appointment-status','Earlier actions checked');assert.equal(await page.locator('#support-code').textContent(),'12345678');
 assert.equal(state.calls.filter(x=>x.path.endsWith('/support')).length,1);assert.equal(await page.evaluate(()=>window.PracticeStaffActions('client').get().length),0);
}));
test('inactive support code is never displayed and rejected evidence cannot change a contact',{skip:!available},()=>staffFixture(async(page,state)=>{
 for(const rejection of [false,true]){
  await lookup(page,state);await page.fill('#support-payment','pay_fixture');await page.fill('#support-reason','Synthetic saved evidence');await page.check('#support-verified');
  state.handlers.set('/api/studio/appointments/support',({reply})=>rejection?reply({code:'support_verification_unavailable'},409):reply({code:'support_saved',revision:2,active:false,expires_at:'2031-04-04T10:45:00Z'}));
  await page.locator('#booking-support-change button').click();await waitText(page,'#booking-support-status',rejection?'No change has been made':'no longer active');assert.equal(await page.locator('#support-code-result').isVisible(),false);assert.equal(await page.locator('#booking-support-change').isVisible(),false);assert.equal(await page.evaluate(()=>window.PracticeStaffActions('client').get().length),0);
 }
}));
test('practice time rejection never submits a move and unacknowledged cancellation is blocked',{skip:!available},()=>staffFixture(async(page,state)=>{
 await open(page,state);await page.locator('#appointment-cancel').evaluate(form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));assert.equal(state.calls.filter(x=>x.path.endsWith('/cancel')).length,0);
 state.handlers.set('/api/studio/calendar/resolve-time',({reply})=>reply({code:'invalid_local_time'},422));await page.fill('#appointment-start','2031-04-05T17:00');await page.fill('#appointment-move-reason','Synthetic request');await page.locator('#appointment-reschedule button').click();await waitText(page,'#appointment-status','time');
 assert.equal(state.calls.filter(x=>x.path.endsWith('/reschedule')).length,0);assert.equal(await page.evaluate(()=>window.PracticeStaffActions('client').get().length),0);
}));
test('a late detail reply after permission loss cannot restore private customer information',{skip:!available},()=>staffFixture(async(page,state)=>{
 await lookup(page,state);let finish;state.handlers.set('/api/studio/appointments/detail',({reply})=>{finish=()=>reply(record());});await page.click('#booking-support-manage');await page.waitForFunction(()=>document.querySelector('#calendar-next').disabled);
 await page.evaluate(()=>document.dispatchEvent(new CustomEvent('studio-role',{detail:null})));finish();await page.waitForTimeout(50);
 assert.equal(await page.locator('#appointment-detail').isVisible(),false);assert.equal(await page.locator('#appointment-summary').textContent(),'');assert.equal(await page.locator('#booking-support-content').textContent(),'');
}));
test('non JSON reply and expired mutation permissions never claim success or retain private details',{skip:!available},()=>staffFixture(async(page,state)=>{
 await open(page,state);state.handlers.set('/api/studio/appointments/cancel',({res})=>{res.writeHead(200,{'content-type':'text/html'});res.end('<html>Gateway error</html>');});await cancel(page);await waitText(page,'#appointment-status','could not confirm');
 state.handlers.set('/api/studio/appointments/action-result',({reply})=>reply({code:'access_unavailable'},401));await page.click('#appointment-repeat');await waitText(page,'#status','Sign in again');assert.equal(await page.locator('#appointment-summary').textContent(),'');assert.equal(await page.locator('#booking-support-content').textContent(),'');assert.equal(await page.evaluate(()=>window.PracticeStaffActions('client').get().length),1);
}));
for(const path of ['lookup','cancel','support','action-result'])test(`late appointment ${path} reply cannot restore private information after OFF`,{skip:!available},()=>staffFixture(async(page,state)=>{
 const received=Promise.withResolvers();
 if(path==='cancel'||path==='action-result')await open(page,state);else if(path==='support')await lookup(page,state);
 if(path==='action-result'){
  state.handlers.set('/api/studio/appointments/cancel',({reply})=>reply({code:'unknown'},503));await cancel(page);await waitText(page,'#appointment-status','could not confirm');
 }
 state.handlers.set('/api/studio/appointments/'+path,({body,reply})=>{received.resolve(()=>reply(path==='lookup'?record():path==='support'?{code:'support_saved',revision:2,active:true,activation_code:'12345678',expires_at:'2031-04-04T10:45:00Z'}:{code:'cancelled',revision:3,operation_id:body.operation_id}));});
 if(path==='cancel')await cancel(page);
 else if(path==='lookup'){await page.fill('#booking-reference',id);await page.locator('#booking-lookup button').click();}
 else if(path==='action-result')await page.click('#appointment-repeat');
 else{await page.fill('#support-payment','pay_fixture');await page.fill('#support-reason','Synthetic verified evidence');await page.check('#support-verified');await page.locator('#booking-support-change button').click();}
 const finish=await within(received.promise);state.enabled=false;await page.evaluate(()=>window.bookingVisibility.refresh({force:true}));finish();await page.waitForTimeout(50);
 assert.equal(await page.locator('#booking-support-content').textContent(),'');assert.equal(await page.locator('#appointment-summary').textContent(),'');assert.equal(await page.locator('#support-code').textContent(),'');
 if(path!=='lookup')assert.equal(await page.evaluate(()=>window.PracticeStaffActions('client').get().length),1);
}));
test('a definitively missing old action releases its saved marker without repeating a booking change',{skip:!available},()=>staffFixture(async(page,state)=>{
 await open(page,state);state.handlers.set('/api/studio/appointments/cancel',({reply})=>reply({code:'unknown'},503));await cancel(page);await waitText(page,'#appointment-status','could not confirm');
 await page.evaluate(()=>{const now=Date.now;Date.now=()=>now()+300001;});
 state.handlers.set('/api/studio/appointments/action-result',({body,reply})=>reply({code:'operation_not_found',operation_id:body.operation_id}));await page.click('#appointment-repeat');await waitText(page,'#appointment-status','Earlier actions checked');
 assert.equal(await page.evaluate(()=>window.PracticeStaffActions('client').get().length),0);assert.equal(state.calls.filter(x=>x.path.endsWith('/appointments/cancel')).length,1);
}));
test('private support cannot submit without verification or while browser storage is unavailable',{skip:!available},()=>staffFixture(async(page,state)=>{
 await lookup(page,state);await page.locator('#booking-support-change').evaluate(form=>form.dispatchEvent(new Event('submit',{cancelable:true})));assert.equal(state.calls.filter(x=>x.path.endsWith('/appointments/support')).length,0);
 await page.fill('#support-payment','pay_fixture');await page.fill('#support-reason','Synthetic verified evidence');await page.check('#support-verified');
 await page.evaluate(()=>{Storage.prototype.setItem=()=>{throw Error('Synthetic unavailable storage');};});await page.locator('#booking-support-change button').click();await waitText(page,'#booking-support-status','could not safely save');
 assert.equal(state.calls.filter(x=>x.path.endsWith('/appointments/support')).length,0);assert.equal(await page.locator('#support-code-result').isVisible(),false);
}));
