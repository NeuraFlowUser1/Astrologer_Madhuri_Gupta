'use strict';
const element=id=>document.getElementById(id);
let busy=false,view='enquiries',after=null,selected=null;
const journal=window.PracticeStaffActions('enquiry');
function waiting(value){busy=value;document.querySelectorAll('button').forEach(button=>button.disabled=value);const pending=journal.get().length>0;element('check-saved').hidden=!pending;for(const id of ['save','retry'])element(id).disabled=value||pending;}
async function api(path,body){
 const response=await fetch('/api/enquiry-studio/'+path,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',
  redirect:'error',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(15000)});
 if(response.status===401&&path==='status')return{signed_in:false};
 if(response.status===401||response.status===403){const error=Error('Access unavailable');error.status=response.status;throw error;}
 const data=await response.json();if(!response.ok){const error=Error('Request unavailable');error.code=data.code;error.status=response.status;throw error;}return data;
}
function clearPrivate(){selected=null;after=null;element('workspace').hidden=true;element('logout').hidden=true;element('signin').hidden=false;element('account').textContent='';element('items').replaceChildren();element('detail').hidden=true;element('detail-body').replaceChildren();element('detail-title').textContent='';element('note').value='';}
async function action(callback){if(busy)return;waiting(true);try{await callback();}catch(error){if(error.status===401||error.status===403){clearPrivate();element('status').textContent='Your access could not be confirmed. Sign in again.';}else element('status').textContent=journal.error||'We could not complete that request. Refresh to check the saved result before trying again.';}finally{waiting(false);}}
async function load(){
 const status=await api('status');element('signin').hidden=status.signed_in===true;element('logout').hidden=status.signed_in!==true;
 element('workspace').hidden=status.signed_in!==true;element('account').textContent=status.signed_in===true?status.email:'';
 if(status.signed_in===true){element('status').textContent='You are signed in.';await list(false);}else{clearPrivate();element('status').textContent='Sign in to read and handle your enquiries.';}
}
async function list(append){
 const result=await api('inbox/list',{view,after:append?after:null});if(result.code!=='ok'||!Array.isArray(result.items))throw Error();
 if(!append){element('items').replaceChildren();element('detail').hidden=true;selected=null;}
 for(const item of result.items){
  if(!/^(enquiry|enquiry-delivery):[a-f0-9-]{36}$/.test(item.item_key))throw Error();
  const row=document.createElement('article'),title=document.createElement('h2'),text=document.createElement('p'),button=document.createElement('button');
  title.textContent=item.title||item.kind||'Message';text.textContent=[item.summary,item.state,item.received_at||item.created_at].filter(Boolean).join(' · ');
  button.textContent='Open details';button.addEventListener('click',()=>action(()=>open(item.item_key)));row.append(title,text,button);element('items').append(row);
 }
 after=result.next_cursor||null;element('more').hidden=!after;
 if(!append&&result.items.length===0)element('status').textContent=view==='enquiries'?'There are no verified messages yet.':'No enquiry updates need attention.';
}
async function open(key){
 selected=null;element('detail').hidden=true;element('detail-body').replaceChildren();
 const result=await api('inbox/detail',{item_key:key});if(result.code!=='ok'||!result.item||result.item.item_key!==key||!Number.isSafeInteger(result.item.review_revision)||result.item.review_revision<0)throw Error();selected=result.item;
 element('detail-title').textContent=selected.title||'Message details';element('detail-body').replaceChildren();
 const values=selected.enquiry||selected;const list=document.createElement('dl');
 const labels={full_name:'Name',name:'Name',email:'Email',phone:'Phone',service_interest:'Interested in',subject:'Subject',message:'Message',source:'Sent from',summary:'Details',destination:'Destination',state:'Update status',created_at:'Received'};
 for(const [name,label] of Object.entries(labels)){
  const value=values[name];if(value===undefined||value===null||value==='')continue;
  const term=document.createElement('dt'),definition=document.createElement('dd');term.textContent=label;
  definition.textContent=typeof value==='object'?JSON.stringify(value):String(value);list.append(term,definition);
 }
 element('detail-body').append(list);element('note').value='';element('retry').hidden=!key.startsWith('enquiry-delivery:');element('detail').hidden=false;
}
async function checkSaved(){
 const results=await journal.check(body=>api('inbox/action-result',body),['review_saved','retry_queued']);
 if(results===null)return;selected=null;await list(false);element('status').textContent='Earlier actions checked. Open the latest details before making another change.';
}
async function save(retry){
 if(!selected||journal.get().length)return;
 const note=element('note').value.trim();if(note.length<2){element('status').textContent='Please write a short note first.';return;}
 const operation=crypto.randomUUID();await journal.remember(operation);
 try {
  const result=await api('inbox/'+(retry?'retry':'review'),{item_key:selected.item_key,expected_revision:selected.review_revision,operation_id:operation,note});
  if(result.code!==(retry?'retry_queued':'review_saved')||result.revision!==selected.review_revision+1)throw Error();
  await journal.forget(operation);element('status').textContent=retry?'The saved update has been queued. This does not mean it has been delivered yet.':'Your note has been saved.';await list(false);
 }catch(error){
  if(error.status===422||['revision_changed','item_unavailable','retry_unavailable','retry_wait'].includes(error.code))await journal.forget(operation);
  throw error;
 }
}
element('signin').addEventListener('click',()=>action(async()=>{
 const result=await api('sign-in/start',{role:'client'});const url=new URL(result.authorization_url);
 if(url.origin!=='https://accounts.google.com'||url.pathname!=='/o/oauth2/v2/auth')throw Error();location.assign(url.href);
}));
element('logout').addEventListener('click',()=>action(async()=>{await api('logout',{});await load();}));
element('messages').addEventListener('click',()=>action(async()=>{view='enquiries';await list(false);}));
element('attention').addEventListener('click',()=>action(async()=>{view='issues';await list(false);}));
element('refresh').addEventListener('click',()=>action(()=>load()));element('more').addEventListener('click',()=>action(()=>list(true)));
element('check-saved').addEventListener('click',()=>action(checkSaved));
element('save').addEventListener('click',()=>action(()=>save(false)));element('retry').addEventListener('click',()=>action(()=>save(true)));
element('close').addEventListener('click',()=>{element('detail').hidden=true;selected=null;});
action(()=>load());
