/** One display controller for React and ordinary pages; it never reads Neon. */
const OFF=Object.freeze({enabled:false,verified:false,activation_epoch:null});
const disabled=()=>OFF;
const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
export function checkedDisplay(value){
 if(!value || typeof value!=='object' || Array.isArray(value)
  || Object.keys(value).sort().join(',')!=='activation_epoch,enabled' || typeof value.enabled!=='boolean'
  || typeof value.activation_epoch!=='string' || !uuid.test(value.activation_epoch)
  || value.activation_epoch==='00000000-0000-0000-0000-000000000000')throw Error('display_state_invalid');
 return Object.freeze({...value,verified:true});
}

export function createStateController({fetcher=globalThis.fetch,clock=Date.now}={}){
 let state=disabled(),sequence=0,pending=null,controller=null,deadline=null,lastAttempt=-Infinity,stop=null;
 const listeners=new Set();
 const emit=value=>{state=value;for(const listener of [...listeners])listener();};
 function invalidate(){
  ++sequence;controller?.abort();clearTimeout(deadline);pending=null;controller=null;emit(disabled());
 }
 function refresh({force=false}={}){
  if(pending)return pending;
  if(!force && clock()-lastAttempt<5000)return Promise.resolve(state);
  lastAttempt=clock();const turn=++sequence,abort=new AbortController();controller=abort;
  const work=(async()=>{
   let reader;
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
     deadline=setTimeout(rejectUnavailable,2000);
    })]);
    if(turn===sequence)emit(value);
   }catch{if(turn===sequence)emit(disabled());}
   finally{
    abort.abort();if(reader)void reader.cancel().catch(()=>{});
    if(turn===sequence){clearTimeout(deadline);pending=null;controller=null;}
   }
   return state;
  })();pending=work;return work;
 }
 function start(windowObject=window,documentObject=document){
  if(stop)return stop;
  const visible=()=>documentObject.visibilityState!=='hidden';
  const activity=()=>{invalidate();if(visible())void refresh({force:true});};
  const hiding=()=>invalidate();
  const timer=setInterval(()=>{if(visible())void refresh({force:true});},5000);
  windowObject.addEventListener('focus',activity);windowObject.addEventListener('pageshow',activity);
  windowObject.addEventListener('pagehide',hiding);documentObject.addEventListener('visibilitychange',activity);
  stop=()=>{clearInterval(timer);windowObject.removeEventListener('focus',activity);windowObject.removeEventListener('pageshow',activity);
   windowObject.removeEventListener('pagehide',hiding);documentObject.removeEventListener('visibilitychange',activity);stop=null;invalidate();};
  activity();return stop;
 }
 return Object.freeze({getSnapshot:()=>state,getServerSnapshot:disabled,
  subscribe:listener=>{listeners.add(listener);return()=>listeners.delete(listener);},refresh,start,invalidate});
}

export const productState=createStateController();
