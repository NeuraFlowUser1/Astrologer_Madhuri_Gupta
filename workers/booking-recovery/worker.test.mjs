import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorker,checkedPlan} from './worker.mjs';
import {readFileSync} from 'node:fs';
const APP='004-sarsa-jyotish-sansthan', SECRET='a'.repeat(43)+'=';
const idle=()=>({application:APP,version:1,attention:false,lanes:{email:null,email_events:null,google:null,payment:null,payment_events:null,contact_email:null,contact_google:null}});
function fixture(states=[idle()], handler) {
  const writes=[],sends=[],calls=[],records=new Map();
  let time=1_800_000,index=0;
  const env={SARSA_WAKE_KEY:SECRET,SARSA_RECOVERY_WORKER_KEY:SECRET,SARSA_GOOGLE_WORKER_KEY:SECRET,SARSA_EMAIL_WORKER_KEY:SECRET,
    WAKE_QUEUE:{async send(...args){sends.push(args);}},
    HEARTBEATS:{async put(k,v){writes.push([k,JSON.parse(v)]);records.set(k,JSON.parse(v));},async get(k){return records.get(k) || null;}}};
  const worker=createWorker({now:()=>time,fetcher:async (url,options)=>{
    calls.push([url,options]);
    assert.equal(new URL(url).origin,'https://www.sarsajyotishsansthan.com');
    assert.equal(options.body,'{}');assert.equal(options.redirect,'manual');
    if(url.endsWith('/plan')) return Response.json(states[Math.min(index++,states.length-1)]);
    return handler ? handler(url,options):Response.json({application:APP,processed:1});
  }});
  return {worker,env,writes,sends,calls,records,setTime:v=>time=v};
}
function message(body={version:1,remaining:8}) {
  return {body,acks:0,retries:[],ack(){this.acks++;},retry(v){this.retries.push(v);}};
}
const request=(path,body='{}',auth=true)=>new Request('https://sarsa-booking-recovery.test.workers.dev'+path,
  {method:'POST',headers:{'content-type':'application/json',...(auth?{authorization:'Bearer '+SECRET}:{})},body});

test('additive maintenance accepts old plans and invokes only the protected new lane when due',async()=>{
  assert.equal(checkedPlan(idle()).version,1);
  const due=idle();due.lanes.maintenance=0;
  const done=idle();done.lanes.maintenance=null;
  const f=fixture([due,done]);const m=message();await f.worker.queue({messages:[m]},f.env);
  assert.equal(m.acks,1);assert.equal(m.retries.length,0);
  const calls=f.calls.filter(([url])=>!url.endsWith('/plan'));
  assert.equal(calls.length,1);assert.ok(calls[0][0].endsWith('/maintenance'));
  assert.equal(calls[0][1].headers.authorization,'Bearer '+SECRET);
  due.lanes.unknown=0;assert.throws(()=>checkedPlan(due),/plan_invalid/);
});

test('idle scheduled rescue reads plan once, no queue or provider work',async()=>{
  const f=fixture();await f.worker.scheduled({scheduledTime:1_800_000},f.env);
  assert.equal(f.calls.length,1);assert.equal(f.sends.length,0);assert.equal(f.writes[0][1].healthy,true);
});
test('scheduled rescue publishes only a hint, records success after queue acceptance',async()=>{
  const state=idle();state.lanes.google=0;const f=fixture([state]);
  await f.worker.scheduled({scheduledTime:1_800_000},f.env);
  assert.deepEqual(f.sends,[[{version:1,remaining:8}]]);assert.equal(f.writes[0][1].healthy,true);
});
test('failed queue publish records unhealthy and fails the scheduled invocation',async()=>{
  const state=idle();state.lanes.email=0;const f=fixture([state]);f.env.WAKE_QUEUE.send=async()=>{throw Error('private');};
  await assert.rejects(f.worker.scheduled({scheduledTime:1_800_000},f.env));assert.equal(f.writes[0][1].healthy,false);
});
test('attention does not suppress rescue but cannot produce healthy monitoring',async()=>{
  const state=idle();state.attention=true;state.lanes.payment=0;const f=fixture([state]);
  await assert.rejects(f.worker.scheduled({scheduledTime:1_800_000},f.env));assert.equal(f.sends.length,1);assert.equal(f.writes[0][1].healthy,false);
});
test('health reads only KV and detects stopped scheduler after grace',async()=>{
  const f=fixture();await f.worker.scheduled({scheduledTime:1_800_000},f.env);f.calls.length=0;
  const req=new Request('https://worker.invalid/health');
  assert.equal((await f.worker.fetch(req,f.env)).status,200);
  f.setTime(3_000_001);assert.equal((await f.worker.fetch(req,f.env)).status,503);assert.equal(f.calls.length,0);
});
test('missing KV, failed/newest sweep and future timestamp fail health closed',async()=>{
  const f=fixture();const req=new Request('https://worker.invalid/health');
  assert.equal((await f.worker.fetch(req,f.env)).status,503);
  f.records.set('sweep:2',{scheduled_at:1_800_000,completed_at:1_800_001,healthy:true});
  assert.equal((await f.worker.fetch(req,f.env)).status,503);
  f.records.set('sweep:2',{scheduled_at:1_800_000,completed_at:1_800_000,healthy:false});
  assert.equal((await f.worker.fetch(req,f.env)).status,503);
});
test('wake authentication, tiny empty JSON, no forwarding or database call',async()=>{
  const f=fixture();
  assert.equal((await f.worker.fetch(request('/wake','{}',false),f.env)).status,401);
  assert.equal((await f.worker.fetch(request('/wake','{"recipient":"x"}'),f.env)).status,400);
  assert.equal((await f.worker.fetch(request('/wake','[]'),f.env)).status,400);
  assert.equal((await f.worker.fetch(request('/wake',' '.repeat(65)+'{}'),f.env)).status,400);
  assert.equal((await f.worker.fetch(request('/wake?url=https://other.invalid'),f.env)).status,404);
  assert.equal((await f.worker.fetch(request('/wake'),f.env)).status,202);
  assert.equal(f.sends.length,1);assert.equal(f.calls.length,0);
});
test('queue acknowledges empty system without an infinite continuation',async()=>{
  const f=fixture(),m=message();await f.worker.queue({messages:[m]},f.env);
  assert.equal(m.acks,1);assert.equal(f.calls.length,2);assert.equal(f.sends.length,0);
});
test('due lanes run once, future work delayed, new Google email picked up next pass',async()=>{
  const before=idle(),after=idle();before.lanes.google=0;after.lanes.email=15;
  const f=fixture([before,after]),m=message();await f.worker.queue({messages:[m]},f.env);
  assert.equal(m.acks,1);assert.equal(f.calls.filter(([u])=>u.endsWith('/google/run')).length,1);
  assert.deepEqual(f.sends,[[{version:1,remaining:7},{delaySeconds:15}]]);
});
test('broken lane cannot starve a separate lane or acknowledge incomplete execution',async()=>{
  const before=idle();before.lanes.payment=0;before.lanes.email=0;
  const f=fixture([before],url=>url.endsWith('/payment')?new Response('failure',{status:503}):Response.json({application:APP,processed:1}));
  const m=message();await f.worker.queue({messages:[m]},f.env);
  assert.equal(m.acks,0);assert.equal(m.retries.length,1);assert(f.calls.some(([u])=>u.endsWith('/email/run')));assert.equal(f.sends.length,0);
});
test('malformed queue message never reaches backend',async()=>{
  const f=fixture(),m=message({version:1,remaining:100,job:'private'});await f.worker.queue({messages:[m]},f.env);
  assert.equal(f.calls.length,0);assert.equal(m.acks,1);
});
test('bounded continuation ends even with persistent pending work',async()=>{
  const state=idle();state.lanes.email=0;const f=fixture([state]),m=message({version:1,remaining:0});
  await f.worker.queue({messages:[m]},f.env);assert.equal(m.acks,1);assert.equal(f.sends.length,0);
});
test('success response with another project identity is never acknowledged',async()=>{
  const before=idle();before.lanes.email=0;const f=fixture([before],()=>Response.json({application:'003',processed:1}));
  const m=message();await f.worker.queue({messages:[m]},f.env);assert.equal(m.acks,0);assert.equal(m.retries.length,1);
});
test('database planning failure records failed scheduled check',async()=>{
  const f=fixture([{application:'003'}]);await assert.rejects(f.worker.scheduled({scheduledTime:1_800_000},f.env));
  assert.equal(f.writes[0][1].healthy,false);assert.equal(f.sends.length,0);
});
test('stale scheduled event cannot refresh health',async()=>{
  const f=fixture();await assert.rejects(f.worker.scheduled({scheduledTime:0},f.env));assert.equal(f.calls.length,0);assert.equal(f.writes.length,0);
});
test('scheduled HTTP failure reports only status and keeps a failed heartbeat',async()=>{
  const f=fixture();
  const worker=createWorker({now:()=>1_800_000,fetcher:async()=>new Response('private provider response', {status:401})});
  await assert.rejects(worker.scheduled({scheduledTime:1_800_000},f.env),error=>error.message==='backend_http_401');
  assert.equal(f.writes.length,1);assert.equal(f.writes[0][1].healthy,false);
});
test('redirects are rejected without forwarding the protected request',async()=>{
  const f=fixture(),calls=[];
  const worker=createWorker({now:()=>1_800_000,fetcher:async(url,options)=>{
    calls.push(url);assert.equal(options.redirect,'manual');
    return new Response(null,{status:302,headers:{location:'https://untrusted.invalid/'}});
  }});
  await assert.rejects(worker.scheduled({scheduledTime:1_800_000},f.env),error=>error.message==='backend_http_302');
  assert.deepEqual(calls,['https://www.sarsajyotishsansthan.com/api/internal/recovery/plan']);
  assert.equal(f.writes[0][1].healthy,false);
});
test('malformed responses and unknown provider errors cannot enter diagnostic text',async()=>{
  for(const fetcher of [async()=>new Response('private-provider-response',{headers:{'content-type':'application/json'}}),async()=>{throw Error('private authorization or provider detail');}]) {
    const f=fixture(),worker=createWorker({now:()=>1_800_000,fetcher});
    await assert.rejects(worker.scheduled({scheduledTime:1_800_000},f.env),error=>error.message==='backend_request_failed');
    assert.equal(f.writes[0][1].healthy,false);
  }
});
test('queue retries include a fixed safe cause without private provider content',async()=>{
  const f=fixture(),item=message(),logs=[],warn=console.warn;
  const worker=createWorker({now:()=>1_800_000,fetcher:async()=>new Response('private provider response',{status:421})});
  console.warn=(...parts)=>logs.push(parts);
  try{await worker.queue({messages:[item]},f.env);}finally{console.warn=warn;}
  assert.equal(item.acks,0);assert.deepEqual(item.retries,[{delaySeconds:60}]);
  assert.deepEqual(logs,[['recovery_wake_retry','backend_http_421']]);
});
test('contract rejects missing lanes, nonnumeric or out of bounds delay',()=>{
  for(const value of [null,{}, {...idle(),lanes:{}}, {...idle(),lanes:{...idle().lanes,email:true}}, {...idle(),lanes:{...idle().lanes,email:901}}])assert.throws(()=>checkedPlan(value));
});
test('config pins Sarsa account, queue, cadence and one consumer',()=>{
  const c=JSON.parse(readFileSync(new URL('./wrangler.json',import.meta.url),'utf8'));
  assert.equal(c.kv_namespaces[0].id,'927be5fbe5c54002ae03e55c48a0a2e5');
  assert.deepEqual(c.triggers.crons,['*/15 * * * *']);assert.equal(c.queues.consumers[0].max_concurrency,1);
  assert.equal(c.queues.producers[0].queue,'sarsa-booking-recovery');assert.equal(c.account_id,'162c1ab1ba0619c1c78d9495f3260f18');
});

test('independent monitor checks only fixed Cloudflare signal, rejects failure and oversized output',async()=>{
  const {checkRecovery,HEALTH_URL}=await import('./monitor.mjs');
  const calls=[];
  assert.equal(await checkRecovery(async(url,options)=>{
    calls.push(url);assert.equal(options.redirect,'error');return Response.json({status:'healthy'});
  }),true);
  assert.deepEqual(calls,[HEALTH_URL]);
  for(const response of [Response.json({status:'attention'},{status:503}),Response.json({status:'unknown'}),
    Response.json({status:'healthy',private:'unexpected'}),new Response(' '.repeat(300),{headers:{'content-type':'application/json'}})]) {
    await assert.rejects(checkRecovery(async()=>response));
  }
});

test('older sweep completion cannot overwrite the health of a newer failed slot',async()=>{
  const f=fixture(),req=new Request('https://worker.invalid/health');
  f.records.set('sweep:1',{scheduled_at:900_000,completed_at:1_800_000,healthy:true});
  f.records.set('sweep:2',{scheduled_at:1_800_000,completed_at:1_800_000,healthy:false});
  assert.equal((await f.worker.fetch(req,f.env)).status,503);assert.equal(f.calls.length,0);
});


test('contact lanes use their scoped keys and two email events are valid',async()=>{
  const before=idle();before.lanes.contact_email=0;before.lanes.contact_google=0;before.lanes.email_events=0;
  const f=fixture([before,idle()],url=>Response.json({application:APP,processed:url.endsWith('/events')?2:1}));
  f.env.SARSA_EMAIL_WORKER_KEY='e'.repeat(43)+'=';
  f.env.SARSA_GOOGLE_WORKER_KEY='g'.repeat(43)+'=';
  const m=message();await f.worker.queue({messages:[m]},f.env);
  assert.equal(m.acks,1);
  const delivery=f.calls.filter(([url])=>!url.endsWith('/plan'));
  assert.ok(delivery[0][0].endsWith('/contact/email'));
  for(const [url,options] of delivery)assert.equal(options.headers.authorization,'Bearer '+(url.endsWith('/contact/google')?f.env.SARSA_GOOGLE_WORKER_KEY:f.env.SARSA_EMAIL_WORKER_KEY));
});


test('slow operations stop the pass rather than holding later verification indefinitely',async()=>{
  const before=idle();before.lanes.contact_email=0;before.lanes.google=0;
  let f;f=fixture([before],()=>{f.setTime(1_890_000);return Response.json({application:APP,processed:1});});
  const m=message();await f.worker.queue({messages:[m]},f.env);
  assert.equal(m.acks,0);assert.equal(m.retries.length,1);
  assert.equal(f.calls.filter(([url])=>url.endsWith('/google/run')).length,0);
});
