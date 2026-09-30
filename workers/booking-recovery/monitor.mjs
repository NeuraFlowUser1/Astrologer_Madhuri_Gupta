// Independent observer entry point. Scheduling/notification destination must be
// configured separately. This never calls Vercel, Neon or a customer endpoint.
import {pathToFileURL} from 'node:url';
export const HEALTH_URL='https://sarsa-booking-recovery.neuraflowindia.workers.dev/health';
export async function checkRecovery(fetcher=fetch) {
  const response=await fetcher(HEALTH_URL,{redirect:'error',signal:AbortSignal.timeout(15_000),cache:'no-store'});
  if(response.status!==200 || !response.headers.get('content-type')?.startsWith('application/json')) {
    await response.body?.cancel();throw Error('Sarsa recovery needs attention.');
  }
  const reader=response.body?.getReader();
  if(!reader)throw Error('Sarsa recovery needs attention.');
  const chunks=[];let size=0;
  try {
    while(true) {
      const {done,value}=await reader.read();if(done)break;
      size+=value.byteLength;if(size>256)throw Error('Sarsa recovery needs attention.');chunks.push(value);
    }
    const bytes=new Uint8Array(size);let offset=0;
    for(const value of chunks){bytes.set(value,offset);offset+=value.byteLength;}
    const data=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
    if(!data || Object.keys(data).length!==1 || data.status!=='healthy')throw Error('Sarsa recovery needs attention.');
    return true;
  } finally {await reader.cancel().catch(()=>{});}
}
if(process.argv[1] && import.meta.url===pathToFileURL(process.argv[1]).href) {
  try {await checkRecovery();console.log('Sarsa recovery signal is healthy.');}
  catch {console.error('Sarsa recovery needs attention. Check the dedicated worker and saved pending work.');process.exitCode=1;}
}
