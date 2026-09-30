'use strict';
// Private data and uncertain operation bodies stay in memory only.
(()=>{
 const $=id=>document.getElementById(id),panel=$('inbox-panel');
 const keyPattern=/^(enquiry|payment|delivery|enquiry-delivery):[a-f0-9-]{36}$/;
 let role=null,view='issues',cursor=null,selected=null,pending=null,loading=false,epoch=0,controller=null,pendingAction=null;
 const labels={enquiry:'Verified enquiry',payment:'Payment needs checking',meeting:'Meeting needs attention',booking_email:'Booking email needs attention',enquiry_email:'Enquiry email needs attention',client_records:'Practice record copy needs attention',agency_records:'NeuraFlow record copy needs attention'};
 const advice={payment:'Check the saved payment evidence and Razorpay before taking action. Do not ask the customer to pay again blindly.',meeting:'Check the practice Google connection and meeting delivery. A pending meeting does not cancel the booking.',booking_email:'Check delivery and the saved address. Do not start a fresh send after an uncertain result.',enquiry_email:'The enquiry remains saved even if its email has a problem.',client_records:'Check the practice Google connection and its own spreadsheet. Do not overwrite a conflicting row.',agency_records:'Check NeuraFlow’s Google connection and its own spreadsheet. Do not overwrite a conflicting row.'};
 const time=new Intl.DateTimeFormat('en-IN',{timeZone:'Asia/Kolkata',dateStyle:'medium',timeStyle:'short'});
 const errors={access_unavailable:'Your access could not be confirmed. Sign in again.',item_unavailable:'This item is no longer in this view. Refresh the inbox.',revision_changed:'Another review was saved first. Open the latest details before adding your note.',request_conflict:'This request differs from an earlier saved note. Keep it for support; do not create a duplicate.',refund_not_verified:'A full refund has not been verified for this exact payment, or its appointment still needs attention. Nothing has been marked resolved.',retry_unavailable:'This work cannot safely be retried here. Check its saved evidence and contact support.',retry_wait:'A retry was requested recently. Wait one minute before requesting another.',please_wait:'Please wait a moment before checking again.'};
 function controls(){panel.querySelectorAll('button,textarea').forEach(el=>el.disabled=busy||loading||Boolean(pending));$('inbox-retry-review').disabled=busy||loading;$('inbox-retry-review').hidden=!pending;}
 function clear(){++epoch;controller?.abort();loading=false;role=null;selected=null;pending=null;pendingAction=null;cursor=null;panel.hidden=true;$('inbox-items').replaceChildren();$('inbox-content').replaceChildren();$('inbox-reviews').replaceChildren();$('review-note').value='';$('inbox-status').textContent='';$('inbox-review-status').textContent='';$('inbox-detail').hidden=true;controls();}
 function node(tag,text){const el=document.createElement(tag);el.textContent=text;return el;}
 async function request(path,body){
  const ownController=new AbortController();controller=ownController;const timer=setTimeout(()=>ownController.abort(),15000);
  try{
   const response=await fetch('/api/studio/inbox/'+path,{method:'POST',credentials:'same-origin',cache:'no-store',redirect:'error',headers:{'Content-Type':'application/json',Accept:'application/json'},body:JSON.stringify(body),signal:ownController.signal});
   if(!response.headers.get('content-type')?.includes('application/json')||!response.body)throw Error('unavailable');
   const reader=response.body.getReader(),decoder=new TextDecoder();let size=0,text='';
   try{while(true){const part=await reader.read();if(part.done)break;size+=part.value.length;if(size>65536)throw Error('unavailable');text+=decoder.decode(part.value,{stream:true});}text+=decoder.decode();}finally{await reader.cancel().catch(()=>{});}
   const data=JSON.parse(text);if(!response.ok){const e=Error('unavailable');e.code=data.code;e.status=response.status;throw e;}return data;
  }finally{clearTimeout(timer);if(controller===ownController)controller=null;}
 }
 function itemValid(item){return item&&keyPattern.test(item.item_key)&&Object.hasOwn(labels,item.category)&&Number.isInteger(item.review_revision)&&item.review_revision>=0&&typeof item.state==='string'&&Number.isFinite(Date.parse(item.created_at));}
 function fail(error,target){if(error.status===401||error.status===403){clear();$('status').textContent=errors.access_unavailable;$('retry').hidden=false;return;}target.textContent=errors[error.code]||'We could not confirm the response. Please check again.';}
 async function list(more=false){
  if(loading||pending||!role)return;loading=true;controls();const ticket=epoch;
  $('inbox-status').textContent='Checking saved work…';
  try{
   const data=await request('list',{view,after:more?cursor:null});if(ticket!==epoch)return;
   if(data.code!=='ok'||data.view!==view||!Array.isArray(data.items)||data.items.length>50||data.items.some(i=>!itemValid(i))||(data.next_cursor!==null&&!keyPattern.test(data.next_cursor)))throw Error('unavailable');
   if(!more){$('inbox-items').replaceChildren();$('inbox-detail').hidden=true;selected=null;}
   for(const item of data.items){const li=node('li','');li.append(node('strong',labels[item.category]),node('p',time.format(new Date(item.created_at))+' · India time'));
    if(item.subject)li.append(node('p',item.subject));if(item.reference)li.append(node('p','Reference: '+item.reference));
    li.append(node('p',item.category==='enquiry'?'Saved after email verification.':advice[item.category]));
    if(item.review_revision)li.append(node('p','Staff review recorded; underlying status is unchanged.'));
    const button=node('button','Open details');button.type='button';button.className='secondary';button.addEventListener('click',()=>detail(item.item_key));li.append(button);$('inbox-items').append(li);}
   cursor=data.next_cursor;$('inbox-more').hidden=!cursor;$('inbox-status').textContent=$('inbox-items').children.length?'Saved items shown below. Refresh to check for changes.':view==='enquiries'?'No verified enquiries yet.':'No recorded problems in this view. This is not a complete live-service health check.';
  }catch(e){if(ticket!==epoch)return;$('inbox-items').replaceChildren();cursor=null;$('inbox-more').hidden=true;fail(e,$('inbox-status'));}
  finally{if(ticket===epoch){loading=false;controls();}}
 }
 async function detail(key){
  if(loading||pending||!role)return;loading=true;controls();const ticket=epoch;$('inbox-detail').hidden=true;
  try{
   const data=await request('detail',{item_key:key});if(ticket!==epoch)return;
   const item=data.item;if(data.code!=='ok'||!itemValid(item)||item.item_key!==key||!Array.isArray(item.reviews)||item.reviews.length>20)throw Error('unavailable');
   if(item.category==='enquiry'&&(role!=='client'||!item.enquiry||!['name','email','phone','subject','message'].every(k=>typeof item.enquiry[k]==='string')))throw Error('unavailable');
   selected=item;$('inbox-action-refund').hidden=item.category!=='payment';$('inbox-action-retry').hidden=item.category==='enquiry';$('inbox-action-retry').textContent=item.category==='payment'?'Check payment again':'Retry saved work';$('inbox-content').replaceChildren();$('inbox-reviews').replaceChildren();$('inbox-detail-title').textContent=labels[item.category];
   if(role==='client'&&/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(item.reference||'')){const open=node('button','Open booking for support');open.type='button';open.className='secondary';open.addEventListener('click',()=>document.dispatchEvent(new CustomEvent('studio-booking-reference',{detail:item.reference})));$('inbox-content').append(open);}
   if(item.enquiry){for(const [label,key] of [['Name','name'],['Email','email'],['Phone','phone'],['Subject','subject'],['Question','message']])$('inbox-content').append(node('p',label+': '+(item.enquiry[key]||'Not supplied')));}else $('inbox-content').append(node('p',advice[item.category]));
   for(const review of item.reviews){if(typeof review.note!=='string'||!Number.isFinite(Date.parse(review.created_at)))throw Error('unavailable');$('inbox-reviews').append(node('li',time.format(new Date(review.created_at))+' · '+(review.role==='client'?'Practice':'NeuraFlow')+' — '+review.note));}
   if(!item.reviews.length)$('inbox-reviews').append(node('li','No staff review notes yet.'));
   $('inbox-review-status').textContent='';$('review-note').value='';$('inbox-detail').hidden=false;$('inbox-detail-title').focus();
  }catch(e){if(ticket!==epoch)return;selected=null;fail(e,$('inbox-status'));}
  finally{if(ticket===epoch){loading=false;controls();}}
 }
 async function save(){
  if(loading||!pending||!role)return;loading=true;controls();const ticket=epoch;
  $('inbox-review-status').textContent='Saving the same review note…';
  try{const data=await request(pendingAction,pending);if(ticket!==epoch)return;if(data.code!==(pendingAction==='retry'?'retry_queued':pendingAction==='refund-verified'?'refund_verified':'review_saved')||data.revision!==pending.expected_revision+1)throw Error('unavailable');
   const key=pending.item_key,retried=pendingAction!=='review',refund=pendingAction==='refund-verified';pending=null;pendingAction=null;loading=false;controls();if(retried){await list();if(ticket===epoch)$('inbox-status').textContent=refund?'Review closed using a recorded full-refund confirmation. This action did not send money.':'Another attempt is queued. This does not confirm delivery or a refund.';}else{await detail(key);if(ticket===epoch)$('inbox-review-status').textContent='Review note saved. Delivery and payment status have not been changed.';}
  }catch(e){if(ticket!==epoch)return;if(e.status===422||['revision_changed','item_unavailable','retry_unavailable','retry_wait','refund_not_verified'].includes(e.code))pending=null;fail(e,$('inbox-review-status'));}
  finally{if(ticket===epoch){loading=false;controls();}}
 }
 $('inbox-review').addEventListener('submit',e=>{e.preventDefault();if(loading||pending||!selected)return;const note=$('review-note').value.trim();if(note.length<2||[...note].some(c=>c.charCodeAt(0)<32||c.charCodeAt(0)===127)){$('inbox-review-status').textContent='Write a short single-line note.';return;}pendingAction='review';pending={operation_id:crypto.randomUUID(),item_key:selected.item_key,expected_revision:selected.review_revision,note};save();});
 $('inbox-action-retry').addEventListener('click',()=>{if(loading||pending||busy||!selected||selected.category==='enquiry')return;const note=$('review-note').value.trim();if(note.length<2||[...note].some(c=>c.charCodeAt(0)<32||c.charCodeAt(0)===127)){$('inbox-review-status').textContent='First write what you checked or corrected.';return;}pendingAction='retry';pending={operation_id:crypto.randomUUID(),item_key:selected.item_key,expected_revision:selected.review_revision,note};save();});
 $('inbox-action-refund').addEventListener('click',()=>{if(loading||pending||busy||!selected||role!=='client'||selected.category!=='payment')return;const note=$('review-note').value.trim();if(note.length<2||[...note].some(c=>c.charCodeAt(0)<32||c.charCodeAt(0)===127)){$('inbox-review-status').textContent='First write what you checked.';return;}pendingAction='refund-verified';pending={operation_id:crypto.randomUUID(),item_key:selected.item_key,expected_revision:selected.review_revision,note};save();});
 for(const [id,value] of [['inbox-enquiries','enquiries'],['inbox-issues','issues']])$(id).addEventListener('click',()=>{if(pending||loading)return;view=value;$('inbox-enquiries').setAttribute('aria-pressed',String(view==='enquiries'));$('inbox-issues').setAttribute('aria-pressed',String(view==='issues'));list();});
 $('inbox-more').addEventListener('click',()=>list(true));$('inbox-refresh').addEventListener('click',()=>list());$('inbox-retry-review').addEventListener('click',save);
 document.addEventListener('studio-inbox-hide',clear);
 document.addEventListener('studio-busy',controls);
 document.addEventListener('studio-role',event=>{clear();if(!['client','agency'].includes(event.detail))return;role=event.detail;panel.hidden=false;view=role==='client'?'enquiries':'issues';$('inbox-enquiries').hidden=role!=='client';$('inbox-purpose').textContent=role==='client'?'Read verified enquiries and review problems with saved work.':'Review problems with NeuraFlow’s own record copies. Customer enquiries, appointments and payments are not available to this role.';$('inbox-enquiries').setAttribute('aria-pressed',String(view==='enquiries'));$('inbox-issues').setAttribute('aria-pressed',String(view==='issues'));list();});
})();
