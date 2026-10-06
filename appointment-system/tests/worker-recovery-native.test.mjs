// Actual workerd/SQLite Durable Objects and queue transport, with a disconnected API fixture.
import {test,before,after} from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {LANES} from '../worker/recovery.mjs';
import {canonical} from '../worker/service-state.mjs';
const {Miniflare,Response:FixtureResponse}=await import(process.env.BOOKING_MINIFLARE_MODULE?
 pathToFileURL(process.env.BOOKING_MINIFLARE_MODULE).href:'miniflare');
const key=n=>Buffer.alloc(32,n).toString('base64url')+'=';
const env={BOOKING_INSTALLATION_ID:'891d05ec-8ab2-4a87-b537-1c30f2b694b6',BOOKING_PROJECT_ID:'example-practice',
 BOOKING_ENVIRONMENT:'test',BOOKING_PUBLIC_ORIGIN:'https://practice.example.test',BOOKING_RELEASE_DIGEST:'a'.repeat(64),
 BOOKING_RECOVERY_WORKER_KEY:key(21),BOOKING_EMAIL_WORKER_KEY:key(22),BOOKING_GOOGLE_WORKER_KEY:key(23),
 BOOKING_WAKE_KEY:key(24),BOOKING_MONITOR_KEY:key(25)};
let runtime,worker,calls=0,bad=false;const generation=randomUUID();
before(async()=>{
 runtime=new Miniflare({modules:true,scriptPath:fileURLToPath(new URL('../worker/index.mjs',import.meta.url)),
  compatibilityDate:'2026-04-15',bindings:env,
  durableObjects:{BOOKING_RECOVERY_STATE:{className:'BookingRecoveryState',useSQLite:true}},
  queueProducers:{BOOKING_WAKE_QUEUE:'example-wake'},
  queueConsumers:{'example-wake':{maxBatchSize:1,maxBatchTimeout:1,maxRetries:5}},
  outboundService:async request=>{
   calls++;const url=new URL(request.url);assert.equal(url.origin,env.BOOKING_PUBLIC_ORIGIN);
   assert.equal(url.pathname,'/api/internal/worker/plan');const body=await request.json();
   assert.equal(request.headers.get('authorization'),'Bearer '+key(21));
   if(bad) return new FixtureResponse('<html>wrong page</html>',{headers:{'content-type':'text/html'}});
   const value={contract:1,application:env.BOOKING_PROJECT_ID,environment:env.BOOKING_ENVIRONMENT,
    installation_id:env.BOOKING_INSTALLATION_ID,generation,release_digest:env.BOOKING_RELEASE_DIGEST,
    run_id:body.run_id,evaluated_at:Date.now(),cursor:0,
    lanes:Object.fromEntries(LANES.map(lane=>[lane,{remaining_due:0,next_due_at:null}])),attention:false};
   return new FixtureResponse(canonical(value),{headers:{'content-type':'application/json'}});
  }});
 await runtime.ready;worker=await runtime.getWorker();
 assert.equal(typeof worker.scheduled,'function','The native scheduler hook must exist; do not silently skip it.');
});
after(async()=>{await runtime?.dispose();});
const health=()=>runtime.dispatchFetch('https://worker.example.test/health',{headers:{authorization:'Bearer '+key(25)}});

test('native scheduled recovery records an actual evaluated idle plan in SQLite',async()=>{
 assert.equal((await health()).status,503);assert.equal(calls,0);
 await worker.scheduled({scheduledTime:Date.now(),cron:'*/15 * * * *'});
 assert.equal(calls,1);const response=await health();assert.equal(response.status,200);
 assert.deepEqual(await response.json(),{status:'healthy'});
});
test('independent native health reads make no additional website or database calls',async()=>{
 const before=calls;
 for(let i=0;i<3;i++) assert.equal((await health()).status,200);
 assert.equal(calls,before);
 assert.equal((await runtime.dispatchFetch('https://worker.example.test/health')).status,401);
});
test('native queue wakes only saved work and does not require customer data',async()=>{
 const before=calls;
 const result=await runtime.dispatchFetch('https://worker.example.test/wake',{method:'POST',
  headers:{'content-type':'application/json',authorization:'Bearer '+key(24)},body:'{}'});
 assert.equal(result.status,202);
 const until=Date.now()+5000;while(calls===before && Date.now()<until) await new Promise(resolve=>setTimeout(resolve,50));
 assert.equal(calls,before+1);
 const response=await runtime.dispatchFetch('https://worker.example.test/wake',{method:'POST',
  headers:{'content-type':'application/json',authorization:'Bearer '+key(24)},body:'{"recipient":"private@example.test"}'});
 assert.equal(response.status,422);assert.equal(calls,before+1);
});
test('a 200 HTML deployment page cannot mark the next scheduled run healthy',async()=>{
 bad=true;await worker.scheduled({scheduledTime:Date.now(),cron:'*/15 * * * *'});
 const response=await health();assert.equal(response.status,503);assert.deepEqual(await response.json(),{status:'attention'});
 const before=calls;await health();assert.equal(calls,before);
});
