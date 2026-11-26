// Sleep mode in the real workerd runtime: both SQLite Durable Objects, the internal copy read between them, a signed
// OFF and ON publication, and object storage that survives a restart (edited between restarts to stand in for time).
import {test,after} from 'node:test';
import assert from 'node:assert/strict';
import {createHmac,randomUUID} from 'node:crypto';
import {mkdtempSync,readdirSync,rmSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {DatabaseSync} from 'node:sqlite';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {LANES} from '../worker/recovery.mjs';
import {canonical} from '../worker/service-state.mjs';
import {DRAIN_MARGIN} from '../worker/quiet-timer.mjs';
const {Miniflare,Response:FixtureResponse}=await import(process.env.BOOKING_MINIFLARE_MODULE?
 pathToFileURL(process.env.BOOKING_MINIFLARE_MODULE).href:'miniflare');
const key=n=>Buffer.alloc(32,n).toString('base64url')+'=';
const env={BOOKING_INSTALLATION_ID:'891d05ec-8ab2-4a87-b537-1c30f2b694b6',BOOKING_PROJECT_ID:'example-practice',
 BOOKING_ENVIRONMENT:'test',BOOKING_PUBLIC_ORIGIN:'https://practice.example.test',BOOKING_RELEASE_DIGEST:'a'.repeat(64),
 BOOKING_RECOVERY_WORKER_KEY:key(21),BOOKING_EMAIL_WORKER_KEY:key(22),BOOKING_GOOGLE_WORKER_KEY:key(23),
 BOOKING_WAKE_KEY:key(24),BOOKING_MONITOR_KEY:key(25),
 BOOKING_CONTROL_READ_KEY:key(31),BOOKING_CONTROL_PUBLISH_KEY:key(32),BOOKING_CONTROL_RECONCILE_KEY:key(33)};
const secret=n=>Buffer.alloc(32,n);
const persist=mkdtempSync(join(tmpdir(),'booking-sleep-native-'));
after(()=>rmSync(persist,{recursive:true,force:true}));
let calls=0;const generation=randomUUID();
async function start() {
 const runtime=new Miniflare({modules:true,scriptPath:fileURLToPath(new URL('../worker/index.mjs',import.meta.url)),
  compatibilityDate:'2026-04-15',bindings:env,durableObjectsPersist:persist,
  durableObjects:{BOOKING_RECOVERY_STATE:{className:'BookingRecoveryState',useSQLite:true},
   BOOKING_PRODUCT_STATE:{className:'BookingProductState',useSQLite:true}},
  queueProducers:{BOOKING_WAKE_QUEUE:'example-wake'},
  queueConsumers:{'example-wake':{maxBatchSize:1,maxBatchTimeout:1,maxRetries:5}},
  outboundService:async request=>{
   calls++;const url=new URL(request.url);assert.equal(url.origin,env.BOOKING_PUBLIC_ORIGIN);
   assert.equal(url.pathname,'/api/internal/worker/plan');const body=await request.json();
   const value={contract:1,application:env.BOOKING_PROJECT_ID,environment:env.BOOKING_ENVIRONMENT,
    installation_id:env.BOOKING_INSTALLATION_ID,generation,release_digest:env.BOOKING_RELEASE_DIGEST,
    run_id:body.run_id,evaluated_at:Date.now(),cursor:0,
    lanes:Object.fromEntries(LANES.map(lane=>[lane,{remaining_due:0,next_due_at:null}])),attention:false};
   return new FixtureResponse(canonical(value),{headers:{'content-type':'application/json'}});
  }});
 await runtime.ready;
 return {runtime,worker:await runtime.getWorker()};
}
const sign=(purpose,body,n)=>createHmac('sha256',secret(n)).update('booking-product:'+env.BOOKING_INSTALLATION_ID+':'+
 env.BOOKING_ENVIRONMENT+':v1:'+purpose+':'+canonical(body)).digest('hex');
const snapshot={version:1,installation_id:env.BOOKING_INSTALLATION_ID,project:env.BOOKING_PROJECT_ID,environment:env.BOOKING_ENVIRONMENT,
 origin:env.BOOKING_PUBLIC_ORIGIN,enabled:false,restore_generation:randomUUID(),generation_sequence:'1',revision:'1',activation_epoch:randomUUID()};
function control(runtime,purpose,value,extra={}) {
 const body={version:1,installation_id:env.BOOKING_INSTALLATION_ID,project:env.BOOKING_PROJECT_ID,environment:env.BOOKING_ENVIRONMENT,
  purpose,operation_id:randomUUID(),issued_at_ms:Date.now(),snapshot:value,...extra};
 return runtime.dispatchFetch('https://worker.example.test/service-control/'+purpose,{method:'POST',
  headers:{'Content-Type':'application/json','X-Booking-Control-Signature':sign(purpose,body,purpose==='publish'?32:33)},body:canonical(body)});
}
const tick=worker=>worker.scheduled({scheduledTime:Date.now(),cron:'*/15 * * * *'});
const health=runtime=>runtime.dispatchFetch('https://worker.example.test/health',{headers:{authorization:'Bearer '+key(25)}});
async function internal(runtime) {
 const namespace=await runtime.getDurableObjectNamespace('BOOKING_PRODUCT_STATE');
 return namespace.get(namespace.idFromName('booking-product:'+env.BOOKING_INSTALLATION_ID+':'+env.BOOKING_ENVIRONMENT))
  .fetch('https://product.internal/internal/recovery-state');
}
// Stands in for time passing while the runtime is stopped: one object's SQLite file, edited directly.
function edit(className,change) {
 const folder=join(persist,'-'+className),files=readdirSync(folder).filter(name=>name.endsWith('.sqlite') && name!=='metadata.sqlite');
 assert.equal(files.length,1);const db=new DatabaseSync(join(folder,files[0]));
 try {change(db);} finally {db.close();}
}
const notebook=change=>edit('BookingRecoveryState',db=>{
 const view=JSON.parse(db.prepare('SELECT view FROM recovery_view WHERE singleton=1').get().view);
 db.prepare('UPDATE recovery_view SET view=? WHERE singleton=1').run(JSON.stringify({...view,...change}));
});

test('native sleep mode: internal copy, drain after the margin, rest across a restart, and ON waking at once',async()=>{
 let {runtime,worker}=await start();
 try {
  assert.equal((await internal(runtime)).status,503);
  assert.equal((await control(runtime,'reconcile',snapshot,{action:'initialize',expected_generation:null})).status,200);
  const read=await internal(runtime);assert.equal(read.status,200);
  const copy=await read.json();assert.deepEqual(Object.keys(copy).sort(),['idle','pending','published_at_ms']);
  assert.equal(copy.idle,true);assert.equal(copy.pending,false);assert.ok(Math.abs(Date.now()-copy.published_at_ms)<10000);
  // The internal path is not reachable from the internet, whatever the method.
  for(const method of ['GET','POST']) {
   const response=await runtime.dispatchFetch('https://worker.example.test/internal/recovery-state',{method,...(method==='POST'?{body:'{}'}:{})});
   assert.equal(response.status,404);assert.deepEqual(await response.json(),{code:'not_found'});
  }
  await tick(worker);assert.equal(calls,1);assert.equal((await health(runtime)).status,200);
  // Inside the margin the notebook rules apply: no call.
  await tick(worker);assert.equal(calls,1);
 } finally {await runtime.dispose();}
 const now=Date.now();
 edit('BookingProductState',db=>db.prepare('UPDATE product_state SET published_at_ms=?').run(now-DRAIN_MARGIN-50000));
 notebook({full_started_at:now-100000,run_started_at:now-100000,full_at:now-99000});
 ({runtime,worker}=await start());
 try {
  await tick(worker);assert.equal(calls,2,'the first tick after the margin drains');
  await tick(worker);assert.equal(calls,2,'then the site rests');assert.equal((await health(runtime)).status,200);
 } finally {await runtime.dispose();}
 // Thirteen hours later: today's rule would run the twelve-hour check; a resting site does not, and stays green.
 notebook({full_at:Date.now()-13*3600000});
 ({runtime,worker}=await start());
 try {
  await tick(worker);assert.equal(calls,2);assert.equal((await health(runtime)).status,200);
  // ON: the signed publication ends rest and the next tick runs at once.
  const enabled={...snapshot,enabled:true,revision:'2',activation_epoch:randomUUID()};
  assert.equal((await control(runtime,'publish',enabled)).status,200);
  assert.equal((await (await internal(runtime)).json()).idle,false);
  await tick(worker);assert.equal(calls,3);assert.equal((await health(runtime)).status,200);
  await tick(worker);assert.equal(calls,3);
  // A restore awaiting reconciliation reads as pending, so today's pace applies.
  const barrier={...enabled,enabled:false,restore_generation:randomUUID(),generation_sequence:'2',revision:'0',activation_epoch:randomUUID()};
  assert.equal((await control(runtime,'reconcile',barrier,{action:'advance_generation',expected_generation:enabled.restore_generation})).status,200);
  assert.deepEqual(await (await internal(runtime)).json(),{idle:true,pending:true,published_at_ms:(await (await internal(runtime)).json()).published_at_ms});
 } finally {await runtime.dispose();}
 notebook({full_at:Date.now()-13*3600000});
 ({runtime,worker}=await start());
 try {await tick(worker);assert.equal(calls,4,'pending: the twelve-hour rule runs');} finally {await runtime.dispose();}
 // A damaged stored copy answers 503 and never makes the timer sleep.
 edit('BookingProductState',db=>db.prepare('UPDATE product_state SET snapshot=?').run('{}'));
 notebook({full_at:Date.now()-13*3600000});
 ({runtime,worker}=await start());
 try {
  assert.equal((await internal(runtime)).status,503);
  await tick(worker);assert.equal(calls,5);
 } finally {await runtime.dispose();}
});
