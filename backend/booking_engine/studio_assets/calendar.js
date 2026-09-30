'use strict';
// Private form state stays in memory. The server owns roles, capacity and replay.
const calendarPanel = document.querySelector('#calendar-panel');
const calendarStatus = document.querySelector('#calendar-status');
const actionStatus = document.querySelector('#calendar-action-status');
const calendarItems = document.querySelector('#calendar-items');
let calendarCursor = null, calendarDay = null, calendarPending = null, reopenClaim = null;
const calendarDate = new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit'});
const calendarTime = new Intl.DateTimeFormat('en-IN',{timeZone:'Asia/Kolkata',dateStyle:'medium',timeStyle:'short'});
document.querySelector('#calendar-day').value = calendarDate.format(new Date());
const calendarMessages = {
  time_already_reserved:'That period overlaps a reservation or another blocked period. Refresh the day and choose a different period.',
  invalid_closure:'Check the dates and reason. A blocked period must end in the future, last no more than31 days and end within366 days.',
  invalid_calendar_date:'Choose a day within the last31 days or next366 days.',
  access_unavailable:'Your permission could not be confirmed. Sign in again with Sarsa’s account.',
  closure_not_found:'That unavailable period could not be found. Refresh this day before continuing.',
  request_conflict:'This saved request conflicts with an earlier change. Refresh the calendar and ask NeuraFlow for help.',
  please_wait:'Please wait a moment before trying again.',
};
function calendarSyncBusy() {
  calendarPanel.querySelectorAll('input,select,button').forEach(el=>{
    el.disabled = busy || (typeof appointmentPending !== 'undefined' && Boolean(appointmentPending)) || (Boolean(calendarPending) && el.id !== 'calendar-repeat');
  });
  document.querySelector('#calendar-pending').hidden = !calendarPending;
}
async function calendarApi(path, body) {
  const response = await fetch('/api/studio/calendar/'+path,{
    method:'POST',credentials:'same-origin',cache:'no-store',redirect:'error',
    headers:{'Content-Type':'application/json','Accept':'application/json'},
    body:JSON.stringify(body),signal:AbortSignal.timeout(15000),
  });
  if(!response.headers.get('content-type')?.includes('application/json'))throw Error('unavailable');
  const data=await response.json();
  if(!response.ok){const error=Error('unavailable');error.code=data?.code;error.status=response.status;throw error;}
  return data;
}
async function calendarLoad(more=false) {
  if(busy || calendarPending || calendarPanel.hidden)return;
  const day=document.querySelector('#calendar-day').value;
  if(!/^\d{4}-\d{2}-\d{2}$/.test(day))return;
  setBusy(true);calendarStatus.textContent='Checking the practice calendar…';
  try {
    const result=await calendarApi('list',{day,after:more&&calendarDay===day?calendarCursor:null});
    if(result.code!=='ok'||result.day!==day||result.timezone!=='Asia/Kolkata'||!Array.isArray(result.items)||result.items.length>50)throw Error('unavailable');
    if(!more || calendarDay!==day)calendarItems.replaceChildren();
    for(const item of result.items){
      if(!['closure','appointment'].includes(item.kind)||!Number.isFinite(Date.parse(item.starts_at))||!Number.isFinite(Date.parse(item.ends_at)))throw Error('unavailable');
      const li=document.createElement('li'),title=document.createElement('strong'),details=document.createElement('p');
      title.textContent=item.kind==='closure'?'Unavailable':(item.service||'Appointment')+' · '+(item.name||'Customer');
      details.textContent=calendarTime.format(new Date(item.starts_at))+' — '+calendarTime.format(new Date(item.ends_at));
      const note=document.createElement('p');note.textContent=item.kind==='closure'?item.reason:'Status: '+item.state;
      li.append(title,details,note);
      if(item.kind==='closure'){
        const button=document.createElement('button');button.type='button';button.className='secondary';button.textContent='Make this time available';
        button.addEventListener('click',()=>{
          if(busy||calendarPending)return;reopenClaim=item.id;document.querySelector('#calendar-reopen').hidden=false;
          document.querySelector('#reopen-period').textContent=details.textContent;document.querySelector('#reopen-reason').value='';
          document.querySelector('#reopen-reason').focus();
        });li.append(button);
      }
      if(item.kind==='appointment' && item.state==='confirmed'){
        const button=document.createElement('button');button.type='button';button.className='secondary';button.textContent='Manage appointment';
        button.addEventListener('click',()=>document.dispatchEvent(new CustomEvent('studio-appointment',{detail:item.id})));li.append(button);
      }
      calendarItems.append(li);
    }
    calendarDay=day;calendarCursor=result.next_cursor;
    document.querySelector('#calendar-more').hidden=!calendarCursor;
    calendarStatus.textContent=calendarItems.children.length?'Saved reservations and unavailable periods are shown below.':'No saved reservations or unavailable periods on this day.';
  }catch(error){calendarItems.replaceChildren();calendarCursor=null;document.querySelector('#calendar-more').hidden=true;
    calendarStatus.textContent=calendarMessages[error.code]||'We cannot load this day right now. Please try again.';
  }finally{setBusy(false);}
}
async function calendarSave() {
  if(busy||!calendarPending)return;
  setBusy(true);actionStatus.textContent='Saving your change…';
  try{
    const result=await calendarApi(calendarPending.path,calendarPending.body);
    const accepted=calendarPending.path==='close'?['closed','existing']:['reopened','already_open','existing'];
    if(!accepted.includes(result.code))throw Error('unavailable');
    if(calendarPending.path==='close' && typeof result.active!=='boolean')throw Error('unavailable');
    actionStatus.textContent=calendarPending.path==='close'
      ? result.active?'That time is now blocked. Existing appointments have not been changed.':'That earlier blocked period has already been reopened. The calendar has been refreshed.'
      : 'That unavailable period is now open again. Normal booking hours still apply.';
    calendarPending=null;reopenClaim=null;document.querySelector('#calendar-reopen').hidden=true;
    setBusy(false);await calendarLoad();
  }catch(error){
    // Only an explicit server rejection is safe to release; lost replies retain
    // the exact operation ID and body. Never convert a retry into a new action.
    if([409,422].includes(error.status)&&['invalid_closure','closure_not_found','time_already_reserved'].includes(error.code))calendarPending=null;
    actionStatus.textContent=calendarMessages[error.code]||'We could not confirm the change. Check the same saved request below.';
  }finally{setBusy(false);}
}
document.querySelector('#calendar-view').addEventListener('submit',event=>{event.preventDefault();calendarLoad();});
document.querySelector('#calendar-more').addEventListener('click',()=>calendarLoad(true));
document.querySelector('#calendar-close').addEventListener('submit',event=>{
  event.preventDefault();if(busy||calendarPending)return;
  const start=document.querySelector('#closure-start').value,end=document.querySelector('#closure-end').value;
  if(!start||!end||Date.parse(end+'+05:30')<=Date.parse(start+'+05:30')){actionStatus.textContent='Choose an end time after the start time.';return;}
  calendarPending={path:'close',body:{operation_id:crypto.randomUUID(),reason:document.querySelector('#closure-reason').value.trim(),starts_at:start+':00+05:30',ends_at:end+':00+05:30'}};
  calendarSave();
});
document.querySelector('#calendar-reopen').addEventListener('submit',event=>{
  event.preventDefault();if(busy||calendarPending||!reopenClaim)return;
  calendarPending={path:'reopen',body:{operation_id:crypto.randomUUID(),claim_id:reopenClaim,reason:document.querySelector('#reopen-reason').value.trim()}};calendarSave();
});
document.querySelector('#reopen-cancel').addEventListener('click',()=>{if(busy||calendarPending)return;reopenClaim=null;document.querySelector('#calendar-reopen').hidden=true;});
document.querySelector('#calendar-repeat').addEventListener('click',calendarSave);
document.addEventListener('studio-calendar-hide',()=>{calendarItems.replaceChildren();calendarCursor=null;calendarStatus.textContent='';});
document.addEventListener('studio-role',event=>{
  if(event.detail==='client'){setTimeout(()=>calendarLoad(),0);return;}
  calendarPending=null;reopenClaim=null;calendarItems.replaceChildren();calendarCursor=null;actionStatus.textContent='';
  document.querySelector('#calendar-close').reset();document.querySelector('#calendar-reopen').reset();
  document.querySelector('#calendar-reopen').hidden=true;calendarSyncBusy();
});
calendarSyncBusy();
