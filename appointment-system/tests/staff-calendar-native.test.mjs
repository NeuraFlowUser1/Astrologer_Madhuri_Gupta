import {test} from 'node:test';
import assert from 'node:assert/strict';
import {staffFixture,available,id,other,waitText,within} from './staff-page-fixture.mjs';
const closure={id,kind:'closure',starts_at:'2031-04-04T10:30:00Z',ends_at:'2031-04-04T10:50:00Z',reason:'Synthetic private commitment'};
async function refresh(page){await page.locator('#calendar-view button').click();await page.waitForFunction(()=>!document.querySelector('#calendar-next').disabled);}
async function block(page,start='2031-04-04T16:00',end='2031-04-04T16:20'){
 await page.fill('#closure-start',start);await page.fill('#closure-end',end);await page.fill('#closure-reason','Synthetic unavailability');await page.locator('#calendar-close button').click();
}
test('calendar marks appointments, changes month without altering reservations, and pages through saved periods',{skip:!available},()=>staffFixture(async(page,state)=>{
 assert.equal(await page.getByRole('button',{name:'2031-04-04: 1 appointments, 0 blocked periods',exact:true}).textContent(),'41 appt');
 await page.click('#calendar-next');await waitText(page,'#calendar-month-label','May');await page.click('#calendar-previous');await waitText(page,'#calendar-month-label','April');
 state.handlers.set('/api/studio/calendar/list',({body,reply})=>reply({code:'ok',day:body.day,timezone:'Asia/Kolkata',items:[body.after?{...closure,id:other}:closure],next_cursor:body.after?null:id}));await refresh(page);
 await page.click('#calendar-more');await page.waitForFunction(()=>document.querySelectorAll('#calendar-items li').length===2);assert.equal(state.calls.filter(x=>x.path.endsWith('/calendar/list')).at(-1).body.after,id);
 await page.getByRole('button',{name:'2031-04-05: 0 appointments, 1 blocked periods',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#calendar-day').value==='2031-04-05'&&!document.querySelector('#calendar-next').disabled);
 assert.equal(state.calls.filter(x=>x.path.endsWith('/calendar/list')).at(-1).body.after,null);
}));
test('staff blocks and reopens an exact practice-local period without changing existing appointments',{skip:!available},()=>staffFixture(async(page,state)=>{
 state.handlers.set('/api/studio/calendar/close',({reply})=>reply({code:'closed',active:true}));await block(page);await waitText(page,'#calendar-action-status','Existing appointments have not been changed');
 const sent=state.calls.find(x=>x.path.endsWith('/calendar/close'));assert.equal(sent.body.starts_at,'2031-04-04T10:30:00.000Z');assert.equal(sent.body.ends_at,'2031-04-04T10:50:00.000Z');
 state.handlers.set('/api/studio/calendar/list',({body,reply})=>reply({code:'ok',day:body.day,timezone:'Asia/Kolkata',items:[closure],next_cursor:null}));await refresh(page);
 await page.getByRole('button',{name:'Make this time available',exact:true}).click();await page.click('#reopen-cancel');assert.equal(await page.locator('#calendar-reopen').isVisible(),false);
 await page.getByRole('button',{name:'Make this time available',exact:true}).click();await page.fill('#reopen-reason','Synthetic commitment removed');state.handlers.set('/api/studio/calendar/reopen',({reply})=>reply({code:'reopened'}));await page.locator('#calendar-reopen button[type=submit]').click();await waitText(page,'#calendar-action-status','Normal booking hours still apply');
 assert.equal(state.calls.find(x=>x.path.endsWith('/calendar/reopen')).body.claim_id,id);assert.equal(await page.evaluate(()=>window.PracticeStaffActions('calendar').get().length),0);
}));
test('bad local time and overlapping reservation keep the calendar unchanged and allow a corrected request',{skip:!available},()=>staffFixture(async(page,state)=>{
 await block(page,'2031-04-04T16:20','2031-04-04T16:00');await waitText(page,'#calendar-action-status','end time after');assert.equal(state.calls.filter(x=>x.path.endsWith('/calendar/close')).length,0);
 state.handlers.set('/api/studio/calendar/resolve-time',({reply})=>reply({code:'invalid_local_time'},422));await block(page);await waitText(page,'#calendar-action-status','local time does not exist');assert.equal(state.calls.filter(x=>x.path.endsWith('/calendar/close')).length,0);
 state.handlers.delete('/api/studio/calendar/resolve-time');state.handlers.set('/api/studio/calendar/close',({reply})=>reply({code:'time_already_reserved'},409));await block(page);await waitText(page,'#calendar-action-status','overlaps a reservation');assert.equal(await page.evaluate(()=>window.PracticeStaffActions('calendar').get().length),0);
 state.handlers.set('/api/studio/calendar/close',({reply})=>reply({code:'existing',active:false}));await block(page);await waitText(page,'#calendar-action-status','already been reopened');
}));
test('unknown closure outcome is retained until an exact saved result is read, without repeating its write',{skip:!available},()=>staffFixture(async(page,state)=>{
 let operation;state.handlers.set('/api/studio/calendar/close',({body,reply})=>{operation=body.operation_id;reply({code:'closed',active:1});});await block(page);await waitText(page,'#calendar-action-status','could not confirm');
 assert.equal(await page.evaluate(()=>window.PracticeStaffActions('calendar').get().length),1);assert.equal(await page.locator('#closure-start').isDisabled(),true);
 state.handlers.set('/api/studio/calendar/action-result',({reply})=>reply({code:'closed',operation_id:other}));await page.click('#calendar-repeat');await waitText(page,'#calendar-action-status','still needs checking');
 state.handlers.set('/api/studio/calendar/action-result',({body,reply})=>reply({code:'closed',operation_id:body.operation_id}));await page.click('#calendar-repeat');await waitText(page,'#calendar-action-status','Earlier changes checked');assert.equal(state.calls.filter(x=>x.path.endsWith('/calendar/close')).length,1);assert.equal(state.calls.filter(x=>x.path.endsWith('/calendar/action-result')).at(-1).body.operation_id,operation);
}));
test('malformed day and month data clear stale calendar results without enabling a mutation',{skip:!available},()=>staffFixture(async(page,state)=>{
 for(const change of [{day:'different'}, {items:Array(51).fill(closure)}, {items:[{...closure,kind:'unknown'}]}, {items:[{...closure,ends_at:'bad'}]}, {timezone:'Not/AZone'}]){
  state.handlers.set('/api/studio/calendar/list',({body,reply})=>reply({code:'ok',day:body.day,timezone:'Asia/Kolkata',items:[closure],next_cursor:null,...change}));await refresh(page);await waitText(page,'#calendar-status','cannot load');assert.equal(await page.locator('#calendar-items li').count(),0);
 }
 state.handlers.delete('/api/studio/calendar/list');state.handlers.set('/api/studio/calendar/month',({body,reply})=>reply({code:'ok',month:body.month,timezone:'Asia/Kolkata',days:[]}));await refresh(page);await waitText(page,'#calendar-month-status','could not be checked');assert.equal(await page.locator('#calendar-month button').count(),0);
 await page.click('#calendar-next');await waitText(page,'#calendar-month-status','cannot load this month');
 assert.equal(state.calls.filter(x=>x.path.endsWith('/calendar/close')||x.path.endsWith('/calendar/reopen')).length,0);
}));
test('calendar appointment rows open the exact booking and cancelled rows offer no change action',{skip:!available},()=>staffFixture(async(page,state)=>{
 const appointment={...closure,kind:'appointment',state:'confirmed',service:'Synthetic consultation',name:'Fixture Person'};
 state.handlers.set('/api/studio/calendar/list',({body,reply})=>reply({code:'ok',day:body.day,timezone:'Asia/Kolkata',items:[appointment,{...appointment,id:other,state:'cancelled',service:'',name:''}],next_cursor:null}));
 state.handlers.set('/api/studio/appointments/detail',({reply})=>reply({code:'ok',claim_id:id,revision:1,can_cancel:false,can_reschedule:false,policy_guidance:'full_refund_review',starts_at:appointment.starts_at,name:appointment.name,service:appointment.service,state:'cancelled',reference:other}));
 await refresh(page);assert.equal(await page.getByRole('button',{name:'Manage appointment',exact:true}).count(),1);await page.getByRole('button',{name:'Manage appointment',exact:true}).click();await page.locator('#appointment-detail').waitFor();assert.equal(state.calls.filter(x=>x.path.endsWith('/appointments/detail')).at(-1).body.claim_id,id);assert.equal(await page.locator('#appointment-cancel').isVisible(),false);
}));
test('month rows require exact date and nonnegative counts, and invalid initial time zone cannot enable calendar use',{skip:!available},()=>staffFixture(async(page,state)=>{
 for(const changes of [{date:'2031-04-02'},{appointments:-1},{closures:1.5},{appointments:'1'}]){
  state.handlers.set('/api/studio/calendar/month',({body,reply})=>reply({code:'ok',month:body.month,timezone:'Asia/Kolkata',days:Array.from({length:30},(_,i)=>({date:'2031-04-'+String(i+1).padStart(2,'0'),appointments:0,closures:0,...(i===0?changes:{})}))}));
  await refresh(page);await waitText(page,'#calendar-month-status','could not be checked');assert.equal(await page.locator('#calendar-month button').count(),0);
 }
 state.handlers.delete('/api/studio/calendar/month');state.handlers.set('/api/studio/calendar/time-context',({reply})=>reply({code:'ok',today:'2031-04-04',timezone:42}));await page.reload();await waitText(page,'#calendar-status','could not load the practice calendar');assert.equal(await page.locator('#calendar-items li').count(),0);
}));
test('changed time-zone reply cannot reserve a period and HTML gateway replies never render as calendar data',{skip:!available},()=>staffFixture(async(page,state)=>{
 state.handlers.set('/api/studio/calendar/resolve-time',({body,reply})=>reply({code:'ok',local:body.local,timezone:'UTC',instant:'2031-04-04T10:30:00Z'}));await block(page);await waitText(page,'#calendar-action-status','could not check those times');assert.equal(state.calls.filter(x=>x.path.endsWith('/calendar/close')).length,0);
 state.handlers.set('/api/studio/calendar/list',({res})=>{res.writeHead(200,{'content-type':'text/html'});res.end('<h1>Temporary gateway failure</h1>');});await refresh(page);await waitText(page,'#calendar-status','cannot load');assert.equal(await page.locator('#calendar-items li').count(),0);
}));
test('reloaded uncertain closure only checks its saved result, and reopen refusal clears only the rejected request',{skip:!available},()=>staffFixture(async(page,state)=>{
 state.handlers.set('/api/studio/calendar/close',({reply})=>reply({code:'unknown'},503));await block(page);await waitText(page,'#calendar-action-status','could not confirm');await page.reload();await page.locator('#calendar-repeat').waitFor();
 state.handlers.set('/api/studio/calendar/action-result',({body,reply})=>reply({code:'closed',operation_id:body.operation_id}));await page.click('#calendar-repeat');await waitText(page,'#calendar-action-status','Earlier changes checked');assert.equal(state.calls.filter(x=>x.path.endsWith('/calendar/close')).length,1);
 state.handlers.set('/api/studio/calendar/list',({body,reply})=>reply({code:'ok',day:body.day,timezone:'Asia/Kolkata',items:[closure],next_cursor:null}));await refresh(page);await page.getByRole('button',{name:'Make this time available',exact:true}).click();await page.fill('#reopen-reason','Synthetic reason');state.handlers.set('/api/studio/calendar/reopen',({reply})=>reply({code:'closure_not_found'},409));await page.locator('#calendar-reopen button[type=submit]').click();await waitText(page,'#calendar-action-status','could not be found');assert.equal(await page.evaluate(()=>window.PracticeStaffActions('calendar').get().length),0);
}));
test('calendar hides late results after loss of the client role',{skip:!available},()=>staffFixture(async(page,state)=>{
 let finish;state.handlers.set('/api/studio/calendar/list',({body,reply})=>{finish=()=>reply({code:'ok',day:body.day,timezone:'Asia/Kolkata',items:[closure],next_cursor:null});});await page.locator('#calendar-view button').click();await page.waitForFunction(()=>document.querySelector('#calendar-next').disabled);await page.evaluate(()=>document.dispatchEvent(new CustomEvent('studio-role',{detail:null})));finish();await page.waitForTimeout(50);assert.equal(await page.locator('#calendar-items li').count(),0);
}));
test('calendar cannot write when browser storage fails, and a failed acknowledgement cleanup keeps the same operation',{skip:!available},()=>staffFixture(async(page,state)=>{
 await page.evaluate(()=>{window.originalStore=Storage.prototype.setItem;Storage.prototype.setItem=()=>{throw Error('Synthetic storage failure');};});
 await block(page);await waitText(page,'#calendar-action-status','could not safely save');
 assert.equal(state.calls.filter(x=>x.path.endsWith('/calendar/close')).length,0);
 await page.reload();await page.waitForFunction(()=>!!document.querySelector('#calendar-month button')&&!document.querySelector('#calendar-next').disabled);
 state.handlers.set('/api/studio/calendar/close',({reply})=>reply({code:'closed',active:true}));
 await page.evaluate(()=>{const original=Storage.prototype.setItem;Storage.prototype.setItem=function(key,value){if(value==='[]')throw Error('Synthetic acknowledgement storage failure');return original.call(this,key,value);};});
 await block(page);await waitText(page,'#calendar-action-status','could not safely save');
 assert.equal(await page.evaluate(()=>window.PracticeStaffActions('calendar').get().length),1);
 assert.equal(state.calls.filter(x=>x.path.endsWith('/calendar/close')).length,1);
}));
for(const path of ['close','action-result','resolve-time','month'])test(`a late calendar ${path} reply cannot restore controls or write again after OFF`,{skip:!available},()=>staffFixture(async(page,state)=>{
 const received=Promise.withResolvers();
 if(path==='action-result'){
  state.handlers.set('/api/studio/calendar/close',({reply})=>reply({code:'unknown'},503));await block(page);await waitText(page,'#calendar-action-status','could not confirm');
 }
 state.handlers.set('/api/studio/calendar/'+path,({body,reply})=>{received.resolve(()=>reply(path==='resolve-time'?{code:'ok',local:body.local,timezone:body.timezone,instant:'2031-04-04T10:30:00Z'}:path==='month'?{code:'ok',month:body.month,timezone:'Asia/Kolkata',days:[]}:{code:'closed',active:true,operation_id:body.operation_id}));});
 if(path==='action-result')await page.click('#calendar-repeat');else if(path==='month')await page.click('#calendar-next');else await block(page);
 const finish=await within(received.promise);state.enabled=false;await page.evaluate(()=>window.bookingVisibility.refresh({force:true}));finish();await page.waitForTimeout(50);
 assert.equal(await page.locator('#calendar-panel').isVisible(),false);
 assert.equal(await page.locator('#calendar-month button').count(),0);
 assert.equal(state.calls.filter(x=>x.path.endsWith('/calendar/close')).length,path==='close'||path==='action-result'?1:0);
 if(path==='close'||path==='action-result')assert.equal(await page.evaluate(()=>window.PracticeStaffActions('calendar').get().length),1);
}));
test('duplicate calendar actions and empty dates cannot submit while another period is unresolved',{skip:!available},()=>staffFixture(async(page,state)=>{
 await page.fill('#calendar-day','');await page.locator('#calendar-view').evaluate(form=>form.dispatchEvent(new Event('submit',{cancelable:true})));
 const count=state.calls.filter(x=>x.path.endsWith('/calendar/list')).length;await page.waitForTimeout(25);assert.equal(state.calls.filter(x=>x.path.endsWith('/calendar/list')).length,count);
 state.handlers.set('/api/studio/calendar/close',({reply})=>reply({code:'unknown'},503));await block(page);await waitText(page,'#calendar-action-status','could not confirm');
 await page.evaluate(()=>{for(const id of ['calendar-close','calendar-reopen'])document.querySelector('#'+id).dispatchEvent(new Event('submit',{cancelable:true}));document.querySelector('#calendar-next').dispatchEvent(new Event('click'));});
 assert.equal(state.calls.filter(x=>x.path.endsWith('/calendar/close')).length,1);assert.equal(state.calls.filter(x=>x.path.endsWith('/calendar/reopen')).length,0);
}));
test('invalid initial day and delayed initial context cannot enable or revive a calendar',{skip:!available},()=>staffFixture(async(page,state)=>{
 state.handlers.set('/api/studio/calendar/time-context',({reply})=>reply({code:'ok',timezone:'Asia/Kolkata',today:'not-a-day'}));await page.reload();await waitText(page,'#calendar-status','could not load');assert.equal(await page.locator('#calendar-month button').count(),0);
 const received=Promise.withResolvers();state.handlers.set('/api/studio/calendar/time-context',({reply})=>received.resolve(()=>reply({code:'ok',timezone:'Asia/Kolkata',today:'2031-04-04'})));
 await page.fill('#calendar-day','2031-04-04');await page.locator('#calendar-view button').click();const finish=await within(received.promise);state.enabled=false;await page.evaluate(()=>window.bookingVisibility.refresh({force:true}));finish();await page.waitForTimeout(50);
 assert.equal(await page.locator('#calendar-month button').count(),0);assert.equal(await page.locator('#calendar-panel').isVisible(),false);
}));
