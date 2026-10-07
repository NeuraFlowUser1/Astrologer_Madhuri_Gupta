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
export function createStateController({fetcher=globalThis.fetch,clock=Date.now}={}){
 let state=disabled(),sequence=0,pending=null,controller=null,lastAttempt=-Infinity,lastForeground=-Infinity,stop=null;
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
     if(abort.signal.aborted)rejectUnavailable();timer=setTimeout(rejectUnavailable,2000);
    })]);
    if(turn===sequence)emit({...value,checking:false,retained_on_epoch:value.enabled?value.activation_epoch:null,
     foreground_revision:state.foreground_revision});
   }catch{if(turn===sequence)emit({...state,enabled:false,verified:false,checking:false});}
   finally{
    clearTimeout(timer);abort.abort();if(reader)void reader.cancel().catch(()=>{});
    if(turn===sequence){pending=null;controller=null;}
   }
   return state;
  };
  // Assign before notifying: a listener asking for freshness shares this read.
  pending=Promise.resolve().then(work);emit({...state,verified:false,checking:true});return pending;
 }
 function start(windowObject=window,documentObject=document){
  if(stop)return stop;
  const visible=()=>documentObject.visibilityState!=='hidden';
  const activity=()=>{if(visible())void refresh({force:true,foreground:true});};
  const timer=setInterval(()=>{if(visible())void refresh({force:true});},5000);
  windowObject.addEventListener('focus',activity);windowObject.addEventListener('pageshow',activity);
  windowObject.addEventListener('pagehide',pause);documentObject.addEventListener('visibilitychange',activity);
  stop=()=>{clearInterval(timer);windowObject.removeEventListener('focus',activity);windowObject.removeEventListener('pageshow',activity);
   windowObject.removeEventListener('pagehide',pause);documentObject.removeEventListener('visibilitychange',activity);stop=null;invalidate();};
  if(visible())void refresh({force:true});return stop;
 }
 return Object.freeze({getSnapshot:()=>state,getServerSnapshot:disabled,
  subscribe:listener=>{listeners.add(listener);return()=>listeners.delete(listener);},refresh,start,invalidate});
}
export const productState=createStateController();
