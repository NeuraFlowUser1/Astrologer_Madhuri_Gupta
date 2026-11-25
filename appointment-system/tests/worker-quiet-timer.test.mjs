// Quiet timer: every decision rule in order, the notebook, marks, hints and health, with a SQLite storage double.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import {PERIOD,GRACE,TOLERANCE,RESCUE,CLAMP,TICK_STALE,DUE_LATE,WAKE_LATE,backoff,usable,known,summarise,failed,merged,
 decide,followUp,healthy,legacyHealthy} from '../worker/quiet-timer.mjs';
import {BookingRecoveryState,LANES,checkedHint,recoveryFetch} from '../worker/recovery.mjs';
import {canonical} from '../worker/service-state.mjs';

const key=n=>Buffer.alloc(32,n).toString('base64url')+'=';
const digest='a'.repeat(64);
const env={BOOKING_INSTALLATION_ID:'891d05ec-8ab2-4a87-b537-1c30f2b694b6',BOOKING_PROJECT_ID:'example-practice',
 BOOKING_ENVIRONMENT:'test',BOOKING_PUBLIC_ORIGIN:'https://practice.example.test',BOOKING_RELEASE_DIGEST:digest,
 BOOKING_RECOVERY_WORKER_KEY:key(21),BOOKING_EMAIL_WORKER_KEY:key(22),BOOKING_GOOGLE_WORKER_KEY:key(23),
 BOOKING_WAKE_KEY:key(24),BOOKING_MONITOR_KEY:key(25)};
const empty=()=>Object.fromEntries(LANES.map(lane=>[lane,{remaining_due:0,next_due_at:null}]));
const quiet=()=>Object.fromEntries(LANES.map(lane=>[lane,{remaining_due:0,next_due_at:null,stall:0,clamp:0}]));
const noMarks={wake_pending_at:null,last_tick_at:null,hint_at:null};
const T=1_800_000_000_000;
const view=(changes={})=>({version:1,release_digest:digest,observed_at:T,run_started_at:T-5000,offset_ms:0,lanes:quiet(),
 attention:false,healthy:true,full_started_at:T-5000,full_at:T,attempt_at:T-5000,failures:0,...changes});
const withLane=(lane,item,changes={})=>{const value=view(changes);value.lanes[lane]={...value.lanes[lane],...item};return value;};

test('constants: twelve-hour rescue lands on the 48th tick and back-off doubles up to the rescue interval',()=>{
 assert.equal(RESCUE,12*3600*1000);
 const completed=T+30000,tick48=T+48*PERIOD;
 assert.ok(tick48-completed>=RESCUE-TOLERANCE);assert.ok(T+47*PERIOD-completed<RESCUE-TOLERANCE);
 assert.deepEqual([0,1,2,3,4,5,6,7,8,40].map(backoff),[PERIOD,PERIOD,2*PERIOD,4*PERIOD,8*PERIOD,16*PERIOD,32*PERIOD,RESCUE,RESCUE,RESCUE]);
 for(const hours of [1,2,3,6,12]){
  const rescue=hours*3600000,ticks=Math.ceil((rescue-TOLERANCE)/PERIOD);assert.equal(ticks*PERIOD>=rescue-TOLERANCE-30000,true);
 }
});

test('decision rules run in their documented order',()=>{
 const now=T+PERIOD;
 assert.deepEqual(decide(null,noMarks,null,now,digest),{run:true,reason:'unknown'});
 assert.deepEqual(decide({version:2},noMarks,null,now,digest),{run:true,reason:'unknown'});
 assert.deepEqual(decide(view(),noMarks,T+1,now,digest),{run:true,reason:'unknown'});
 assert.deepEqual(decide(view(),noMarks,T,now,digest),{run:false,reason:'idle'});
 assert.deepEqual(decide(view({release_digest:'b'.repeat(64)}),noMarks,null,now,digest),{run:true,reason:'release'});
 assert.deepEqual(decide(view(),{...noMarks,wake_pending_at:T-1},null,now,digest),{run:true,reason:'wake_pending'});
 assert.deepEqual(decide(view({full_at:null}),noMarks,null,now,digest),{run:true,reason:'rescue'});
 assert.deepEqual(decide(view(),noMarks,null,T+RESCUE-TOLERANCE,digest),{run:true,reason:'rescue'});
 assert.deepEqual(decide(view(),noMarks,null,T+RESCUE-TOLERANCE-1,digest),{run:false,reason:'idle'});
 // A release change outranks a wake note, and a wake note outranks a failing back-off.
 assert.equal(decide(view({release_digest:'b'.repeat(64),failures:3}),{...noMarks,wake_pending_at:T},null,now,digest).reason,'release');
 assert.equal(decide(view({failures:3}),{...noMarks,wake_pending_at:T},null,now,digest).reason,'wake_pending');
});

test('after a failure the timer retries every tick while known work waits, otherwise on a doubling back-off',()=>{
 const failing=view({failures:2,attempt_at:T});
 assert.deepEqual(decide(failing,noMarks,null,T+PERIOD,digest),{run:false,reason:'failing'});
 assert.deepEqual(decide(failing,noMarks,null,T+backoff(2),digest),{run:true,reason:'retry'});
 const known=withLane('maintenance',{next_due_at:T+86400000},{failures:2,attempt_at:T});
 assert.deepEqual(decide(known,noMarks,null,T+PERIOD,digest),{run:true,reason:'retry'});
 const remaining=withLane('payment',{remaining_due:1,next_due_at:T},{failures:5,attempt_at:T});
 assert.equal(decide(remaining,noMarks,null,T+1,digest).reason,'retry');
 // Stalled work alone does not force a retry on every tick.
 const blocked=withLane('booking_records',{remaining_due:3,next_due_at:T-3600000,stall:2},{failures:1,attempt_at:T});
 assert.equal(decide(blocked,noMarks,null,T+PERIOD-1,digest).reason,'failing');
});

test('remaining and due work run; work due before the next tick gets exactly one hint; later work waits',()=>{
 assert.deepEqual(decide(withLane('payment',{remaining_due:1,next_due_at:T}),noMarks,null,T+1,digest),{run:true,reason:'remaining'});
 assert.deepEqual(decide(withLane('payment',{next_due_at:T+GRACE+10}),noMarks,null,T+10,digest),{run:true,reason:'due'});
 const soon=withLane('notification_email',{next_due_at:T+600000});
 assert.deepEqual(decide(soon,noMarks,null,T,digest),{run:false,reason:'hint',hint_at:T+600000});
 assert.deepEqual(decide(soon,{...noMarks,hint_at:T+600000},null,T,digest),{run:false,reason:'hinted'});
 assert.equal(decide(soon,{...noMarks,hint_at:T-1},null,T,digest).reason,'hint');
 assert.equal(decide(soon,{...noMarks,hint_at:T+600000+GRACE+1},null,T,digest).reason,'hint');
 assert.deepEqual(decide(withLane('payment',{next_due_at:T+5000}),noMarks,null,T-GRACE-1,digest),{run:false,reason:'hint',hint_at:T+5000});
 assert.deepEqual(decide(withLane('maintenance',{next_due_at:T+PERIOD}),noMarks,null,T,digest),{run:false,reason:'idle'});
 // The database clock is corrected by the recorded offset.
 const skewed=withLane('payment',{next_due_at:T+30000+40000},{offset_ms:40000});
 assert.equal(decide(skewed,noMarks,null,T,digest).reason,'due');
});

test('stalled and clamped lanes never count as known due work and are rechecked on their back-off',()=>{
 const blocked=withLane('booking_records',{remaining_due:3,next_due_at:T-36000000,stall:2});
 assert.deepEqual(decide(blocked,noMarks,null,T+PERIOD-1,digest),{run:false,reason:'idle'});
 assert.deepEqual(decide(blocked,noMarks,null,T+PERIOD,digest),{run:true,reason:'held'});
 const later=withLane('booking_records',{remaining_due:3,next_due_at:T,stall:5});
 assert.equal(decide(later,noMarks,null,T+backoff(4)-1,digest).reason,'idle');
 assert.equal(decide(later,noMarks,null,T+backoff(4),digest).reason,'held');
 const idlePublication=withLane('control_publication',{next_due_at:T+900000,clamp:1});
 assert.equal(decide(idlePublication,noMarks,null,T+1,digest).reason,'idle');
 // An idle cap reading is never a reason to wake the database, however long it lasts.
 assert.equal(decide(idlePublication,noMarks,null,T+PERIOD,digest).reason,'idle');
 assert.equal(decide(idlePublication,noMarks,null,T+8*3600000,digest).reason,'idle');
 const steady=withLane('control_publication',{next_due_at:T+900000,clamp:30});
 assert.equal(decide(steady,noMarks,null,T+RESCUE-TOLERANCE-1,digest).reason,'idle');
 // The earliest re-check wins when several lanes are held.
 const both=withLane('control_publication',{next_due_at:T+900000,clamp:30});both.lanes.booking_records={remaining_due:1,next_due_at:T,stall:2,clamp:0};
 assert.equal(decide(both,noMarks,null,T+PERIOD,digest).reason,'held');
 // A clamp reading on any other lane is ordinary due work.
 assert.equal(decide(withLane('payment',{next_due_at:T+600000,clamp:3}),noMarks,null,T,digest).reason,'hint');
 const due=known(both);assert.deepEqual(due,{remaining:false,earliest:null});
});

function result({lanes=empty(),acks={},attempted=[],final=null,healthy=true,evaluated=T}={}) {
 return {plan:{evaluated_at:evaluated,lanes,attention:false},acknowledgements:acks,attempted,final,healthy};
}
const ack=(lane,changes)=>({lane,code:'deferred',processed:0,remaining_due:1,next_due_at:T,evaluated_at:T+100,attention:false,...changes});

test('summaries count stalls only for called lanes without progress, and reset on progress',()=>{
 const options={startedAt:T-2000,now:T+3000,planAt:T-1000,digest};
 const lanes=empty();lanes.booking_records={remaining_due:3,next_due_at:T-50000};
 const first=summarise(null,result({lanes,attempted:['booking_records']}),options);
 assert.equal(first.lanes.booking_records.stall,1);assert.equal(first.offset_ms,1000);assert.equal(first.full_at,T+3000);
 const second=summarise(first,result({lanes,attempted:['booking_records']}),options);
 assert.equal(second.lanes.booking_records.stall,2);
 // A deadline-skipped lane keeps its count; a lane that is no longer due resets.
 assert.equal(summarise(second,result({lanes}),options).lanes.booking_records.stall,2);
 assert.equal(summarise(second,result({attempted:['booking_records']}),options).lanes.booking_records.stall,0);
 // Any processed item is progress, even when the lane deferred.
 const progressed=summarise(second,result({lanes,attempted:['booking_records'],acks:{booking_records:ack('booking_records',{processed:1})}}),options);
 assert.equal(progressed.lanes.booking_records.stall,0);
 // A due time that moved later is progress; one that stayed is not.
 const moved=summarise(first,result({lanes,attempted:['booking_records'],acks:{booking_records:ack('booking_records',{next_due_at:T+60000})}}),options);
 assert.equal(moved.lanes.booking_records.stall,0);
 const stayed=summarise(first,result({lanes,attempted:['booking_records'],acks:{booking_records:ack('booking_records',{next_due_at:T-50000})}}),options);
 assert.equal(stayed.lanes.booking_records.stall,2);
 // One deferred item among several due items, called twice without progress, is stalled; one transient failure is not.
 assert.equal(stalledAfter(1),false);assert.equal(stalledAfter(2),true);
 function stalledAfter(times){let value=null;for(let i=0;i<times;i++)value=summarise(value,result({lanes,attempted:['booking_records']}),options);return value.lanes.booking_records.stall>=2;}
 // The final summary has precedence over acknowledgements and the plan.
 const ended=summarise(null,result({lanes,attempted:['booking_records'],acks:{booking_records:ack('booking_records')},
  final:{evaluated_at:T+500,attention:true,lanes:{...empty(),booking_records:{remaining_due:0,next_due_at:null}}}}),options);
 assert.deepEqual(ended.lanes.booking_records,{remaining_due:0,next_due_at:null,stall:0,clamp:0});assert.equal(ended.attention,true);
 assert.equal(summarise(null,result(),{...options,planAt:null}).offset_ms,0);
 assert.equal(summarise({...first,offset_ms:77},result(),{...options,planAt:null}).offset_ms,77);
});

test('the display-publication cap reading counts as clamped, and a real due time resets it',()=>{
 const options={startedAt:T,now:T+1000,planAt:T,digest};
 const capped=empty();capped.control_publication={remaining_due:0,next_due_at:T+900000};
 const once=summarise(null,result({lanes:capped}),options);assert.equal(once.lanes.control_publication.clamp,1);
 assert.equal(summarise(once,result({lanes:capped}),options).lanes.control_publication.clamp,2);
 const edge=empty();edge.control_publication={remaining_due:0,next_due_at:T+CLAMP-1};
 assert.equal(summarise(once,result({lanes:edge}),options).lanes.control_publication.clamp,0);
 const other=empty();other.payment={remaining_due:0,next_due_at:T+900000};
 assert.equal(summarise(null,result({lanes:other}),options).lanes.payment.clamp,0);
});

test('a run without a final summary, or unhealthy without a reason, is re-checked soon',()=>{
 const options={startedAt:T,now:T+1000,planAt:T,digest};
 assert.equal(summarise(null,{...result(),complete:false},options).recheck,true);
 assert.equal(summarise(null,result(),options).recheck,false);
 assert.equal(summarise(null,result({healthy:false}),options).recheck,true);
 const attention={...result({healthy:false})};attention.plan.attention=true;
 assert.equal(summarise(null,attention,options).recheck,false);
 const lanes=empty();lanes.booking_records={remaining_due:1,next_due_at:T-1};
 const prior=withLane('booking_records',{remaining_due:1,next_due_at:T-1,stall:1});
 assert.equal(summarise(prior,result({lanes,attempted:['booking_records'],healthy:false}),options).recheck,false);
 assert.equal(failed(null,{startedAt:T,now:T,digest}).recheck,false);
 assert.deepEqual(decide(view({recheck:true}),noMarks,null,T+1,digest),{run:true,reason:'recheck'});
 assert.equal(decide(view({recheck:true,failures:1,attempt_at:T}),noMarks,null,T+1,digest).reason,'failing');
});

test('failed runs count failures and keep the last known lanes; an older run never overwrites newer figures',()=>{
 const first=failed(null,{startedAt:T,now:T+1,digest});
 assert.equal(first.failures,1);assert.equal(first.full_at,null);assert.deepEqual(first.lanes,{});assert.equal(usable(first),true);
 const known=withLane('payment',{next_due_at:T+5000});
 const next=failed(known,{startedAt:T+10,now:T+20,digest});
 assert.equal(next.failures,1);assert.equal(next.full_at,T);assert.deepEqual(next.lanes,known.lanes);
 assert.equal(failed({...known,failures:1000},{startedAt:T,now:T,digest}).failures,1000);
 const newer=view({run_started_at:T+100,observed_at:T+200});
 const older=view({run_started_at:T+50,observed_at:T+300,full_at:T+300});
 assert.deepEqual(merged(newer,older),{...newer,observed_at:T+300});
 assert.equal(merged(newer,{...older,run_started_at:T+100}).full_at,T+300);
 assert.equal(merged(null,older),older);
});

test('follow-up hints: quick retries after failure, 15 s while known work remains, one hint for work due soon',()=>{
 assert.deepEqual(followUp(view({failures:1}),0,T,false),{delay:30,attempt:1});
 assert.deepEqual(followUp(view({failures:2}),4,T,false),{delay:60,attempt:5});
 assert.deepEqual(followUp(view({failures:2}),5,T,false),{delay:60,attempt:5});
 assert.equal(followUp(view({failures:3}),0,T,false),null);
 assert.deepEqual(followUp(withLane('payment',{remaining_due:1,next_due_at:T}),0,T,true),{delay:15,attempt:1});
 assert.equal(followUp(withLane('payment',{remaining_due:1,next_due_at:T}),5,T,true),null);
 assert.deepEqual(followUp(withLane('payment',{next_due_at:T+600000}),1,T,true),{delay:600,attempt:2});
 assert.deepEqual(followUp(withLane('payment',{next_due_at:T+2000}),1,T,true),{delay:15,attempt:2});
 assert.equal(followUp(withLane('payment',{next_due_at:T+PERIOD+1}),1,T,true),null);
 // The five-in-a-row cap applies to the 15-second chain only; a hint for a real due time is never capped.
 assert.deepEqual(followUp(withLane('payment',{next_due_at:T+120000}),5,T,true),{delay:120,attempt:5});
 // A retry that always comes back within a minute (a failing publication probe) cannot chain forever.
 assert.equal(followUp(withLane('control_publication',{next_due_at:T+15000}),5,T,true),null);
 assert.deepEqual(followUp(withLane('control_publication',{next_due_at:T+15000}),4,T,true),{delay:15,attempt:5});
 assert.deepEqual(followUp(withLane('payment',{next_due_at:T+GRACE+1000}),5,T,true),{delay:61,attempt:5});
 assert.deepEqual(followUp(view({recheck:true}),0,T,true),{delay:15,attempt:1});
 assert.equal(followUp(view({recheck:true}),5,T,true),null);
 assert.equal(followUp(withLane('booking_records',{remaining_due:2,next_due_at:T,stall:2}),0,T,true),null);
 assert.equal(followUp(withLane('control_publication',{next_due_at:T+900000,clamp:1}),0,T,true),null);
});

test('health: legacy rule without a usable notebook; the quiet rule with one',()=>{
 const legacy={scheduled:T-60000,completed:T-30000,healthy:1};
 assert.equal(legacyHealthy(legacy,T),true);assert.equal(legacyHealthy(undefined,T),false);
 assert.equal(legacyHealthy({...legacy,healthy:0},T),false);assert.equal(legacyHealthy({...legacy,scheduled:T-TICK_STALE-1},T),false);
 assert.equal(legacyHealthy({...legacy,completed:null},T),false);assert.equal(legacyHealthy({...legacy,scheduled:T+1},T),false);
 assert.equal(legacyHealthy({...legacy,completed:T+1},T),false);
 assert.equal(healthy(null,noMarks,null,legacy,T),true);
 assert.equal(healthy(view(),noMarks,T+1,legacy,T+2),true);
 const marks={...noMarks,last_tick_at:T};
 assert.equal(healthy(view(),marks,null,undefined,T+1000),true);
 assert.equal(healthy(view(),{...marks,last_tick_at:null},null,undefined,T+1000),false);
 // Before the first tick of new code (a wake run came first) the old rule still answers.
 assert.equal(healthy(view(),{...marks,last_tick_at:null},null,{scheduled:T-60000,completed:T-30000,healthy:1},T),true);
 assert.equal(healthy(view(),{...marks,last_tick_at:T-TICK_STALE-1},null,undefined,T),false);
 assert.equal(healthy(view({full_at:null}),marks,null,undefined,T),false);
 assert.equal(healthy(view({full_at:T-RESCUE-TICK_STALE-1}),marks,null,undefined,T),false);
 assert.equal(healthy(view({full_at:T-RESCUE-TICK_STALE}),marks,null,undefined,T),true);
 assert.equal(healthy(view({healthy:false}),marks,null,undefined,T),false);
 assert.equal(healthy(view({failures:1}),marks,null,undefined,T),false);
 assert.equal(healthy(withLane('booking_records',{remaining_due:1,next_due_at:T,stall:2}),marks,null,undefined,T),false);
 assert.equal(healthy(withLane('control_publication',{next_due_at:T+900000,clamp:9}),{...marks,last_tick_at:T+3*PERIOD},null,undefined,T+3*PERIOD),true);
 const late=withLane('payment',{next_due_at:T+60000});
 assert.equal(healthy(late,{...marks,last_tick_at:T+60000+DUE_LATE+1},null,undefined,T+60000+DUE_LATE),true);
 assert.equal(healthy(late,{...marks,last_tick_at:T+60000+DUE_LATE+1},null,undefined,T+60000+DUE_LATE+1),false);
 assert.equal(healthy(withLane('payment',{next_due_at:T-1}),{...marks,last_tick_at:T+DUE_LATE+10},null,undefined,T+DUE_LATE+10),true);
 assert.equal(healthy(view(),{...marks,wake_pending_at:T},null,undefined,T+WAKE_LATE),true);
 assert.equal(healthy(view(),{...marks,last_tick_at:T+WAKE_LATE,wake_pending_at:T},null,undefined,T+WAKE_LATE+1),false);
});

// ---- The Durable Object with a SQLite storage double and a scripted website ----
function storage() {
 const db=new DatabaseSync(':memory:');
 return {db,sql:{exec(query,...values){
  const statement=db.prepare(query);
  if(/^\s*SELECT/i.test(query)) {const rows=statement.all(...values).map(row=>({...row}));return {toArray:()=>rows};}
  statement.run(...values);return {toArray:()=>[]};
 }},transactionSync(callback){db.exec('BEGIN');try{const value=callback();db.exec('COMMIT');return value;}catch(error){db.exec('ROLLBACK');throw error;}}};
}
const generation=randomUUID();
function website(script={}) {
 const site={calls:[],lanes:script.lanes || (()=>empty()),fail:script.fail || (()=>false),lane:script.lane || (()=>null)};
 site.ended=script.ended || site.lanes;
 site.fetch=async(url,options)=>{
  const path=new URL(url).pathname,body=JSON.parse(options.body);site.calls.push(path);
  if(site.fail(path)) return new Response('{}',{status:503,headers:{'content-type':'application/json'}});
  const base={contract:1,application:env.BOOKING_PROJECT_ID,environment:env.BOOKING_ENVIRONMENT,installation_id:env.BOOKING_INSTALLATION_ID,
   generation,release_digest:digest,run_id:body.run_id,evaluated_at:Date.now()};
  let value;
  if(path.endsWith('/plan')) value={...base,cursor:0,lanes:site.lanes(),attention:false};
  else if(path.endsWith('/end')) value={completed:true,generation,release_digest:digest,run_id:body.run_id,evaluated_at:Date.now(),lanes:site.ended(),attention:false};
  else {const lane=path.split('/').at(-1);value=site.lane(lane,base) || {...base,lane,code:'completed-work',processed:1,remaining_due:0,next_due_at:null,attention:false};}
  return new Response(canonical(value),{headers:{'content-type':'application/json'}});
 };
 return site;
}
function object(site,{queue=true,sendFails=false}={}) {
 const sent=[],store=storage();
 const bound={...env,BOOKING_WAKE_QUEUE:queue?{send:async(body,options)=>{if(sendFails)throw Error('synthetic queue failure');sent.push({body,options});}}:undefined};
 const instance=new BookingRecoveryState({storage:store},bound);
 return {instance,store,sent,site,
  async call(path,body){
   const saved=globalThis.fetch;globalThis.fetch=site.fetch;
   try {return await instance.fetch(new Request('https://recovery.internal'+path,{method:'POST',headers:{'content-type':'application/json'},body:body===undefined?undefined:canonical(body)}));}
   finally {globalThis.fetch=saved;}
  },
  tick(at=Date.now()){return this.call('/tick',{contract:1,installation_id:env.BOOKING_INSTALLATION_ID,release_digest:digest,run_id:randomUUID(),source:'scheduled',scheduled_at:at,attempt:0});},
  run(source='wake',attempt=0,at=Date.now()){return this.call('/run',{contract:1,installation_id:env.BOOKING_INSTALLATION_ID,release_digest:digest,run_id:randomUUID(),source,scheduled_at:at,attempt});},
  async health(){return (await instance.fetch(new Request('https://recovery.internal/health'))).status;},
  view(){return instance.view();},marks(){return instance.marks();},
  edit(change){const value={...instance.view(),...change};store.sql.exec('UPDATE recovery_view SET view=?',JSON.stringify(value));}};
}
const quietLog=async callback=>{const saved=console.log;console.log=()=>{};try{return await callback();}finally{console.log=saved;}};

test('the first tick runs once; an idle tick then makes zero website calls and health stays healthy',()=>quietLog(async()=>{
 const o=object(website());
 assert.equal(await o.health(),503);
 assert.equal((await o.tick()).status,200);assert.deepEqual(o.site.calls,['/api/internal/worker/plan']);
 assert.equal(await o.health(),200);assert.equal(o.view().failures,0);
 for(let i=0;i<3;i++) await o.tick();
 assert.equal(o.site.calls.length,1);assert.equal(await o.health(),200);assert.equal(o.sent.length,0);
 assert.equal((await o.call('/unknown',{})).status,404);
 assert.equal((await o.call('/tick',{...o.marks(),bad:true})).status,400);
 assert.equal((await o.call('/tick',{contract:1,installation_id:env.BOOKING_INSTALLATION_ID,release_digest:digest,run_id:randomUUID(),source:'wake',scheduled_at:Date.now(),attempt:0})).status,400);
}));

test('work due in ten minutes gets one hint carrying its delivery time, which is accepted on arrival',()=>quietLog(async()=>{
 const lanes=empty();
 const o=object(website({lanes:()=>lanes}));
 await o.tick();lanes.notification_email={remaining_due:0,next_due_at:Date.now()+600000};
 o.edit({lanes:{...o.view().lanes,notification_email:{remaining_due:0,next_due_at:Date.now()+600000,stall:0,clamp:0}}});
 const before=o.site.calls.length,start=Date.now();await o.tick();
 assert.equal(o.site.calls.length,before);assert.equal(o.sent.length,1);
 const {body,options}=o.sent[0];
 assert.ok(options.delaySeconds>=599 && options.delaySeconds<=601,String(options.delaySeconds));assert.equal(body.source,'continue');assert.equal(body.attempt,0);
 assert.ok(Math.abs(body.scheduled_at-(start+options.delaySeconds*1000))<1000);assert.equal(o.marks().hint_at,body.scheduled_at);
 assert.equal(checkedHint(body,env,body.scheduled_at+5000),body);
 assert.throws(()=>checkedHint({...body,scheduled_at:start},env,start+900500));
 await o.tick();assert.equal(o.sent.length,1);
 // A run clears the stored hint; a lost queue send stores none.
 await o.run('continue',1);assert.equal(o.marks().hint_at===null || o.marks().hint_at>Date.now(),true);
 const lost=object(website({lanes:()=>lanes}),{sendFails:true});await lost.tick();
 lost.edit({lanes:{...lost.view().lanes,notification_email:{remaining_due:0,next_due_at:Date.now()+600000,stall:0,clamp:0}}});
 await lost.tick();assert.equal(lost.marks().hint_at,null);
 const none=object(website({lanes:()=>lanes}),{queue:false});await none.tick();await none.tick();assert.equal(none.marks().hint_at,null);
}));

test('the rescue runs after twelve hours and resets after any full run',()=>quietLog(async()=>{
 const o=object(website());await o.tick();
 o.edit({full_at:Date.now()-RESCUE+TOLERANCE-1000});await o.tick();assert.equal(o.site.calls.length,2);
 assert.ok(Date.now()-o.view().full_at<5000);await o.tick();assert.equal(o.site.calls.length,2);
 o.edit({full_at:Date.now()-RESCUE});await o.run('wake');assert.equal(o.site.calls.length,3);
 await o.tick();assert.equal(o.site.calls.length,3);
}));

test('failures turn health to attention at once, retry at 30 s and 60 s, then follow the tick rules',()=>quietLog(async()=>{
 let down=false;const o=object(website({fail:path=>down && path.endsWith('/plan')}));
 await o.tick();assert.equal(await o.health(),200);
 down=true;await o.run('wake',3);
 assert.equal(await o.health(),503);assert.equal(o.view().failures,1);assert.deepEqual(o.sent.at(-1).options,{delaySeconds:30});
 assert.equal(o.sent.at(-1).body.attempt,4);
 await o.run('continue',4);assert.deepEqual(o.sent.at(-1).options,{delaySeconds:60});assert.equal(o.sent.at(-1).body.attempt,5);
 await o.run('continue',5);assert.equal(o.sent.length,2);assert.equal(o.view().failures,3);
 const calls=o.site.calls.length;await o.tick();assert.equal(o.site.calls.length,calls);
 o.edit({attempt_at:Date.now()-backoff(3)});await o.tick();assert.equal(o.site.calls.length,calls+1);
 down=false;o.edit({attempt_at:0});await o.tick();assert.equal(o.view().failures,0);assert.equal(await o.health(),200);
}));

test('wake notes: written before queuing, run by the next tick if the message is lost, cleared only by a later run',()=>quietLog(async()=>{
 const o=object(website());await o.tick();
 const order=[];
 const binding={idFromName:()=> 'one',get:()=>({fetch:async(url,options)=>{order.push('note');return o.instance.fetch(new Request(url,options));}})};
 const request=()=>new Request('https://worker.example.test/wake',{method:'POST',headers:{'content-type':'application/json',authorization:'Bearer '+key(24)},body:'{}'});
 const lostQueue={send:async()=>{order.push('queue');}};
 assert.equal((await recoveryFetch(request(),{...env,BOOKING_RECOVERY_STATE:binding,BOOKING_WAKE_QUEUE:lostQueue})).status,202);
 assert.deepEqual(order,['note','queue']);const noted=o.marks().wake_pending_at;assert.ok(noted>0);
 const calls=o.site.calls.length;await o.tick();assert.equal(o.site.calls.length,calls+1);assert.equal(o.marks().wake_pending_at,null);
 await o.tick();assert.equal(o.site.calls.length,calls+1);
 // A note that arrives after a run started stays for the next tick.
 await o.call('/wake-note');const later=o.marks().wake_pending_at;
 o.instance.mark('wake_pending_at',Date.now()+60000);await o.run('wake');assert.ok(o.marks().wake_pending_at>Date.now());
 o.instance.mark('wake_pending_at',later);await o.run('wake');assert.equal(o.marks().wake_pending_at,null);
 // A failed run never clears the note.
 const failing=object(website({fail:path=>path.endsWith('/plan')}));await failing.call('/wake-note');await failing.run('wake');
 assert.notEqual(failing.marks().wake_pending_at,null);
 await failing.call('/wake-note');assert.ok(failing.marks().wake_pending_at>0);
 assert.throws(()=>failing.instance.mark('view',1),/mark_invalid/);
}));

test('a run by older code after a rollback makes the next tick treat the notebook as unknown',()=>quietLog(async()=>{
 const o=object(website());await o.tick();await o.tick();assert.equal(o.site.calls.length,1);
 o.store.sql.exec("INSERT INTO recovery_runs(id,scheduled,source,completed,healthy) VALUES(?,?,?,?,1)",randomUUID(),Date.now(),'scheduled',o.view().observed_at+1);
 await o.tick();assert.equal(o.site.calls.length,2);
 o.store.sql.exec('UPDATE recovery_view SET view=?','not json');assert.equal(o.view(),null);await o.tick();assert.equal(o.site.calls.length,3);
}));

test('blocked lanes stall after two called turns: no 15-second chain, attention, and back-off re-checks',()=>quietLog(async()=>{
 const lanes=empty();lanes.booking_records={remaining_due:3,next_due_at:Date.now()-3600000};
 const o=object(website({lanes:()=>lanes,fail:path=>path.endsWith('/booking_records')}));
 await o.tick();assert.equal(o.view().lanes.booking_records.stall,1);assert.equal(o.sent.length,1);assert.equal(o.sent[0].options.delaySeconds,15);
 await o.run('continue',1);assert.equal(o.view().lanes.booking_records.stall,2);assert.equal(o.sent.length,1);
 assert.equal(await o.health(),503);
 const calls=o.site.calls.length;await o.tick();assert.equal(o.site.calls.length,calls);
 o.edit({full_at:Date.now()-PERIOD});await o.tick();assert.ok(o.site.calls.length>calls);assert.equal(o.view().lanes.booking_records.stall,3);
 // Once the lane works again it resets and health recovers.
 lanes.booking_records={remaining_due:0,next_due_at:null};o.edit({full_at:Date.now()-RESCUE});await o.tick();
 assert.equal(o.view().lanes.booking_records.stall,0);assert.equal(await o.health(),200);
}));

test('the idle display-publication cap never keeps the timer awake and never turns health red',()=>quietLog(async()=>{
 const lanes=()=>({...empty(),control_publication:{remaining_due:0,next_due_at:Date.now()+900000}});
 const o=object(website({lanes}));await o.tick();
 assert.equal(o.view().lanes.control_publication.clamp,1);assert.equal(o.sent.length,0);
 const calls=o.site.calls.length;await o.tick();assert.equal(o.site.calls.length,calls);assert.equal(o.sent.length,0);
 o.instance.mark('last_tick_at',Date.now());o.edit({full_at:Date.now()-2*PERIOD});
 assert.equal(await o.health(),200);
}));

test('work created in another lane by a run whose final summary failed is found within seconds',()=>quietLog(async()=>{
 const lanes=empty();lanes.payment={remaining_due:1,next_due_at:Date.now()-1000};let endFails=true;
 const o=object(website({lanes:()=>lanes,fail:path=>endFails && path.endsWith('/end'),
  lane:(lane,base)=>lane==='payment'?{...base,lane,code:'completed-work',processed:1,remaining_due:0,next_due_at:null,attention:false}:null}));
 await o.tick();
 assert.equal(o.view().recheck,true);assert.equal(o.sent.length,1);assert.equal(o.sent[0].options.delaySeconds,15);
 // Even if that hint is lost, the next tick runs; with a final summary the notebook is trusted again.
 lanes.payment={remaining_due:0,next_due_at:null};lanes.notification_email={remaining_due:1,next_due_at:Date.now()-500};endFails=false;
 const calls=o.site.calls.length;await o.tick();assert.ok(o.site.calls.length>calls);
 assert.ok(o.site.calls.includes('/api/internal/worker/notification_email'));
 lanes.notification_email={remaining_due:0,next_due_at:null};await o.run('continue',1);
 assert.equal(o.view().recheck,false);assert.equal(await o.health(),200);
}));

test('a lane call that timed out after the website did the work does not leave health red for hours',()=>quietLog(async()=>{
 const lanes=empty();lanes.notification_email={remaining_due:1,next_due_at:Date.now()-1000};let laneFails=true;
 const o=object(website({lanes:()=>laneFails?lanes:empty(),ended:()=>empty(),fail:path=>laneFails && path.endsWith('/notification_email')}));
 await o.tick();assert.equal(await o.health(),503);
 // The final summary shows nothing left, yet the run was unhealthy: a 15-second re-check, and the tick runs too.
 assert.equal(o.view().recheck,true);assert.equal(o.sent.length,1);assert.equal(o.sent[0].options.delaySeconds,15);
 laneFails=false;const calls=o.site.calls.length;await o.tick();assert.ok(o.site.calls.length>calls);
 assert.equal(await o.health(),200);assert.equal(o.view().recheck,false);
 const after=o.site.calls.length;await o.tick();assert.equal(o.site.calls.length,after);
}));

test('a busy lease keeps the tick quiet, and a run is refused while another holds the lease',()=>quietLog(async()=>{
 const o=object(website());await o.tick();
 o.store.sql.exec('INSERT INTO recovery_lease VALUES(1,?,?)',randomUUID(),Date.now()+60000);
 o.edit({full_at:0});const calls=o.site.calls.length;await o.tick();assert.equal(o.site.calls.length,calls);
 assert.equal((await o.run('wake')).status,409);
}));
