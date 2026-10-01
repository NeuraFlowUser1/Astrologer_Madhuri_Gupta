import {expect,test,vi,afterEach} from 'vitest';
import {createWorker} from '../../../workers/booking-recovery/worker.mjs';
import {checkRecovery,HEALTH_URL} from '../../../workers/booking-recovery/monitor.mjs';
import {pages,titleFor} from '../../src/site/page-metadata.mjs';

const APP='004-sarsa-jyotish-sansthan',KEY='a'.repeat(43)+'=';
const idle=()=>({application:APP,version:1,attention:false,lanes:{contact_email:null,payment_events:null,payment:null,google:null,email_events:null,email:null,contact_google:null,maintenance:null}});
function environment(){const writes=[],sent=[];return {writes,sent,SARSA_WAKE_KEY:KEY,SARSA_RECOVERY_WORKER_KEY:KEY,SARSA_GOOGLE_WORKER_KEY:KEY,SARSA_EMAIL_WORKER_KEY:KEY,HEARTBEATS:{get:async()=>null,put:async(k,v)=>writes.push(JSON.parse(v))},WAKE_QUEUE:{send:async(...args)=>sent.push(args)}};}
function message(remaining=8){return {body:{version:1,remaining},ack:vi.fn(),retry:vi.fn()};}
afterEach(()=>vi.restoreAllMocks());

test('monitor rejects missing body and uses only its fixed public signal with default transport',async()=>{
 await expect(checkRecovery(async()=>new Response(null,{headers:{'content-type':'application/json'}}))).rejects.toThrow('needs attention');
 vi.stubGlobal('fetch',vi.fn(async()=>Response.json({status:'healthy'})));
 try{expect(await checkRecovery()).toBe(true);expect(fetch.mock.calls[0][0]).toBe(HEALTH_URL);}finally{vi.unstubAllGlobals();}
});
test('worker failure boundaries reject missing secrets, missing bodies and aborted requests without private diagnostics',async()=>{
 for(const kind of ['secret','body','content','abort']){
  const env=environment(),fetcher=vi.fn(async()=>{if(kind==='abort')throw new DOMException('private provider detail','AbortError');return new Response(null,{headers:{'content-type':kind==='content'?'text/plain':'application/json'}});});
  if(kind==='secret')env.SARSA_RECOVERY_WORKER_KEY='bad';
  const worker=createWorker({now:()=>1800000,fetcher});await expect(worker.scheduled({scheduledTime:1800000},env)).rejects.toThrow(kind==='secret'?'configuration_missing':kind==='abort'?'backend_timeout':'response_invalid');expect(env.writes[0].healthy).toBe(false);if(kind==='secret')expect(fetcher).not.toHaveBeenCalled();
 }
});
test('worker wake requires the correct identity encoding and records failure only when publication fails',async()=>{
 const env=environment(),worker=createWorker({fetcher:()=>{throw Error('must not read database');}});
 const request=encoding=>new Request('https://worker.invalid/wake',{method:'POST',headers:{'content-type':'application/json',authorization:'Bearer '+KEY,...(encoding?{'content-encoding':encoding}:{})},body:'{}'});
 expect((await worker.fetch(request('gzip'),env)).status).toBe(400);expect(env.sent).toHaveLength(0);
 expect((await worker.fetch(request('identity'),env)).status).toBe(202);
 env.SARSA_WAKE_KEY='bad';expect((await worker.fetch(request(),env)).status).toBe(401);
 env.SARSA_WAKE_KEY=KEY;env.WAKE_QUEUE.send=async()=>{throw Error('private');};expect((await worker.fetch(request(),env)).status).toBe(503);
 env.HEARTBEATS.get=async()=>{throw Error('private');};expect((await worker.fetch(new Request('https://worker.invalid/health'),env)).status).toBe(503);
});
test.each([{processed:-1},{processed:2},{processed:true},{processed:1,retry:true}])('a rejected lane result %j retries the wake without acknowledging provider success',async outcome=>{
 const before=idle();before.lanes.google=0;const env=environment(),m=message();vi.spyOn(console,'warn').mockImplementation(()=>{});
 const worker=createWorker({now:()=>1800000,fetcher:async url=>Response.json(url.endsWith('/plan')?before:{application:APP,...outcome})});await worker.queue({messages:[m]},env);expect(m.ack).not.toHaveBeenCalled();expect(m.retry).toHaveBeenCalledWith({delaySeconds:60});expect(env.sent).toHaveLength(0);
});
test.each([0,1])('continued work with processed=%s is bounded and respects the due time',async processed=>{
 const due=idle();due.lanes.email=0;const env=environment(),m=message();const worker=createWorker({now:()=>1800000,fetcher:async url=>Response.json(url.endsWith('/plan')?due:{application:APP,processed})});await worker.queue({messages:[m]},env);expect(m.ack).toHaveBeenCalledOnce();expect(env.sent).toEqual([[{version:1,remaining:7},{delaySeconds:processed?5:60}]]);
});
test('failed heartbeat publication cannot be called a successful rescue',async()=>{
 const env=environment();env.HEARTBEATS.put=async()=>{throw Error('private');};const worker=createWorker({now:()=>1800000,fetcher:async()=>Response.json(idle())});await expect(worker.scheduled({scheduledTime:1800000},env)).rejects.toThrow('heartbeat_write_failed');
});
test('page title metadata distinguishes every published page from a missing path',()=>{
 for(const [path,[title]] of Object.entries(pages))expect(titleFor(path)).toBe(title+' | Sarsa Jyotish Sansthan');
 expect(titleFor('/absent')).toBe('Page not found | Sarsa Jyotish Sansthan');
});
