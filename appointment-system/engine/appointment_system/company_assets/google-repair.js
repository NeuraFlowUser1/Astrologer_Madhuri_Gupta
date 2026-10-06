(() => {
 'use strict'; const $=id=>document.getElementById(id); let owner=null,csrf=null,pending=null,busy=false;
 const say=value=>{$('message').textContent=value;};
 async function call(path,body) {
  const response=await fetch(path,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',redirect:'error',
   headers:{'Content-Type':'application/json',...(csrf?{'X-Company-CSRF':csrf}:{})},
   ...(body===undefined?{}:{body:JSON.stringify(body)}),signal:AbortSignal.timeout(15000)});
  if(response.status===401||response.status===403){
   owner=null;csrf=null;pending=null;
   $('owner').hidden=$('company').hidden=$('link-label').hidden=$('copy').hidden=true;
   $('owner-link').value='';$('issue').reset();
  }
  if(!response.ok)throw new Error('This approval could not be confirmed. Check your company sign-in or ask support for a new owner link.');
  return response.json();
 }
 const fragment=location.hash;history.replaceState(null,'',location.pathname);
 const match=/^#link=([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})\.([a-f0-9]{64})$/.exec(fragment);
 if(match){owner={operation_id:match[1],secret:match[2]};$('owner').hidden=false;say('Approve this permission with the named Google account. The link works once and expires after ten minutes.');}
 else if(fragment==='#approved=pending'){say('Your approval was received. Company support must finish saving the connection. You can close this page.');}
 else if(fragment.startsWith('#approved=')){say('The approval was not saved. Ask company support for a new link.');}
 else {
  $('company-return').hidden=false;
  call('/api/company/control/status').then(value=>{csrf=value.csrf_token;$('company').hidden=false;say('Create an owner link only for unfinished work on an existing paid appointment.');}).catch(error=>say(error.message));
 }
 $('approve').addEventListener('click',async()=>{
  if(busy||!owner)return;busy=true;$('approve').disabled=true;
  try{const value=await call('/api/company/resources/owner-start',owner);const target=new URL(value.authorization_url);
   if(target.origin!=='https://accounts.google.com'||target.pathname!=='/o/oauth2/v2/auth')throw new Error('The Google approval address could not be confirmed.');
   owner=null;location.assign(target.href);
  }catch(error){say(error.message);busy=false;$('approve').disabled=false;}
 });
 $('issue').addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;busy=true;
  if(!pending)pending={operation_id:crypto.randomUUID(),reference:$('reference').value.trim(),resource:$('resource').value,reason:$('reason').value.trim()};
  try{const result=await call('/api/company/resources/owner-link',pending);const target=new URL(result.owner_link);
   if(target.origin!==location.origin||target.pathname!=='/company/google-repair')throw new Error('The owner link could not be confirmed.');
   $('owner-link').value=target.href;$('link-label').hidden=$('copy').hidden=false;pending=null;
   say('Send this link privately to the named account owner. It expires after ten minutes.');
  }catch(error){say(error.message);}finally{busy=false;}
 });
 $('copy').addEventListener('click',()=>navigator.clipboard.writeText($('owner-link').value).then(()=>say('The private link is copied.')).catch(()=>say('Select and copy the displayed link.')));
})();
