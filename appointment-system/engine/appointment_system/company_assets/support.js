(() => {
 'use strict';const $=id=>document.getElementById(id);
 const journal=window.PracticeStaffActions('company');
 let timeZone=null,csrf=null,current=null,pending=journal.get()[0]||null,busy=false,accessEpoch=0;
 const allowed=new Set(['ok','rescheduled','cancelled','support_saved','refund_verified','resource_reviewed','operation_not_found','operation_conflict']);
 function clearPrivate(){
  accessEpoch++;csrf=null;current=null;timeZone=null;
  for(const id of ['appointments','reviews','summary','activation'])$(id).replaceChildren();
  $('detail').hidden=$('activation').hidden=true;$('change').reset();$('reference').value='';
 }
 const outcomes={cancel:'cancelled',reschedule:'rescheduled',support:'support_saved','verified-refund':'refund_verified','resource-reviewed':'resource_reviewed'};
 function checkedOutcome(value){
  if(!Object.values(outcomes).includes(value.code)||!Number.isSafeInteger(value.revision)||value.revision<1)throw Error('support_unavailable');
  if(value.code==='support_saved'&&(typeof value.active!=='boolean'||!Number.isFinite(Date.parse(value.expires_at))||(value.active&&!/^[0-9]{8}$/.test(value.activation_code))))throw Error('support_unavailable');
  return value;
 }
 async function api(path,body){
  const ticket=accessEpoch;
  const response=await fetch('/api/company/support/'+path,{method:body?'POST':'GET',credentials:'same-origin',redirect:'error',cache:'no-store',
   headers:{'Content-Type':'application/json',...(csrf?{'X-Company-CSRF':csrf}:{})},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(15000)});
  if([401,403].includes(response.status))clearPrivate();
  const value=await response.json();
  if(ticket!==accessEpoch){const error=Error('company_session_required');throw error;}
  if(!response.ok || !allowed.has(value.code)){
   const error=Error(value.code || 'support_unavailable');
   error.definitive=[400,403,404,409,415,422].includes(response.status);throw error;
  }return value;
 }
 function text(tag,value){const element=document.createElement(tag);element.textContent=value;return element;}
 const time=value=>new Date(value).toLocaleString('en-IN',{timeZone:timeZone,dateStyle:'medium',timeStyle:'short'});
 async function load(){
  if(busy)return;
  try{const value=await api('status');csrf=value.csrf_token;const context=await api('time-context',{});if(context.code!=='ok'||typeof context.timezone!=='string')throw Error();new Intl.DateTimeFormat('en-IN',{timeZone:context.timezone});timeZone=context.timezone;document.querySelectorAll('[data-staff-timezone]').forEach(node=>node.textContent=timeZone);
   $('appointments').replaceChildren();$('reviews').replaceChildren();
   for(const row of value.appointments){const item=document.createElement('li'),button=document.createElement('button');
    button.type='button';button.className='secondary';button.textContent=`${time(row.starts_at)} · ${row.name} · ${row.service}`;
    button.addEventListener('click',()=>lookup(row.reference));item.append(button);$('appointments').append(item);}
   for(const row of value.reviews){const item=document.createElement('li');item.append(text('p',`${row.reference} · ${row.reason.replaceAll('_',' ')}`));
    const dispute=row.resource_kind==='dispute';
    if(dispute&&(!row.resource_verified||row.resource_attention||!['won','lost','closed'].includes(row.resource_status))){
     item.append(text('p','The dispute remains open until its current outcome is verified.'));$('reviews').append(item);continue;}
    const button=text('button',dispute?'Finish dispute review':'Close after verified full refund');button.type='button';button.className='secondary';
    button.addEventListener('click',()=>{if(busy||pending)return;const note=window.prompt(dispute?'Record the checked dispute outcome. This does not change money.':'Record how the full refund was verified. This does not issue a refund.');
     if(!note || note.trim().length<2)return;submit(dispute?'resource-reviewed':'verified-refund',{operation_id:crypto.randomUUID(),case_id:row.case_id,expected_revision:row.revision,reason:note.trim()});});
    item.append(button);$('reviews').append(item);}
   $('status').textContent=`${value.appointments.length} upcoming appointment(s), ${value.reviews.length} payment review(s). Use the reference to find an older appointment.`;
  }catch(error){$('status').textContent=error.message==='company_session_required'?'Sign in with company support permission to continue.':'We could not check existing appointments. Please retry.';}
 }
 async function lookup(reference){
  if(busy||pending)return;
  try{current=await api('lookup',{reference});$('reference').value=reference;$('summary').replaceChildren();
   for(const [name,value] of [['Person',current.name],['Consultation',current.service],['Time',time(current.starts_at)+' · '+timeZone],['Status',current.state],['Email',current.email],['Mobile',current.phone]]){
    const cell=document.createElement('div');cell.append(text('dt',name),text('dd',value));$('summary').append(cell);}
   $('detail').hidden=false;$('detail-title').focus();$('activation').hidden=true;fields();
  }catch{current=null;$('detail').hidden=true;$('status').textContent='We could not find an accepted appointment for that reference.';}
 }
 function fields(){
  const action=$('action').value,support=['receipt_recovery','contact_correction'].includes(action);
  $('time-field').hidden=action!=='reschedule';$('starts-at').required=action==='reschedule';
  for(const id of ['email','phone']){$(id+'-field').hidden=action!=='contact_correction';$(id).required=action==='contact_correction' && (id!=='email' || current?.contact_email_required!==false);}
  $('payment-field').hidden=$('verification-field').hidden=!support;$('payment').required=$('verified').required=support;
  $('action-note').textContent=action==='cancel'?'Cancellation releases the appointment time. It does not issue a refund.':support?'Use the original saved mobile and payment details. If that mobile is unavailable, keep the case for manual review.':'The original appointment remains if the new time is unavailable.';
 }
 async function submit(path,body){
  if(busy||journal.get().some(row=>row.operation_id!==body.operation_id))return;
  pending={path,body,operation_id:body.operation_id};busy=true;$('submit-change').disabled=true;$('retry').hidden=true;
  $('status').textContent='Checking and saving this action…';
  try{await journal.remember(body.operation_id);const value=checkedOutcome(await api(path,body));
   const revision=body.expected_revision+(path==='support'&&body.action==='receipt_recovery'?0:1);
   if(value.code!==outcomes[path]||value.revision!==revision||(value.operation_id!==undefined&&value.operation_id!==body.operation_id)||(path==='reschedule'&&!Number.isFinite(Date.parse(value.starts_at))))throw Error('support_unavailable');
   await journal.forget(body.operation_id);pending=null;$('status').textContent=value.code.replaceAll('_',' ')+'.';
   if(value.active&&value.activation_code){$('activation').hidden=false;$('activation').textContent=`Give this code only during the verified call: ${value.activation_code}. The customer uses the booking access page. No receipt secret is exposed here.`;}
   else $('activation').hidden=true;
   current=null;$('detail').hidden=true;
   $('status').textContent+=' Find the booking again before another change.';
  }catch(error){
   if(error.definitive){try{await journal.forget(body.operation_id);}catch{$('status').textContent=journal.error;$('retry').hidden=false;return;}pending=null;current=null;$('detail').hidden=true;
    const messages={revision_changed:'This appointment has changed. Find it again before making another change.',
     time_unavailable:'That time is unavailable. Find the appointment again and choose another time.',
     resource_not_verified:'The current dispute outcome has not been verified. The review stays open.',
     refund_not_verified:'The saved payment evidence does not yet show a full refund. No review was closed.',
     request_conflict:'This action reference belongs to another change. Check the saved appointment before continuing.'};
    $('status').textContent=messages[error.message] || 'This change was not accepted. Check the appointment and try again.';
   }else{$('status').textContent=journal.error||(error.message==='company_session_required'?'Renew company access, then check this same action.':'The outcome is not confirmed. Check this same action before submitting another.');$('retry').hidden=false;}
  }
  finally{busy=false;$('submit-change').disabled=!!pending;}
 }
 async function checkSaved(){
  if(busy)return;busy=true;
  try{const saved=journal.get();if(journal.error)throw Error(journal.error);for(const item of saved){const value=await api('actions/'+item.operation_id);
    if(value.operation_id!==item.operation_id||value.code==='operation_conflict')throw Error('operation_conflict');
    if(value.code==='operation_not_found'){if(Date.now()-item.created_at<300000)throw Error('still_checking');await journal.forget(item.operation_id);continue;}
    checkedOutcome(value);await journal.forget(item.operation_id);current=null;$('detail').hidden=true;
    if(value.active&&value.activation_code){$('activation').hidden=false;$('activation').textContent='Give this short code only to the verified customer: '+value.activation_code;}
   }pending=journal.get()[0]||null;$('status').textContent='Earlier results checked. Find the booking again before another change.';
  }catch{$('status').textContent='The earlier result still needs checking. Renew company access if needed, then retry.';}
  finally{busy=false;$('retry').hidden=!journal.get().length;$('submit-change').disabled=!!journal.get().length;}
 }
 $('lookup').addEventListener('submit',e=>{e.preventDefault();lookup($('reference').value.trim());});
 $('change').addEventListener('submit',async e=>{e.preventDefault();if(!current||pending)return;
  const action=$('action').value,base={operation_id:crypto.randomUUID(),expected_revision:current.revision,reason:$('reason').value.trim()};
  if(action==='cancel')submit('cancel',{...base,claim_id:current.claim_id});
  else if(action==='reschedule'){
   if(busy||!timeZone)return;busy=true;const target=current,local=$('starts-at').value;
   try{const resolved=await api('resolve-time',{local,timezone:timeZone});
    if(resolved.code!=='ok'||resolved.timezone!==timeZone||resolved.local!==local||!Number.isFinite(Date.parse(resolved.instant)))throw Error();
    busy=false;await submit('reschedule',{...base,claim_id:target.claim_id,starts_at:resolved.instant});
   }catch{$('status').textContent='We could not check that local time. Refresh the calendar and try again.';}
   finally{busy=false;}
  }
  else submit('support',{...base,reference:current.reference,action,verified_payment_id:$('payment').value.trim(),verification_confirmed:$('verified').checked,
    ...(action==='contact_correction'?{email:$('email').value.trim()||null,phone:$('phone').value.trim()}:{} )});
 });
 $('action').addEventListener('change',fields);$('retry').textContent='Check saved action';$('retry').addEventListener('click',checkSaved);
 $('refresh').addEventListener('click',load);if(pending){$('retry').hidden=false;$('submit-change').disabled=true;}load();
})();
