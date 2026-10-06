'use strict';
// Private form state stays in memory. The server owns roles, capacity and replay.
const calendarPanel = document.querySelector('#calendar-panel');
const calendarStatus = document.querySelector('#calendar-status');
const actionStatus = document.querySelector('#calendar-action-status');
const calendarItems = document.querySelector('#calendar-items');
const calendarJournal=window.PracticeStaffActions('calendar');
let calendarEpoch=0;
let calendarCursor = null, calendarDay = null, calendarPending = calendarJournal.get()[0] || null, reopenClaim = null;
let calendarZone=null,calendarMonth=null;
let calendarTime={format:()=>{throw Error('The practice time zone is not loaded.');}};
function calendarSetZone(zone){
 if(typeof zone!=='string' || zone.length>100)throw Error('Invalid time zone');
 calendarTime=new Intl.DateTimeFormat('en-IN',{timeZone:zone,dateStyle:'medium',timeStyle:'short'});calendarZone=zone;
 document.querySelectorAll('[data-staff-timezone]').forEach(node=>node.textContent=zone);
}
async function calendarResolve(local){
 if(!calendarZone)throw Error('The practice time zone is not loaded.');
 const value=await calendarApi('resolve-time',{local,timezone:calendarZone});
 if(value.code!=='ok'||value.timezone!==calendarZone||value.local!==local||!Number.isFinite(Date.parse(value.instant)))throw Error('unavailable');
 return value.instant;
}
async function calendarInitialize(){
 if(!studioEnabled || calendarPanel.hidden || busy)return;
 const ticket=calendarEpoch;setBusy(true);
 try{
  const value=await calendarApi('time-context',{});if(ticket!==calendarEpoch)return;
  if(value.code!=='ok'||!/^\d{4}-\d{2}-\d{2}$/.test(value.today))throw Error('unavailable');
  calendarSetZone(value.timezone);
  if(!document.querySelector('#calendar-day').value)document.querySelector('#calendar-day').value=value.today;
  calendarMonth=document.querySelector('#calendar-day').value.slice(0,7)+'-01';
  setBusy(false);await calendarLoad();
 }catch{if(ticket===calendarEpoch)calendarStatus.textContent='We could not load the practice calendar. Refresh to try again.';}
 finally{if(ticket===calendarEpoch)setBusy(false);}
}
async function calendarMonthLoad(ticket){
 const result=await calendarApi('month',{month:calendarMonth});if(ticket!==calendarEpoch)return;
 if(result.code!=='ok'||result.timezone!==calendarZone||result.month!==calendarMonth||!Array.isArray(result.days)||result.days.length<28||result.days.length>31)throw Error('unavailable');
 const month=document.querySelector('#calendar-month');month.replaceChildren();
 document.querySelector('#calendar-month-label').textContent=new Intl.DateTimeFormat('en-IN',{timeZone:'UTC',month:'long',year:'numeric'}).format(new Date(calendarMonth+'T12:00:00Z'));
 for(const label of ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']){const node=document.createElement('span');node.textContent=label;node.className='weekday';month.append(node);}
 const offset=new Date(calendarMonth+'T12:00:00Z').getUTCDay();for(let i=0;i<offset;i++)month.append(document.createElement('span'));
 for(const [index,day] of result.days.entries()){
  if(day.date!==calendarMonth.slice(0,8)+String(index+1).padStart(2,'0')||!Number.isSafeInteger(day.appointments)||day.appointments<0||!Number.isSafeInteger(day.closures)||day.closures<0)throw Error('unavailable');
  const button=document.createElement('button');button.type='button';button.disabled=busy;button.className='secondary';button.textContent=String(index+1);
  button.setAttribute('aria-pressed',String(day.date===document.querySelector('#calendar-day').value));
  button.setAttribute('aria-label',`${day.date}: ${day.appointments} appointments, ${day.closures} blocked periods`);
  if(day.appointments||day.closures){const marker=document.createElement('span');marker.className='day-count';marker.textContent=day.appointments?`${day.appointments} appt`:'Blocked';button.append(marker);}
  button.addEventListener('click',()=>{if(busy||calendarPending)return;document.querySelector('#calendar-day').value=day.date;calendarLoad();});month.append(button);
 }
 document.querySelector('#calendar-month-status').textContent='Dates show saved appointments and blocked periods. Select a date to see its details.';
}
const calendarMessages = {
  time_already_reserved:'That period overlaps a reservation or another blocked period. Refresh the day and choose a different period.',
  invalid_closure:'Check the dates and reason. A blocked period must end in the future, last no more than31 days and end within366 days.',
  invalid_calendar_date:'Choose a day within the last31 days or next366 days.',
  access_unavailable:'Your permission could not be confirmed. Sign in again with Practice’s account.',
  closure_not_found:'That unavailable period could not be found. Refresh this day before continuing.',
  request_conflict:'This saved request conflicts with an earlier change. Refresh the calendar and ask NeuraFlow for help.',
  timezone_changed:'The practice time zone has changed. Refresh the calendar before selecting another time.',
  invalid_local_time:'That local time does not exist. Please check the date and time.',
  please_wait:'Please wait a moment before trying again.',
};
function calendarSyncBusy() {
  calendarPanel.querySelectorAll('input,select,button').forEach(el=>{
    el.disabled = busy || (typeof appointmentPending !== 'undefined' && Boolean(appointmentPending)) || (Boolean(calendarPending) && el.id !== 'calendar-repeat');
  });
  document.querySelector('#calendar-pending').hidden = !calendarPending;
}
async function calendarApi(path, body) {
  if(!studioEnabled || calendarPanel.hidden)throw Error('Page unavailable');
  const response = await fetch('/api/studio/calendar/'+path,{
    method:'POST',credentials:'same-origin',cache:'no-store',redirect:'error',
    headers:{'Content-Type':'application/json','Accept':'application/json'},
    body:JSON.stringify(body),signal:AbortSignal.timeout(15000),
  });
  studioCheckAccess(response);
  if(!response.headers.get('content-type')?.includes('application/json'))throw Error('unavailable');
  const data=await response.json();
  if(!response.ok){const error=Error('unavailable');error.code=data?.code;error.status=response.status;throw error;}
  return data;
}
async function calendarLoad(more=false) {
  if(busy || calendarPanel.hidden)return;
  if(!calendarZone)return calendarInitialize();
  const day=document.querySelector('#calendar-day').value;
  if(!/^\d{4}-\d{2}-\d{2}$/.test(day))return;
  const ticket=calendarEpoch;setBusy(true);calendarStatus.textContent='Checking the practice calendar…';
  try {
    const result=await calendarApi('list',{day,after:more&&calendarDay===day?calendarCursor:null});if(ticket!==calendarEpoch)return;
    if(result.code!=='ok'||result.day!==day||!Array.isArray(result.items)||result.items.length>50)throw Error('unavailable');
    calendarSetZone(result.timezone);
    if(!more || calendarDay!==day)calendarItems.replaceChildren();
    for(const item of result.items){
      if(!['closure','appointment'].includes(item.kind)||!Number.isFinite(Date.parse(item.starts_at))||!Number.isFinite(Date.parse(item.ends_at)))throw Error('unavailable');
      const li=document.createElement('li'),title=document.createElement('strong'),details=document.createElement('p');
      title.textContent=item.kind==='closure'?'Unavailable':(item.service||'Appointment')+' · '+(item.name||'Customer');
      details.textContent=calendarTime.format(new Date(item.starts_at))+' — '+calendarTime.format(new Date(item.ends_at));
      const note=document.createElement('p');note.textContent=item.kind==='closure'?item.reason:'Status: '+item.state;
      li.append(title,details,note);
      if(item.kind==='closure'){
        const button=document.createElement('button');button.type='button';button.disabled=busy;button.className='secondary';button.textContent='Make this time available';
        button.addEventListener('click',()=>{
          if(busy||calendarPending)return;reopenClaim=item.id;document.querySelector('#calendar-reopen').hidden=false;
          document.querySelector('#reopen-period').textContent=details.textContent;document.querySelector('#reopen-reason').value='';
          document.querySelector('#reopen-reason').focus();
        });li.append(button);
      }
      if(item.kind==='appointment' && item.state==='confirmed'){
        const button=document.createElement('button');button.type='button';button.disabled=busy;button.className='secondary';button.textContent='Manage appointment';
        button.addEventListener('click',()=>document.dispatchEvent(new CustomEvent('studio-appointment',{detail:item.id})));li.append(button);
      }
      calendarItems.append(li);
    }
    calendarDay=day;calendarCursor=result.next_cursor;calendarMonth=day.slice(0,7)+'-01';
    try{await calendarMonthLoad(ticket);}catch{if(ticket===calendarEpoch){document.querySelector('#calendar-month').replaceChildren();document.querySelector('#calendar-month-status').textContent='The month could not be checked. Refresh before choosing another date.';}}if(ticket!==calendarEpoch)return;
    document.querySelector('#calendar-more').hidden=!calendarCursor;
    calendarStatus.textContent=calendarItems.children.length?'Saved reservations and unavailable periods are shown below.':'No saved reservations or unavailable periods on this day.';
  }catch(error){if(ticket!==calendarEpoch)return;calendarItems.replaceChildren();calendarCursor=null;document.querySelector('#calendar-more').hidden=true;
    calendarStatus.textContent=calendarMessages[error.code]||'We cannot load this day right now. Please try again.';
  }finally{if(ticket===calendarEpoch)setBusy(false);}
}
async function calendarCheck() {
  if(busy || !studioEnabled || calendarPanel.hidden)return;
  const ticket=calendarEpoch;setBusy(true);
  try {
    const results=await calendarJournal.check(body=>calendarApi('action-result',body),['closed','reopened'],()=>ticket===calendarEpoch);
    if(results===null)return;
    calendarPending=null;reopenClaim=null;
    actionStatus.textContent='Earlier changes checked. The calendar shows the current saved times.';
    document.querySelector('#calendar-reopen').hidden=true;
    setBusy(false);await calendarLoad();
  }catch(error){if(ticket===calendarEpoch)actionStatus.textContent=calendarJournal.error||error.message||'Please check the earlier change again.';}
  finally{if(ticket===calendarEpoch){calendarPending=calendarJournal.get()[0]||null;setBusy(false);calendarSyncBusy();}}
}
async function calendarSave() {
  if(busy||!calendarPending||!studioEnabled||calendarPanel.hidden)return;
  if(!calendarPending.body)return calendarCheck();
  const action=calendarPending,ticket=calendarEpoch;
  setBusy(true);actionStatus.textContent='Saving your change…';
  try{
    await calendarJournal.remember(action.body.operation_id);if(ticket!==calendarEpoch)return;
    const result=await calendarApi(action.path,action.body);if(ticket!==calendarEpoch)return;
    const accepted=action.path==='close'?['closed','existing']:['reopened','already_open','existing'];
    if(!accepted.includes(result.code))throw Error('unavailable');
    if(action.path==='close' && typeof result.active!=='boolean')throw Error('unavailable');
    await calendarJournal.forget(action.body.operation_id);if(ticket!==calendarEpoch)return;
    actionStatus.textContent=action.path==='close'
      ? result.active?'That time is now blocked. Existing appointments have not been changed.':'That earlier blocked period has already been reopened. The calendar has been refreshed.'
      : 'That unavailable period is now open again. Normal booking hours still apply.';
    calendarPending=null;reopenClaim=null;document.querySelector('#calendar-reopen').hidden=true;
    setBusy(false);await calendarLoad();
  }catch(error){
    if(ticket!==calendarEpoch)return;
    if([409,422].includes(error.status)&&['invalid_closure','closure_not_found','time_already_reserved'].includes(error.code)){
      try{await calendarJournal.forget(action.body.operation_id);calendarPending=null;}
      catch{actionStatus.textContent=calendarJournal.error;return;}
    }
    actionStatus.textContent=calendarJournal.error||calendarMessages[error.code]||'We could not confirm the change. Check the same saved request below.';
  }finally{if(ticket===calendarEpoch)setBusy(false);}
}
document.querySelector('#calendar-view').addEventListener('submit',event=>{event.preventDefault();calendarLoad();});
document.querySelector('#calendar-more').addEventListener('click',()=>calendarLoad(true));
document.querySelector('#calendar-close').addEventListener('submit',async event=>{
 event.preventDefault();if(busy||calendarPending||!studioEnabled)return;
 const start=document.querySelector('#closure-start').value,end=document.querySelector('#closure-end').value,ticket=calendarEpoch;
 if(!start||!end||end<=start){actionStatus.textContent='Choose an end time after the start time.';return;}
 setBusy(true);
 try{
  const starts_at=await calendarResolve(start);if(ticket!==calendarEpoch)return;
  const ends_at=await calendarResolve(end);if(ticket!==calendarEpoch)return;
  calendarPending={path:'close',body:{operation_id:crypto.randomUUID(),reason:document.querySelector('#closure-reason').value.trim(),starts_at,ends_at}};
  setBusy(false);await calendarSave();
 }catch(error){if(ticket===calendarEpoch)actionStatus.textContent=calendarMessages[error.code]||'We could not check those times. Refresh and try again.';}
 finally{if(ticket===calendarEpoch)setBusy(false);}
});
document.querySelector('#calendar-reopen').addEventListener('submit',event=>{
  event.preventDefault();if(busy||calendarPending||!reopenClaim)return;
  calendarPending={path:'reopen',body:{operation_id:crypto.randomUUID(),claim_id:reopenClaim,reason:document.querySelector('#reopen-reason').value.trim()}};calendarSave();
});
document.querySelector('#reopen-cancel').addEventListener('click',()=>{if(busy||calendarPending)return;reopenClaim=null;document.querySelector('#calendar-reopen').hidden=true;});
document.querySelector('#calendar-repeat').textContent='Check saved change';
document.querySelector('#calendar-repeat').addEventListener('click',calendarCheck);
document.addEventListener('studio-calendar-hide',()=>{++calendarEpoch;calendarZone=null;document.querySelector('#calendar-month').replaceChildren();document.querySelector('#calendar-month-status').textContent='';calendarPending=calendarJournal.get()[0]||null;calendarItems.replaceChildren();calendarCursor=null;calendarStatus.textContent='';});
document.addEventListener('studio-role',event=>{
  ++calendarEpoch;calendarPending=calendarJournal.get()[0]||null;
  if(event.detail==='client'){calendarSyncBusy();if(calendarPending)actionStatus.textContent='An earlier calendar change needs checking before another change.';setTimeout(()=>calendarInitialize(),0);return;}
  // A mode check can temporarily suspend the page. Keep an uncertain submitted
  // operation so restoring the page cannot invent a second request.
  reopenClaim=null;calendarItems.replaceChildren();calendarCursor=null;actionStatus.textContent='';
  document.querySelector('#calendar-close').reset();document.querySelector('#calendar-reopen').reset();
  document.querySelector('#calendar-reopen').hidden=true;calendarSyncBusy();
});
calendarSyncBusy();

for(const [id,direction] of [['calendar-previous',-1],['calendar-next',1]])document.querySelector('#'+id).addEventListener('click',async()=>{
 if(busy||calendarPending||!calendarMonth||!calendarZone)return;const ticket=calendarEpoch;
 const date=new Date(calendarMonth+'T12:00:00Z');date.setUTCMonth(date.getUTCMonth()+direction);calendarMonth=date.toISOString().slice(0,10);setBusy(true);
 try{await calendarMonthLoad(ticket);}catch(error){if(ticket===calendarEpoch){document.querySelector('#calendar-month').replaceChildren();document.querySelector('#calendar-month-status').textContent=calendarMessages[error.code]||'We cannot load this month right now.';}}
 finally{if(ticket===calendarEpoch)setBusy(false);}
});
