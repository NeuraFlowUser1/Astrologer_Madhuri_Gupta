import {test} from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {configuration,checkedPlan,checkedAck,checkedHint,caller,execute,LANES,queue,recoveryFetch,scheduled} from '../worker/recovery.mjs';
import {canonical} from '../worker/service-state.mjs';
const key=n=>Buffer.alloc(32,n).toString('base64url')+'=';
const env={BOOKING_INSTALLATION_ID:'891d05ec-8ab2-4a87-b537-1c30f2b694b6',BOOKING_PROJECT_ID:'example-practice',
 BOOKING_ENVIRONMENT:'test',BOOKING_PUBLIC_ORIGIN:'https://practice.example.test',BOOKING_RELEASE_DIGEST:'a'.repeat(64),
 BOOKING_RECOVERY_WORKER_KEY:key(21),BOOKING_EMAIL_WORKER_KEY:key(22),BOOKING_GOOGLE_WORKER_KEY:key(23),
 BOOKING_WAKE_KEY:key(24),BOOKING_MONITOR_KEY:key(25)};
const declared=configuration(env),generation=randomUUID();
const empty=()=>Object.fromEntries(LANES.map(lane=>[lane,{remaining_due:0,next_due_at:null}]));
const hint=()=>({contract:1,installation_id:declared.installation_id,release_digest:declared.release_digest,
 run_id:randomUUID(),source:'scheduled',scheduled_at:Date.now(),attempt:0});
function plan(work,lanes=empty(),cursor=0) {
 return {contract:1,application:declared.project,environment:declared.environment,installation_id:declared.installation_id,
  generation,release_digest:declared.release_digest,run_id:work.run_id,evaluated_at:Date.now(),cursor,lanes,attention:false};
}
const reply=value=>new Response(canonical(value),{headers:{'content-type':'application/json'}});
function server(work,{lanes=empty(),cursor=0,badLane=null,attention=false}={}) {
 const calls=[],initial=plan(work,lanes,cursor);initial.attention=attention;
 const fetcher=async(url,options)=>{
  const path=new URL(url).pathname;calls.push({path,options});
  if(path.endsWith('/plan')) return reply(initial);
  if(path.endsWith('/end')) return reply({completed:true,generation,release_digest:declared.release_digest,
   run_id:work.run_id,evaluated_at:Date.now(),lanes:empty(),attention:false});
  const lane=path.split('/').at(-1);
  const ack={contract:1,application:declared.project,environment:declared.environment,installation_id:declared.installation_id,
   generation,release_digest:declared.release_digest,run_id:work.run_id,lane,code:'completed-work',
   evaluated_at:Date.now(),processed:1,remaining_due:0,next_due_at:null,attention:false};
  if(lane===badLane) ack.processed=true;
  return reply(ack);
 };
 return {calls,fetcher,initial};
}

test('an idle evaluated plan makes one call, without nine empty consumers or an end query',async()=>{
 const work=hint(),fake=server(work);const value=await execute(env,work,{fetcher:fake.fetcher});
 assert.equal(value.healthy,true);assert.deepEqual(value.acknowledgements,{});assert.equal(fake.calls.length,1);
});
test('all nine busy lanes run once from the persisted cursor and use only their own capability',async()=>{
 const work=hint(),lanes=empty();for(const lane of LANES)lanes[lane]={remaining_due:1,next_due_at:Date.now()};
 const fake=server(work,{lanes,cursor:7});const value=await execute(env,work,{fetcher:fake.fetcher});
 assert.equal(value.healthy,true);assert.equal(Object.keys(value.acknowledgements).length,9);
 const lanesCalled=fake.calls.slice(1,-1).map(call=>call.path.split('/').at(-1));
 assert.deepEqual(lanesCalled,[...LANES.slice(7),...LANES.slice(0,7)]);
 for(const call of fake.calls.slice(1,-1)) {
  const lane=call.path.split('/').at(-1),expected=['verification_email','notification_email','email_events'].includes(lane)?key(22)
   :['booking_records','enquiry_records'].includes(lane)?key(23):key(21);
  assert.equal(call.options.headers.authorization,'Bearer '+expected);assert.equal(call.options.redirect,'manual');
 }
});
test('a boolean count is not a completed task even if the HTTP status is 200',async()=>{
 const work=hint(),lanes=empty();lanes.email_events={remaining_due:1,next_due_at:Date.now()};
 const fake=server(work,{lanes,badLane:'email_events'});const value=await execute(env,work,{fetcher:fake.fetcher});
 assert.equal(value.healthy,false);assert.equal(value.interrupted,true);assert.equal(value.acknowledgements.email_events,undefined);
});
test('wrong installation, release, generation, lane and result counts are refused',()=>{
 const work=hint(),p=plan(work),expected={...declared,run_id:work.run_id};
 for(const mutation of [{contract:true},{installation_id:randomUUID()},{release_digest:'b'.repeat(64)},
  {lanes:{...p.lanes,payment:{remaining_due:true,next_due_at:null}}},{evaluated_at:0}]) {
  assert.throws(()=>checkedPlan({...p,...mutation},expected));
 }
 const a={contract:1,application:p.application,environment:p.environment,installation_id:p.installation_id,
  generation:p.generation,release_digest:p.release_digest,run_id:p.run_id,lane:'payment',code:'evaluated-empty',
  evaluated_at:p.evaluated_at,processed:0,remaining_due:0,next_due_at:null,attention:false};
 assert.equal(checkedAck(a,p,'payment'),a);
 for(const mutation of [{generation:randomUUID()},{run_id:randomUUID()},{lane:'email_events'},{processed:true},
  {code:'completed-work'},{remaining_due:-1},{next_due_at:'soon'},{attention:1}]) assert.throws(()=>checkedAck({...a,...mutation},p,'payment'));
});
test('HTML, redirects, duplicate JSON keys and oversized responses do not prove progress',async()=>{
 const work=hint();
 const bodies=[new Response('<html>ready</html>',{headers:{'content-type':'text/html'}}),
  new Response('{}',{status:302,headers:{'content-type':'application/json'}}),
  new Response('{"completed":false,"completed":true}',{headers:{'content-type':'application/json'}}),
  new Response('"'+'x'.repeat(32768)+'"',{headers:{'content-type':'application/json'}})];
 for(const response of bodies) await assert.rejects(()=>execute(env,work,{fetcher:async()=>response}));
});
test('streaming responses are bounded by the caller deadline',async()=>{
 const streaming=new ReadableStream({start(){},cancel(){}});
 const call=caller(env,{fetcher:async()=>new Response(streaming,{headers:{'content-type':'application/json'}})});
 const start=Date.now();await assert.rejects(()=>call('/api/internal/worker/plan',{},'RECOVERY',start+30));
 assert.ok(Date.now()-start<1000);
});
test('finishing late risky work can clear attention only through the final saved summary',async()=>{
 const work=hint(),lanes=empty();lanes.notification_email={remaining_due:1,next_due_at:Date.now()};
 const fake=server(work,{lanes,attention:true});const value=await execute(env,work,{fetcher:fake.fetcher});
 assert.equal(value.healthy,true);assert.equal(fake.calls.at(-1).path,'/api/internal/worker/end');
});
test('wrong keys or stale and malformed opaque queue hints cannot select work',()=>{
 assert.throws(()=>configuration({...env,BOOKING_EMAIL_WORKER_KEY:key(21)}));
 assert.throws(()=>configuration({...env,BOOKING_WAKE_KEY:'bad'}));
 assert.throws(()=>configuration({...env,BOOKING_PROJECT_ID:'a'.repeat(76)}));
 const valid=hint();assert.equal(checkedHint(valid,env),valid);
 for(const mutation of [{attempt:6},{attempt:true},{source:'customer'},{run_id:randomUUID().toUpperCase()},
  {scheduled_at:Date.now()-900001},{installation_id:randomUUID()},{email:'private@example.test'}]) {
  assert.throws(()=>checkedHint({...valid,...mutation},env));
 }
});
test('queue transport failures retry; invalid hints are acknowledged without a provider call',async()=>{
 const messages=[{body:hint(),ack(){this.acked=true;},retry(){this.retried=true;}},
  {body:{email:'private@example.test'},ack(){this.acked=true;},retry(){this.retried=true;}}];
 let calls=0;const binding={idFromName(){return 'one';},get(){return {fetch(){calls++;throw Error('disconnected');}};}};
 await queue({messages},{...env,BOOKING_RECOVERY_STATE:binding});
 assert.equal(calls,1);assert.equal(messages[0].retried,true);assert.equal(messages[0].acked,undefined);
 assert.equal(messages[1].acked,true);assert.equal(messages[1].retried,undefined);
});
test('public wake endpoint accepts only an authenticated empty request and stores an opaque hint',async()=>{
 const queued=[],bound={...env,BOOKING_WAKE_QUEUE:{send(value){queued.push(value);}}};
 const make=body=>new Request('https://worker.example.test/wake',{method:'POST',headers:{'content-type':'application/json',authorization:'Bearer '+key(24)},body});
 assert.equal((await recoveryFetch(make('{"email":"private@example.test"}'),bound)).status,422);
 assert.equal(queued.length,0);assert.equal((await recoveryFetch(make('{}'),bound)).status,202);
 assert.equal(queued.length,1);checkedHint(queued[0],env);assert.ok(!canonical(queued[0]).includes('email'));
 assert.equal((await recoveryFetch(new Request('https://worker.example.test/health'),bound)).status,401);
});

test('idle future work reports its earliest due time and attention is never healthy',async()=>{
 const work=hint(),lanes=empty();lanes.payment.next_due_at=Date.now()+60000;lanes.enquiry_records.next_due_at=Date.now()+30000;
 const fake=server(work,{lanes,attention:true});const result=await execute(env,work,{fetcher:fake.fetcher});
 assert.equal(result.healthy,false);assert.equal(result.next_due_at,lanes.enquiry_records.next_due_at);assert.equal(fake.calls.length,1);
});

test('invalid final readback preserves pending work rather than inventing completion',async()=>{
 for(const mutation of [{completed:false},{generation:randomUUID()},{release_digest:'b'.repeat(64)},{run_id:randomUUID()},
  {evaluated_at:0},{attention:null},{lanes:{...empty(),payment:{remaining_due:true,next_due_at:null}}},
  {lanes:{...empty(),payment:{remaining_due:0,next_due_at:'soon'}}}]){
  const work=hint(),lanes=empty();lanes.payment={remaining_due:2,next_due_at:Date.now()+60000};const fake=server(work,{lanes});
  const fetcher=async(url,options)=>{
   const response=await fake.fetcher(url,options),value=await response.json();
   if(url.endsWith('/end'))return reply({...value,...mutation});
   if(url.endsWith('/payment'))return reply({...value,remaining_due:1,next_due_at:lanes.payment.next_due_at,attention:true});
   return reply(value);
  };
  const result=await execute(env,work,{fetcher});assert.equal(result.healthy,false);assert.equal(result.interrupted,true);
  assert.equal(result.remaining_due,1);assert.equal(result.next_due_at,lanes.payment.next_due_at);
 }
});

test('turn deadline stops new calls while retaining due work for the next run',async()=>{
 for(const elapsed of [65000,90000]){
  const work=hint(),lanes=empty();lanes.payment={remaining_due:1,next_due_at:Date.now()};const fake=server(work,{lanes});let clock=Date.now();const start=clock;
  const result=await execute(env,work,{now:()=>clock,onPlan:()=>{clock=start+elapsed;},fetcher:fake.fetcher});
  assert.equal(result.healthy,false);assert.equal(result.interrupted,true);assert.equal(fake.calls.some(c=>c.path.endsWith('/payment')),false);
  if(elapsed===90000)assert.equal(fake.calls.length,1);
 }
 const call=caller(env,{now:()=>100,fetcher:()=>assert.fail('Expired call reached network')});await assert.rejects(()=>call('/api/internal/worker/plan',{},'RECOVERY',100));
});

test('malformed projection numbers canonical key padding and different capability reuse fail closed',()=>{
 const work=hint(),p=plan(work),expected={...declared,run_id:work.run_id};
 for(const mutation of [{cursor:9},{attention:1},{lanes:{...p.lanes,payment:{remaining_due:0,next_due_at:-1}}},{generation:'00000000-0000-0000-0000-000000000000'}])assert.throws(()=>checkedPlan({...p,...mutation},expected));
 assert.throws(()=>configuration({...env,BOOKING_RELEASE_DIGEST:'bad'}));
 assert.throws(()=>configuration({...env,BOOKING_MONITOR_KEY:key(25).slice(0,42)+'B='}));
 assert.throws(()=>configuration({...env,BOOKING_CONTROL_READ_KEY:env.BOOKING_WAKE_KEY}));
 assert.equal(configuration({...env,BOOKING_CONTROL_READ_KEY:key(26)}).project,declared.project);
 const ack={...p,lane:'payment',code:'evaluated-empty',processed:0,remaining_due:0,next_due_at:null};delete ack.cursor;delete ack.lanes;
 for(const mutation of [{code:'evaluated-empty',processed:1},{code:'unknown'},{evaluated_at:p.evaluated_at-1},{processed:2}])assert.throws(()=>checkedAck({...ack,...mutation},p,'payment'));
 assert.throws(()=>checkedHint({...work,scheduled_at:Date.now()+61000},env));
});

test('wake method body limits and private health access do not expose database work',async()=>{
 const requests=[],binding={idFromName:()=> 'synthetic',get:()=>({fetch:async(...args)=>{requests.push(args);return new Response('ok');}})};
 const bound={...env,BOOKING_RECOVERY_STATE:binding,BOOKING_WAKE_QUEUE:{send:async()=>{}}};
 const request=(path,method='POST',headers={},body='{}')=>new Request('https://worker.example.test'+path,{method,headers:{authorization:'Bearer '+key(path.startsWith('/health')?25:24),'content-type':'application/json',...headers},...(method==='GET'?{}:{body})});
 assert.equal(await recoveryFetch(request('/unrelated'),bound),null);assert.equal((await recoveryFetch(request('/wake?extra=1'),bound)).status,400);
 assert.equal((await recoveryFetch(request('/wake','GET'),bound)).status,404);assert.equal((await recoveryFetch(request('/health'),bound)).status,404);
 assert.equal((await recoveryFetch(request('/health','GET'),bound)).status,200);assert.equal(requests.length,1);
 for(const headers of [{'content-type':'text/plain'},{'content-encoding':'gzip'}])assert.equal((await recoveryFetch(request('/wake','POST',headers),bound)).status,415);
 for(const body of [null,'x'.repeat(1025),new Uint8Array([255])])assert.equal((await recoveryFetch(request('/wake','POST',{},body),bound)).status,503);
 assert.equal((await recoveryFetch(request('/wake'),env)).status,503);
 assert.equal((await recoveryFetch(request('/health','GET'),env)).status,503);
 assert.equal((await recoveryFetch(request('/wake'),{...bound,BOOKING_WAKE_QUEUE:{send:async()=>{throw Error('synthetic queue failure');}}})).status,503);
});

test('scheduled and queued work preserve exact hint and report unavailable execution',async()=>{
 const calls=[];let status=200;
 const bound={...env,BOOKING_RECOVERY_STATE:{idFromName:name=>name,get:()=>({fetch:async(url,options)=>{calls.push({url,options});return new Response('{}',{status});}})}};
 await scheduled({scheduledTime:Date.now()},bound);assert.equal(calls.length,1);assert.equal(JSON.parse(calls[0].options.body).source,'scheduled');
 status=503;await assert.rejects(()=>scheduled({scheduledTime:Date.now()},bound));
 for(const scheduledTime of [null,Date.now()+60000,Date.now()-900001])await assert.rejects(()=>scheduled({scheduledTime},bound));
 const message=()=>({body:hint(),ack(){this.acked=true;},retry(value){this.retryOptions=value;}});
 const failed=message();await queue({messages:[failed]},bound);assert.deepEqual(failed.retryOptions,{delaySeconds:30});assert.equal(failed.acked,undefined);
 status=200;const accepted=message();await queue({messages:[accepted]},bound);assert.equal(accepted.acked,true);assert.equal(accepted.retryOptions,undefined);
});
