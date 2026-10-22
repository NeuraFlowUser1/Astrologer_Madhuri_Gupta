/** One display controller for React and ordinary pages; it never reads Neon. */
const OFF=Object.freeze({enabled:false,verified:false,activation_epoch:null,checking:false,
 retained_on_epoch:null,foreground_revision:0});
const disabled=()=>OFF;
const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
export function checkedDisplay(value){
 if(!value || typeof value!=='object' || Array.isArray(value)
  || Object.keys(value).sort().join(',')!=='activation_epoch,enabled' || typeof value.enabled!=='boolean'
  || typeof value.activation_epoch!=='string' || !uuid.test(value.activation_epoch)
  || value.activation_epoch==='00000000-0000-0000-0000-000000000000')throw Error('display_state_invalid');
 return Object.freeze({...value,verified:true});
}
/** A pending check keeps a visible form, but cannot admit a new operation. */
export const displayAllowed=value=>value?.enabled===true && (value.verified===true || value.checking===true);
export const admissionAllowed=value=>value?.enabled===true && value.verified===true && value.checking!==true;
export const retainView=value=>typeof value?.retained_on_epoch==='string';
/** Build snapshots describe public copy only; they never grant admission. */
export function publicDisplaySnapshot(enabled){
 if(typeof enabled!=='boolean')throw TypeError('Invalid public display mode.');
 return Object.freeze({...OFF,enabled,checking:enabled});
}
export function createStateController({fetcher=globalThis.fetch,clock=Date.now,serverSnapshot=disabled,initialDisplay=false,
 setTimer=(fn,delay)=>globalThis.setTimeout(fn,delay),clearTimer=id=>globalThis.clearTimeout(id)}={}){
 if(typeof serverSnapshot!=='function')throw TypeError('A server snapshot reader is required.');
 if(typeof initialDisplay!=='boolean')throw TypeError('Invalid initial public display choice.');
 // Retain only the reviewed display boolean. Never copy verification, epochs or credentials from HTML.
 let state=initialDisplay?publicDisplaySnapshot(serverSnapshot()?.enabled):disabled(),sequence=0,pending=null,controller=null,lastAttempt=-Infinity,lastForeground=-Infinity,stop=null;
 let profile='active',schedule=null,isVisible=()=>false;
 const listeners=new Set();
 const emit=value=>{state=Object.freeze(value);for(const listener of [...listeners])listener();};
 function cancel(){++sequence;controller?.abort();pending=null;controller=null;}
 function invalidate(){cancel();lastForeground=-Infinity;emit(disabled());}
 function pause(){cancel();lastForeground=-Infinity;emit({...state,enabled:false,verified:false,checking:false});}
 function refresh({force=false,foreground=false}={}){
  if(foreground){
   if(clock()-lastForeground<100)return pending||Promise.resolve(state);
   lastForeground=clock();emit({...state,verified:false,checking:true,foreground_revision:state.foreground_revision+1});
  }
  if(pending)return pending;
  if(!force && clock()-lastAttempt<5000)return Promise.resolve(state);
  lastAttempt=clock();const turn=++sequence,abort=new AbortController();controller=abort;
  const work=async()=>{
   let reader,timer;
   try{
    const value=await Promise.race([(async()=>{
     const response=await fetcher('/api/service-state',{credentials:'same-origin',cache:'no-store',redirect:'error',signal:abort.signal});
     if(response.status!==200 || response.headers.get('content-type')?.split(';')[0].trim()!=='application/json' || !response.body)
      throw Error('display_state_unavailable');
     reader=response.body.getReader();const decoder=new TextDecoder('utf-8',{fatal:true});let size=0,text='';
     while(true){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;
      if(size>1024)throw Error('display_state_invalid');text+=decoder.decode(value,{stream:true});}
     return checkedDisplay(JSON.parse(text+decoder.decode()));
    })(),new Promise((_,reject)=>{
     const rejectUnavailable=()=>reject(Error('display_state_unavailable'));
     abort.signal.addEventListener('abort',rejectUnavailable,{once:true});
     if(abort.signal.aborted)rejectUnavailable();timer=setTimer(rejectUnavailable,2000);
    })]);
    if(turn===sequence)emit({...value,checking:false,retained_on_epoch:value.enabled?value.activation_epoch:null,
     foreground_revision:state.foreground_revision});
   }catch{if(turn===sequence)emit({...state,enabled:false,verified:false,checking:false});}
   finally{
    clearTimer(timer);abort.abort();if(reader)void reader.cancel().catch(()=>{});
    if(turn===sequence){pending=null;controller=null;schedule?.();}
   }
   return state;
  };
  // Assign before notifying: a listener asking for freshness shares this read.
  pending=Promise.resolve().then(work);emit({...state,verified:false,checking:true});schedule?.();return pending;
 }
 function setProfile(next){
  if(next!=='public' && next!=='active')throw TypeError('Invalid display profile.');
  if(next===profile)return;
  profile=next;
  if(stop && isVisible() && next==='active')void refresh({force:true});
  schedule?.();
 }
 function start(windowObject=window,documentObject=document,{profile:initial='active',refreshOnStart=true}={}){
  if(stop)return stop;
  if(initial!=='public' && initial!=='active')throw TypeError('Invalid display profile.');
  profile=initial;let timer=null,pageHidden=false;
  isVisible=()=>!pageHidden && documentObject.visibilityState!=='hidden';
  const clear=()=>{if(timer!==null)clearTimer(timer);timer=null;};
  schedule=()=>{
   clear();if(!isVisible())return;
   const period=profile==='public'?60000:5000;
   const elapsed=Number.isFinite(lastAttempt)?Math.max(0,clock()-lastAttempt):0;
   timer=setTimer(()=>{timer=null;if(isVisible())void refresh({force:true});},Math.max(1,period-elapsed));
  };
  const activity=()=>{if(isVisible())void refresh({force:true,foreground:true});schedule?.();};
  const visibilityChanged=()=>{if(documentObject.visibilityState!=='hidden')pageHidden=false;activity();};
  const shown=event=>{
   const resumed=pageHidden;pageHidden=false;
   // The initial pageshow belongs to this same bootstrap, not a new visit.
   // A restored page, a hidden lifetime or a not-yet-started one still refreshes.
   if(event?.persisted===false && !resumed && Number.isFinite(lastAttempt)){schedule?.();return;}
   activity();
  };
  const hidden=()=>{pageHidden=true;clear();pause();};
  windowObject.addEventListener('focus',activity);windowObject.addEventListener('pageshow',shown);
  windowObject.addEventListener('pagehide',hidden);documentObject.addEventListener('visibilitychange',visibilityChanged);
  const dispose=()=>{
   if(stop!==dispose)return;
   clear();schedule=null;isVisible=()=>false;
   windowObject.removeEventListener('focus',activity);windowObject.removeEventListener('pageshow',shown);
   windowObject.removeEventListener('pagehide',hidden);documentObject.removeEventListener('visibilitychange',visibilityChanged);
   stop=null;invalidate();
  };
  stop=dispose;
  if(isVisible() && refreshOnStart)void refresh({force:true});
  schedule();return stop;
 }
 return Object.freeze({getSnapshot:()=>state,getServerSnapshot:serverSnapshot,
  subscribe:listener=>{listeners.add(listener);return()=>listeners.delete(listener);},refresh,start,setProfile,invalidate});
}
export const productState=createStateController();
