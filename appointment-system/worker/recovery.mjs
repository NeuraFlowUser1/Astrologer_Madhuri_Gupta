// One implementation for every contained project worker. No database credentials.
import {facts} from './installation.mjs';
import {canonical} from './service-state.mjs';
export const LANES=Object.freeze(['verification_email','payment_events','payment','booking_records','email_events',
 'notification_email','enquiry_records','maintenance','control_publication']);
const PERIOD=900000,DEADLINE=90000,HTTP_TIMEOUT=25000;
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const HEX=/^[a-f0-9]{64}$/;
const exact=(value,fields)=>value && typeof value==='object' && !Array.isArray(value)
 && Object.keys(value).sort().join(',')===fields.split(',').sort().join(',');
const count=(value,maximum=10000)=>Number.isSafeInteger(value) && value>=0 && value<=maximum;
const identifier=value=>typeof value==='string' && UUID.test(value) && value!=='00000000-0000-0000-0000-000000000000';
const time=value=>Number.isSafeInteger(value) && value>=0;
const failure=(code,status=503)=>Response.json({code},{status,headers:{'cache-control':'no-store'}});

export function configuration(env) {
 const declared=facts(env);
 if (!HEX.test(env.BOOKING_RELEASE_DIGEST || '')) throw Error('worker_configuration');
 const names=['RECOVERY_WORKER','EMAIL_WORKER','GOOGLE_WORKER','WAKE','MONITOR'];
 const materials=names.map(name=>env['BOOKING_'+name+'_KEY']);
 for (const value of materials) {
  if (typeof value!=='string' || !/^[A-Za-z0-9_-]{43}=$/.test(value)) throw Error('worker_configuration');
  const bytes=Uint8Array.from(atob(value.replaceAll('-','+').replaceAll('_','/')),x=>x.charCodeAt(0));
  if (bytes.length!==32 || btoa(String.fromCharCode(...bytes)).replaceAll('+','-').replaceAll('/','_')!==value) throw Error('worker_configuration');
 }
 for (const name of ['READ','PUBLISH','RECONCILE']) {
  const value=env['BOOKING_CONTROL_'+name+'_KEY'];
  if (value!==undefined) materials.push(value);
 }
 if (new Set(materials).size!==materials.length) throw Error('worker_configuration');
 return {...declared,release_digest:env.BOOKING_RELEASE_DIGEST};
}

function identity(value,expected) {
 return value.contract===1 && value.application===expected.project && value.environment===expected.environment
  && value.installation_id===expected.installation_id && value.release_digest===expected.release_digest
  && value.run_id===expected.run_id && identifier(value.generation);
}

export function checkedPlan(value,expected,now=Date.now()) {
 if (!exact(value,'contract,application,environment,installation_id,generation,release_digest,run_id,evaluated_at,cursor,lanes,attention')
  || !identity(value,expected) || !time(value.evaluated_at) || Math.abs(now-value.evaluated_at)>60000
  || !count(value.cursor,8) || typeof value.attention!=='boolean' || !exact(value.lanes,LANES.join(','))) throw Error('plan_invalid');
 for (const item of Object.values(value.lanes)) {
  if (!exact(item,'remaining_due,next_due_at') || !count(item.remaining_due)
   || !(item.next_due_at===null || time(item.next_due_at))) throw Error('plan_invalid');
 }
 return value;
}

export function checkedAck(value,plan,lane,now=Date.now()) {
 const expected={...plan,project:plan.application};
 if (!exact(value,'contract,application,environment,installation_id,generation,release_digest,run_id,lane,code,evaluated_at,processed,remaining_due,next_due_at,attention')
  || !identity(value,expected) || value.generation!==plan.generation || value.lane!==lane
  || !['evaluated-empty','completed-work','deferred'].includes(value.code) || !count(value.processed,1)
  || value.code==='evaluated-empty' && value.processed!==0 || value.code==='completed-work' && value.processed!==1
  || !time(value.evaluated_at) || value.evaluated_at<plan.evaluated_at || Math.abs(now-value.evaluated_at)>60000
  || !count(value.remaining_due) || !(value.next_due_at===null || time(value.next_due_at))
  || typeof value.attention!=='boolean') throw Error('lane_ack_invalid');
 return value;
}

async function boundedJSON(response,signal) {
 if (response.status!==200 || !response.headers.get('content-type')?.toLowerCase().startsWith('application/json')
  || ![null,'identity'].includes(response.headers.get('content-encoding')) || !response.body) throw Error('worker_response_invalid');
 const reader=response.body.getReader(),decoder=new TextDecoder('utf-8',{fatal:true});let raw='',size=0;
 try {
  while (true) {
   if (signal.aborted) throw Error('worker_deadline');
   const pending=reader.read();
   const chunk=await new Promise((resolve,reject)=>{
    const abort=()=>reject(Error('worker_deadline'));signal.addEventListener('abort',abort,{once:true});
    pending.then(resolve,reject).finally(()=>signal.removeEventListener('abort',abort));
   });
   if (chunk.done) break;size+=chunk.value.byteLength;if(size>32768) throw Error('worker_response_invalid');
   raw+=decoder.decode(chunk.value,{stream:true});
  }
  raw+=decoder.decode();const value=JSON.parse(raw);
  if(raw!==canonical(value)) throw Error('worker_response_invalid');
  return value;
 } finally {await reader.cancel().catch(()=>{});}
}

export function caller(env,{fetcher=fetch,now=Date.now}={}) {
 const declared=configuration(env);
 return async (path,body,purpose='RECOVERY',deadline=now()+HTTP_TIMEOUT)=>{
  const duration=Math.min(HTTP_TIMEOUT,deadline-now());if(duration<=0) throw Error('worker_deadline');
  const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),duration);
  try {
   const response=await fetcher(declared.origin+path,{method:'POST',redirect:'manual',signal:abort.signal,
    headers:{'content-type':'application/json','authorization':'Bearer '+env['BOOKING_'+purpose+'_WORKER_KEY']},body:canonical(body)});
   return await boundedJSON(response,abort.signal);
  } finally {clearTimeout(timer);}
 };
}

export async function execute(env,hint,{fetcher=fetch,now=Date.now,onPlan=()=>{},onAck=()=>{}}={}) {
 const declared=configuration(env),start=now(),deadline=start+DEADLINE,call=caller(env,{fetcher,now});
 const expected={...declared,run_id:hint.run_id};
 const plan=checkedPlan(await call('/api/internal/worker/plan',{run_id:hint.run_id,
  release_digest:declared.release_digest,scheduled_at:hint.scheduled_at},'RECOVERY',deadline),expected,now());
 const acknowledgements={};let interrupted=false;
 onPlan(plan);
 if(Object.values(plan.lanes).every(item=>item.remaining_due===0)) {
  const pending=Object.values(plan.lanes).map(item=>item.next_due_at).filter(time);
  return {plan,acknowledgements,healthy:!plan.attention,remaining_due:0,
   next_due_at:pending.length?Math.min(...pending):null,interrupted:false};
 }
 let final=null;
 try {
  for(let offset=0;offset<LANES.length;offset++) {
   const lane=LANES[(plan.cursor+offset)%LANES.length];
   if(plan.lanes[lane].remaining_due===0) continue;
   if(deadline-now()<HTTP_TIMEOUT+1000) {interrupted=true;break;}
   const purpose=['verification_email','notification_email','email_events'].includes(lane)?'EMAIL'
    :['booking_records','enquiry_records'].includes(lane)?'GOOGLE':'RECOVERY';
   try {
    const ack=checkedAck(await call('/api/internal/worker/'+lane,{run_id:plan.run_id,
     release_digest:plan.release_digest,generation:plan.generation},purpose,deadline),plan,lane,now());
    acknowledgements[lane]=ack;onAck(ack);
   } catch {interrupted=true;}
  }
 } finally {
  if(deadline-now()>1000) {
   try {
    const ended=await call('/api/internal/worker/end',{run_id:plan.run_id,release_digest:plan.release_digest},'RECOVERY',deadline);
    if(!exact(ended,'completed,generation,release_digest,run_id,evaluated_at,lanes,attention') || ended.completed!==true
     || ended.generation!==plan.generation || ended.release_digest!==plan.release_digest || ended.run_id!==plan.run_id
     || !time(ended.evaluated_at) || ended.evaluated_at<plan.evaluated_at || Math.abs(now()-ended.evaluated_at)>60000
     || typeof ended.attention!=='boolean' || !exact(ended.lanes,LANES.join(','))) throw Error('final_progress_invalid');
    for(const item of Object.values(ended.lanes)) {
     if(!exact(item,'remaining_due,next_due_at') || !count(item.remaining_due)
      || !(item.next_due_at===null || time(item.next_due_at))) throw Error('final_progress_invalid');
    }
    final=ended;
   } catch {interrupted=true;}
  } else interrupted=true;
 }
 let healthy=!(final||plan).attention && !interrupted,remaining=0,nextDue=null;
 for(const lane of LANES) {
  const item=final?.lanes[lane] || acknowledgements[lane] || plan.lanes[lane];
  if(plan.lanes[lane].remaining_due>0 && !acknowledgements[lane]) healthy=false;
  if(item.attention===true || item.remaining_due>0) healthy=false;
  remaining=Math.min(10000,remaining+item.remaining_due);
  if(item.next_due_at!==null) nextDue=nextDue===null?item.next_due_at:Math.min(nextDue,item.next_due_at);
 }
 return {plan,acknowledgements,healthy,remaining_due:remaining,next_due_at:nextDue,interrupted};
}

export function checkedHint(hint,env,now=Date.now()) {
 const declared=configuration(env);
 if (!exact(hint,'contract,installation_id,release_digest,run_id,source,scheduled_at,attempt')
  || hint.contract!==1 || hint.installation_id!==declared.installation_id || hint.release_digest!==declared.release_digest
  || !identifier(hint.run_id) || !['scheduled','wake','continue'].includes(hint.source)
  || !time(hint.scheduled_at) || hint.scheduled_at>now+60000 || now-hint.scheduled_at>PERIOD
  || !count(hint.attempt,5)) throw Error('wake_invalid');
 return hint;
}

function hint(env,source,scheduled,attempt=0) {
 const declared=configuration(env);
 return {contract:1,installation_id:declared.installation_id,release_digest:declared.release_digest,
  run_id:crypto.randomUUID(),source,scheduled_at:scheduled,attempt};
}

export class BookingRecoveryState {
 constructor(ctx,env) {
  this.ctx=ctx;this.env=env;
  ctx.storage.sql.exec('CREATE TABLE IF NOT EXISTS recovery_runs(id TEXT PRIMARY KEY,scheduled INTEGER NOT NULL,source TEXT NOT NULL,completed INTEGER,healthy INTEGER NOT NULL DEFAULT 0,details TEXT)');
  ctx.storage.sql.exec('CREATE TABLE IF NOT EXISTS recovery_lease(singleton INTEGER PRIMARY KEY CHECK(singleton=1),id TEXT NOT NULL,until_ms INTEGER NOT NULL)');
 }
 async fetch(request) {
  const path=new URL(request.url).pathname;
  if(path==='/health') {
   const latest=this.ctx.storage.sql.exec("SELECT scheduled,completed,healthy FROM recovery_runs WHERE source='scheduled' ORDER BY scheduled DESC LIMIT 1").toArray()[0];
   const okay=latest && latest.healthy===1 && latest.completed!==null && latest.scheduled<=Date.now()
    && latest.completed<=Date.now() && Date.now()-latest.scheduled<=1200000;
   return Response.json({status:okay?'healthy':'attention'},{status:okay?200:503,headers:{'cache-control':'no-store'}});
  }
  if(path!=='/run' || request.method!=='POST') return failure('not_found',404);
  let work;
  try{work=checkedHint(await request.json(),this.env);}catch{return failure('wake_invalid',400);}
  const admitted=this.ctx.storage.transactionSync(()=>{
   const active=this.ctx.storage.sql.exec('SELECT until_ms FROM recovery_lease WHERE singleton=1').toArray()[0];
   if(active && active.until_ms>Date.now()) return false;
   this.ctx.storage.sql.exec('INSERT INTO recovery_lease VALUES(1,?,?) ON CONFLICT(singleton) DO UPDATE SET id=excluded.id,until_ms=excluded.until_ms',work.run_id,Date.now()+DEADLINE);
   this.ctx.storage.sql.exec('INSERT OR IGNORE INTO recovery_runs(id,scheduled,source) VALUES(?,?,?)',work.run_id,work.scheduled_at,work.source);
   return true;
  });
  if(!admitted) return failure('worker_busy',409);
  let result;
  try {
   result=await execute(this.env,work,{onPlan:plan=>this.save(work,{plan,acknowledgements:{}}),
    onAck:ack=>{
     const row=this.ctx.storage.sql.exec('SELECT details FROM recovery_runs WHERE id=?',work.run_id).toArray()[0];
     const details=JSON.parse(row.details);details.acknowledgements[ack.lane]=ack;this.save(work,details);
    }});
   this.save(work,{plan:result.plan,acknowledgements:result.acknowledgements},result.healthy);
  } catch {
   this.ctx.storage.sql.exec('UPDATE recovery_runs SET completed=?,healthy=0 WHERE id=?',Date.now(),work.run_id);
  } finally {
   this.ctx.storage.sql.exec('DELETE FROM recovery_lease WHERE id=?',work.run_id);
   this.ctx.storage.sql.exec('DELETE FROM recovery_runs WHERE id IN (SELECT id FROM recovery_runs ORDER BY scheduled DESC LIMIT -1 OFFSET 128)');
  }
  const due=result?.next_due_at;
  if(this.env.BOOKING_WAKE_QUEUE && work.attempt<5 && (result===undefined || result.remaining_due>0 || due!==null && due<=Date.now()+PERIOD)) {
   const delay=result===undefined?30:Math.max(15,Math.min(900,Math.ceil(((due??Date.now())-Date.now())/1000)));
   try{await this.env.BOOKING_WAKE_QUEUE.send(hint(this.env,'continue',Date.now(),work.attempt+1),{delaySeconds:delay});}
   catch{/* Durable database work remains; scheduled rescue does not need the hint. */}
  }
  return Response.json({recorded:true},{headers:{'cache-control':'no-store'}});
 }
 save(work,details,healthy=null) {
  this.ctx.storage.sql.exec('UPDATE recovery_runs SET details=?,completed=?,healthy=? WHERE id=?',
   canonical(details),healthy===null?null:Date.now(),healthy===true?1:0,work.run_id);
 }
}

function state(env) {
 const declared=configuration(env);
 if(!env.BOOKING_RECOVERY_STATE) throw Error('worker_configuration');
 return env.BOOKING_RECOVERY_STATE.get(env.BOOKING_RECOVERY_STATE.idFromName('booking-recovery:'+declared.installation_id+':'+declared.environment));
}

export async function recoveryFetch(request,env) {
 const url=new URL(request.url);
 if(!['/wake','/health'].includes(url.pathname)) return null;
 if(url.search) return failure('request_invalid',400);
 try {
  const declared=configuration(env);
  const key=url.pathname==='/wake'?env.BOOKING_WAKE_KEY:env.BOOKING_MONITOR_KEY;
  if(request.headers.get('authorization')!=='Bearer '+key) return failure('unauthorized',401);
  if(url.pathname==='/health' && request.method==='GET') return await state(env).fetch('https://recovery.internal/health');
  if(url.pathname!=='/wake' || request.method!=='POST') return failure('not_found',404);
  if(request.headers.get('content-type')?.split(';')[0].trim()!=='application/json'
   || ![null,'identity'].includes(request.headers.get('content-encoding'))) return failure('request_invalid',415);
  // The external caller can wake saved work but cannot select any customer or lane.
  const bytes=await boundedWakeBody(request);
  if(bytes.trim()!=='{}') return failure('request_invalid',422);
  if(!env.BOOKING_WAKE_QUEUE) return failure('worker_configuration');
  await env.BOOKING_WAKE_QUEUE.send(hint(env,'wake',Date.now()));
  return Response.json({application:declared.project,queued:true},{status:202,headers:{'cache-control':'no-store'}});
 } catch{return failure('worker_unavailable');}
}

async function boundedWakeBody(request) {
 if(!request.body) throw Error('request_invalid');
 const reader=request.body.getReader();let bytes=0,body='';
 const decoder=new TextDecoder('utf-8',{fatal:true});let timer;
 try {
  return await Promise.race([(async()=>{
   while(true) {const chunk=await reader.read();if(chunk.done) break;bytes+=chunk.value.byteLength;
    if(bytes>1024) throw Error('request_invalid');body+=decoder.decode(chunk.value,{stream:true});}
   return body+decoder.decode();
  })(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('request_deadline')),2000);})]);
 } finally {clearTimeout(timer);await reader.cancel().catch(()=>{});}
}

export async function scheduled(controller,env) {
 const now=Date.now();
 if(!time(controller.scheduledTime) || controller.scheduledTime>now || now-controller.scheduledTime>PERIOD) throw Error('stale_schedule');
 const result=await state(env).fetch('https://recovery.internal/run',{method:'POST',headers:{'content-type':'application/json'},
  body:canonical(hint(env,'scheduled',controller.scheduledTime))});
 if(result.status!==200) throw Error('scheduled_run_unavailable');
}

export async function queue(batch,env) {
 for(const message of batch.messages) {
  try {checkedHint(message.body,env);}
  catch {message.ack();continue;/* Invalid hints cannot select work; the durable schedule replans. */}
  try {
   const response=await state(env).fetch('https://recovery.internal/run',{method:'POST',headers:{'content-type':'application/json'},body:canonical(message.body)});
   if(response.status!==200) {message.retry({delaySeconds:30});continue;}
   message.ack();
  } catch {message.retry({delaySeconds:30});}
 }
}
