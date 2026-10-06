import {test,before,after} from 'node:test';
import assert from 'node:assert/strict';
import {createHmac,createHash,randomUUID} from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {canonical,checkedSnapshot} from '../worker/service-state.mjs';
import {facts} from '../worker/installation.mjs';
const {Miniflare}=await import(process.env.BOOKING_MINIFLARE_MODULE ?
  pathToFileURL(process.env.BOOKING_MINIFLARE_MODULE).href:'miniflare');
const keys={read:Buffer.alloc(32,11),publish:Buffer.alloc(32,12),reconcile:Buffer.alloc(32,13)};
const encoded=value=>value.toString('base64url')+'=';
const env={BOOKING_INSTALLATION_ID:'891d05ec-8ab2-4a87-b537-1c30f2b694b6',BOOKING_PROJECT_ID:'example-practice',
 BOOKING_ENVIRONMENT:'test',BOOKING_PUBLIC_ORIGIN:'https://practice.example.test',
 BOOKING_CONTROL_READ_KEY:encoded(keys.read),BOOKING_CONTROL_PUBLISH_KEY:encoded(keys.publish),
 BOOKING_CONTROL_RECONCILE_KEY:encoded(keys.reconcile)};
const declared=facts(env);
const sign=(purpose,body,secret)=>createHmac('sha256',secret).update('booking-product:'+
 declared.installation_id+':'+declared.environment+':v1:'+purpose+':'+canonical(body)).digest('hex');
const base={version:1,...declared,enabled:false,restore_generation:randomUUID(),generation_sequence:'1',
 revision:'1',activation_epoch:randomUUID()};
let current=base;let runtime;
before(async()=>{
 runtime=new Miniflare({modules:true,scriptPath:fileURLToPath(new URL('../worker/index.mjs',import.meta.url)),
  compatibilityDate:'2026-04-15',bindings:env,durableObjects:{BOOKING_PRODUCT_STATE:{className:'BookingProductState',useSQLite:true}}});
 await runtime.ready;
});
after(async()=>{await runtime?.dispose();});
async function submit(purpose,snapshot,extra={},secret=keys[purpose],raw=null){
 const body={version:1,installation_id:declared.installation_id,project:declared.project,environment:declared.environment,
  purpose,operation_id:randomUUID(),issued_at_ms:Date.now(),snapshot,...extra};
 return runtime.dispatchFetch('https://worker.example.test/service-control/'+purpose,{method:'POST',
   headers:{'Content-Type':'application/json','X-Booking-Control-Signature':sign(purpose,body,secret)},
   body:raw??canonical(body)});
}
async function read(nonce='a'.repeat(64)){
 return runtime.dispatchFetch('https://worker.example.test/service-state',{headers:{'X-Booking-State-Nonce':nonce}});
}

test('uninitialized projection is unavailable and an ordinary publisher cannot initialize it',async()=>{
 assert.equal((await read()).status,503);
 assert.equal((await submit('publish',base)).status,503);
});
test('maintenance initializes only off, with an immutable first generation',async()=>{
 assert.equal((await submit('reconcile',{...base,enabled:true},{action:'initialize',expected_generation:null})).status,409);
 assert.equal((await submit('reconcile',base,{action:'initialize',expected_generation:null})).status,200);
 assert.equal((await submit('reconcile',base,{action:'initialize',expected_generation:null})).status,409);
});
test('fresh read is nonce bound and signed independently of publication age',async()=>{
 const response=await read();assert.equal(response.status,200);
 const value=await response.json();assert.deepEqual(value.snapshot,base);assert.equal(value.nonce,'a'.repeat(64));
 const {signature,...body}=value;assert.equal(signature,sign('read',body,keys.read));
 assert.equal(value.snapshot_hash,createHash('sha256').update(canonical(base)).digest('hex'));
 assert.ok(value.published_at_ms<=value.issued_at_ms);
 assert.equal((await read('bad')).status,400);
});
test('publisher must use its own key and canonical bounded unambiguous input',async()=>{
 assert.equal((await submit('publish',base,{},keys.read)).status,401);
 assert.equal((await submit('publish',base,{},keys.publish,'{"version":1,"version":1}')).status,400);
 assert.equal((await submit('publish',base,{},keys.publish,' '.repeat(4097))).status,400);
});
test('newer publish is accepted but an equal revision with changed meaning is rejected',async()=>{
 current={...base,enabled:true,revision:'2',activation_epoch:randomUUID()};
 const response=await submit('publish',current);assert.equal(response.status,200);
 const value=await response.json();const {signature,...body}=value;
 assert.equal(signature,sign('publish-ack',body,keys.publish));
 assert.equal((await submit('publish',{...current,enabled:false})).status,409);
 assert.equal((await submit('publish',base)).status,409);
});
test('concurrent stale on and newer off cannot leave the projection on',async()=>{
 const off={...current,enabled:false,revision:'3',activation_epoch:randomUUID()};
 const responses=await Promise.all([submit('publish',current),submit('publish',off)]);
 assert.ok(responses.every(response=>[200,409].includes(response.status)));
 assert.deepEqual((await (await read()).json()).snapshot,off);current=off;
 assert.equal((await submit('publish',{...base,enabled:true,revision:'2'})).status,409);
});
test('restore barrier advances outside the restored database and prevents old on from winning',async()=>{
 const barrier={...current,enabled:false,restore_generation:randomUUID(),generation_sequence:'2',revision:'0',activation_epoch:randomUUID()};
 assert.equal((await submit('reconcile',barrier,{action:'advance_generation',expected_generation:current.restore_generation})).status,200);
 assert.equal((await read()).status,503);
 assert.equal((await submit('publish',{...current,enabled:true,revision:'100'})).status,409);
 const off={...barrier,revision:'1'};
 assert.equal((await submit('publish',{...off,enabled:true})).status,503);
 assert.equal((await submit('publish',off)).status,200);
 assert.deepEqual((await (await read()).json()).snapshot,off);current=off;
});
test('another installation, origin or environment cannot publish into this object',async()=>{
 for(const changed of [{installation_id:randomUUID()},{origin:'https://other.example.test'},{environment:'production'}]){
  assert.equal((await submit('publish',{...current,...changed,revision:'2'})).status,400);
 }
});
test('all counters stay decimal strings through the full signed exchange',async()=>{
 const large={...current,revision:'9007199254740993',activation_epoch:randomUUID()};
 assert.equal((await submit('publish',large)).status,200);
 assert.equal((await (await read()).json()).snapshot.revision,'9007199254740993');
 for(const revision of [true,2,2.5,'0','01','9223372036854775808']){
  assert.throws(()=>checkedSnapshot({...large,revision},env));
 }
});

test('state endpoints reject stale signed requests and unsupported transport without changing saved mode',async()=>{
 const before=(await (await read()).json()).snapshot;
 for(const path of ['/service-state?other=1','/service-control/unknown'])assert.equal((await runtime.dispatchFetch('https://worker.example.test'+path)).status,path.includes('?')?400:404);
 for(const headers of [{'Content-Type':'text/plain'},{'Content-Type':'application/json','Content-Encoding':'gzip'}]){
  assert.equal((await runtime.dispatchFetch('https://worker.example.test/service-control/publish',{method:'POST',headers,body:'{}'})).status,400);
 }
 assert.equal((await submit('publish',before,{issued_at_ms:Date.now()-120000})).status,400);
 assert.equal((await submit('publish',before,{operation_id:'00000000-0000-0000-0000-000000000000'})).status,400);
 assert.equal((await runtime.dispatchFetch('https://worker.example.test/service-control/publish',{method:'POST',headers:{'Content-Type':'application/json'},body:canonical({version:1,installation_id:declared.installation_id,project:declared.project,environment:declared.environment,purpose:'publish',operation_id:randomUUID(),issued_at_ms:Date.now(),snapshot:before})})).status,401);
 assert.deepEqual((await (await read()).json()).snapshot,before);
});

test('generation recovery can replay its exact operation but cannot reuse it for changed meaning',async()=>{
 const before=(await (await read()).json()).snapshot,operation_id=randomUUID();
 const barrier={...before,enabled:false,restore_generation:randomUUID(),generation_sequence:String(BigInt(before.generation_sequence)+1n),revision:'0',activation_epoch:randomUUID()};
 const extra={operation_id,action:'advance_generation',expected_generation:before.restore_generation};
 assert.equal((await submit('reconcile',barrier,extra)).status,200);
 assert.equal((await submit('reconcile',barrier,extra)).status,200);
 assert.equal((await submit('reconcile',{...barrier,activation_epoch:randomUUID()},extra)).status,409);
 assert.equal((await submit('reconcile',barrier,{action:'unknown',expected_generation:before.restore_generation})).status,400);
 assert.equal((await submit('reconcile',barrier,{...extra,operation_id:randomUUID(),expected_generation:randomUUID()})).status,409);
 const off={...barrier,revision:'1'};assert.equal((await submit('publish',off)).status,200);
 assert.deepEqual((await (await read()).json()).snapshot,off);
});
