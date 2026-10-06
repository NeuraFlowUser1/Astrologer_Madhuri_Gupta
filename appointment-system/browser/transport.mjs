/** Bounded same-origin JSON transport. Errors contain codes, never submitted fields. */
export class RequestError extends Error{
 constructor(code='temporarily_unavailable',{status=0,retryAfter=0}={}){
  super(code);this.name='RequestError';this.code=code;this.status=status;this.retryAfter=retryAfter;
 }
}

export function createTransport({allowed,fetcher=globalThis.fetch,timeout=60000,maximum=65536}={}){
 if(typeof allowed!=='function' || !Number.isSafeInteger(timeout) || timeout<1 || timeout>60000
   || !Number.isSafeInteger(maximum) || maximum<1 || maximum>131072)throw new TypeError('Explicit transport bounds required.');
 return async function request(path,{body,headers={},signal}={}){
  if(typeof path!=='string' || !path.startsWith('/api/') || /[\\#\u0000-\u001f\u007f]/.test(path)
    || !allowed(path))throw new RequestError('invalid_request');
  const abort=new AbortController();let timer,reader;
  const cancel=()=>abort.abort();signal?.addEventListener('abort',cancel,{once:true});
  if(signal?.aborted)cancel();
  try{
   return await Promise.race([(async()=>{
    if(abort.signal.aborted)throw new RequestError('request_cancelled');
    const response=await fetcher(path,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',
     redirect:'error',signal:abort.signal,headers:{Accept:'application/json',...(body===undefined?{}:{'Content-Type':'application/json'}),...headers},
     ...(body===undefined?{}:{body:JSON.stringify(body)})});
    if(response.headers.get('content-type')?.split(';')[0].trim()!=='application/json' || !response.body)
     throw new RequestError('temporarily_unavailable',{status:response.status});
    reader=response.body.getReader();const decoder=new TextDecoder('utf-8',{fatal:true});let length=0,text='';
    while(true){const {done,value}=await reader.read();if(done)break;length+=value.byteLength;
     if(length>maximum)throw new RequestError('invalid_response');text+=decoder.decode(value,{stream:true});}
    const data=JSON.parse(text+decoder.decode());
    if(!data || typeof data!=='object' || Array.isArray(data))throw new RequestError('invalid_response');
    if(!response.ok){
     const code=typeof data.code==='string' && /^[a-z][a-z0-9_]{0,63}$/.test(data.code)?data.code:'temporarily_unavailable';
     const retry=response.headers.get('retry-after');
     throw new RequestError(code,{status:response.status,retryAfter:retry && /^[0-9]{1,9}$/.test(retry)?Math.min(3600,Number(retry)):0});
    }
    return data;
   })(),new Promise((_,reject)=>{
    abort.signal.addEventListener('abort',()=>reject(new RequestError('request_cancelled')),{once:true});
    timer=setTimeout(()=>reject(new RequestError('temporarily_unavailable')),timeout);
   })]);
  }catch(error){if(error instanceof RequestError)throw error;throw new RequestError('temporarily_unavailable');}
  finally{clearTimeout(timer);signal?.removeEventListener('abort',cancel);abort.abort();if(reader)void reader.cancel().catch(()=>{});}
 };
}
