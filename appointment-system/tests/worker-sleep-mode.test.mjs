// Sleep mode while booking is OFF: the pure rules, health while resting, and the recovery object reading the worker's
// own signed ON/OFF copy (a storage double and a scripted website; no Neon, no network).
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import {PERIOD,GRACE,TOLERANCE,RESCUE,TICK_STALE,DORMANT_CHECK,DRAIN_MARGIN,decide,resting,drained,healthy} from '../worker/quiet-timer.mjs';
import {BookingRecoveryState,LANES} from '../worker/recovery.mjs';
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
const T=1_800_000_000_000,HOUR=3600000,DAY=24*HOUR;
// OFF was published at T; the last full run started after the margin, so the site is drained.
const OFF=T,off=(published=OFF)=>({idle:true,pending:false,published_at_ms:published});
const on=(published=OFF)=>({idle:false,pending:false,published_at_ms:published});
const view=(changes={})=>({version:1,release_digest:digest,observed_at:T+DRAIN_MARGIN+5000,run_started_at:T+DRAIN_MARGIN,offset_ms:0,
 lanes:quiet(),attention:false,healthy:true,recheck:false,full_started_at:T+DRAIN_MARGIN,full_at:T+DRAIN_MARGIN+5000,
 attempt_at:T+DRAIN_MARGIN,failures:0,...changes});
const withLane=(lane,item,changes={})=>{const value=view(changes);value.lanes[lane]={...value.lanes[lane],...item};return value;};
const F=T+DRAIN_MARGIN+5000; // the last full look

test('constants: a weekly safety check and a drain margin above the 120 s function limit',()=>{
 assert.equal(DORMANT_CHECK,7*DAY);assert.equal(DRAIN_MARGIN,150000);assert.ok(DRAIN_MARGIN>120000+20000);
 // The weekly check lands on a quarter-hour tick before health would turn red.
 // Worst case: the threshold falls just after a tick, so the check runs one full period later. That is still
 // inside the week-long health allowance.
 assert.ok(DORMANT_CHECK-TOLERANCE+PERIOD<=DORMANT_CHECK+TICK_STALE);
});

test('resting needs a settled OFF copy, a drain after the margin and a clean last run',()=>{
 assert.equal(resting(view(),off(),noMarks),true);
 assert.equal(drained(view(),off()),true);
 for(const state of [null,undefined,on(),{...off(),pending:true},{...off(),published_at_ms:null},{...off(),published_at_ms:'1'},
  {...off(),published_at_ms:-1},{...off(),idle:'true'},'off'])
  assert.equal(resting(view(),state,noMarks),false,JSON.stringify(state));
 // A run that started inside the margin does not count as the drain.
 assert.equal(resting(view({full_started_at:T+DRAIN_MARGIN-1}),off(),noMarks),false);
 assert.equal(resting(view({full_started_at:null}),off(),noMarks),false);
 for(const changes of [{failures:1},{healthy:false},{attention:true},{recheck:true},{full_at:null},{version:2}])
  assert.equal(resting(view(changes),off(),noMarks),false,JSON.stringify(changes));
 assert.equal(resting(view(),off(),{...noMarks,wake_pending_at:T}),false);
 assert.equal(resting(withLane('booking_records',{remaining_due:3,next_due_at:T,stall:2}),off(),noMarks),false);
 assert.equal(resting(withLane('payment',{remaining_due:1,next_due_at:T}),off(),noMarks),false);
 // Known future work and the idle publication cap reading do not prevent rest.
 assert.equal(resting(withLane('maintenance',{next_due_at:T+2*DAY}),off(),noMarks),true);
 assert.equal(resting(withLane('control_publication',{next_due_at:F+900000,clamp:4}),off(),noMarks),true);
});

test('without a readable copy every decision is exactly today\'s',()=>{
 const old=view({full_at:F-13*HOUR});
 for(const state of [undefined,null,on(),{...off(),pending:true},{idle:true}]) {
  assert.deepEqual(decide(old,noMarks,null,F,digest,state),{run:true,reason:'rescue'});
  assert.deepEqual(decide(view(),noMarks,null,F+PERIOD,digest,state),{run:false,reason:'idle'});
 }
});

test('the drain: never inside the margin, exactly once after it, and never while failing',()=>{
 // The ring run right after OFF started one second later; inside the margin today's rules apply.
 const ring=view({full_started_at:OFF+1000,run_started_at:OFF+1000,attempt_at:OFF+1000,full_at:OFF+2000,observed_at:OFF+2000});
 assert.deepEqual(decide(ring,noMarks,null,OFF+DRAIN_MARGIN-1,digest,off()),{run:false,reason:'idle'});
 assert.deepEqual(decide(ring,noMarks,null,OFF+DRAIN_MARGIN,digest,off()),{run:true,reason:'drain'});
 assert.deepEqual(decide(ring,noMarks,null,OFF+5*DAY,digest,off()),{run:true,reason:'drain'});
 // Once a run started after the margin has completed, the site rests.
 assert.deepEqual(decide(view(),noMarks,null,F+PERIOD,digest,off()),{run:false,reason:'dormant',rest:true});
 // A failing site is not drained by a loop: today's failure rules decide until a run succeeds.
 assert.deepEqual(decide({...ring,failures:1,attempt_at:OFF+DRAIN_MARGIN},noMarks,null,OFF+DRAIN_MARGIN+PERIOD-1,digest,off()),{run:false,reason:'failing'});
 assert.equal(decide({...ring,failures:1,full_at:OFF-13*HOUR},noMarks,null,OFF+DRAIN_MARGIN+PERIOD,digest,off()).reason,'rescue');
 // Release, wake note and unknown notebook outrank the drain.
 assert.equal(decide({...ring,release_digest:'b'.repeat(64)},noMarks,null,OFF+DRAIN_MARGIN,digest,off()).reason,'release');
 assert.equal(decide(ring,{...noMarks,wake_pending_at:OFF},null,OFF+DRAIN_MARGIN,digest,off()).reason,'wake_pending');
 assert.equal(decide(ring,noMarks,OFF+3000,OFF+DRAIN_MARGIN,digest,off()).reason,'unknown');
});

test('work committed after a run that started inside the margin is caught by the drain',()=>{
 // The ring run found nothing; a request admitted before OFF then saved emails without a ring.
 const ring=view({full_started_at:OFF+1000,full_at:OFF+2000,observed_at:OFF+2000,run_started_at:OFF+1000,attempt_at:OFF+1000});
 assert.equal(decide(ring,noMarks,null,OFF+DRAIN_MARGIN+PERIOD,digest,off()).reason,'drain');
 // The drain run sees the owed work, so the site does not rest; today's rules finish it.
 const owed=withLane('notification_email',{remaining_due:2,next_due_at:OFF+DRAIN_MARGIN},{});
 assert.equal(resting(owed,off(),noMarks),false);
 assert.deepEqual(decide(owed,noMarks,null,F+1,digest,off()),{run:true,reason:'remaining'});
});

test('clock difference between the two objects: the margin absorbs a second either way',()=>{
 // The product clock one second ahead: a run that started 149 s after the recovery clock saw OFF is not the drain.
 const ahead=off(OFF+1000);
 assert.equal(drained(view({full_started_at:OFF+DRAIN_MARGIN+500}),ahead),false);
 assert.equal(decide(view({full_started_at:OFF+DRAIN_MARGIN+500}),noMarks,null,OFF+DRAIN_MARGIN+999,digest,ahead).reason,'idle');
 assert.equal(decide(view({full_started_at:OFF+DRAIN_MARGIN+500}),noMarks,null,OFF+DRAIN_MARGIN+1000,digest,ahead).reason,'drain');
 // One second behind: the boundary run counts.
 const behind=off(OFF-1000);
 assert.equal(drained(view({full_started_at:OFF+DRAIN_MARGIN-1000}),behind),true);
 assert.equal(drained(view({full_started_at:OFF+DRAIN_MARGIN-1001}),behind),false);
});

test('while resting: due work runs on time, near work gets one hint, and the weekly check runs',()=>{
 assert.deepEqual(decide(withLane('maintenance',{next_due_at:F+DAY}),noMarks,null,F+DAY-GRACE,digest,off()),{run:true,reason:'due',rest:true});
 const soon=withLane('notification_email',{next_due_at:F+DAY+600000});
 assert.deepEqual(decide(soon,noMarks,null,F+DAY,digest,off()),{run:false,reason:'hint',hint_at:F+DAY+600000,rest:true});
 assert.deepEqual(decide(soon,{...noMarks,hint_at:F+DAY+600000},null,F+DAY,digest,off()),{run:false,reason:'hinted',rest:true});
 assert.deepEqual(decide(withLane('maintenance',{next_due_at:F+3*DAY}),noMarks,null,F+DAY,digest,off()),{run:false,reason:'dormant',rest:true});
 // No twelve-hour safety check while resting; the weekly check instead.
 assert.equal(decide(view(),noMarks,null,F+RESCUE,digest,off()).reason,'dormant');
 assert.equal(decide(view(),noMarks,null,F+DORMANT_CHECK-TOLERANCE-1,digest,off()).reason,'dormant');
 assert.deepEqual(decide(view(),noMarks,null,F+DORMANT_CHECK-TOLERANCE,digest,off()),{run:true,reason:'dormant_check',rest:true});
 // Due work outranks the weekly check; a stuck lane ends rest and its back-off applies.
 assert.equal(decide(withLane('payment',{next_due_at:F+DORMANT_CHECK}),noMarks,null,F+DORMANT_CHECK,digest,off()).reason,'due');
 assert.equal(decide(withLane('booking_records',{remaining_due:1,next_due_at:F,stall:2}),noMarks,null,F+PERIOD,digest,off()).reason,'held');
});

test('leaving rest: ON, a failed weekly check or an unreadable copy brings back today\'s rescue at once',()=>{
 const slept=view({full_at:F-6*DAY});
 assert.equal(decide(slept,noMarks,null,F,digest,off()).reason,'dormant');
 assert.deepEqual(decide(slept,noMarks,null,F,digest,on(F-60000)),{run:true,reason:'rescue'});
 assert.deepEqual(decide(slept,noMarks,null,F,digest,null),{run:true,reason:'rescue'});
 assert.deepEqual(decide(slept,noMarks,null,F,digest,{...off(),pending:true}),{run:true,reason:'rescue'});
 const failedCheck={...slept,failures:1,healthy:false,attention:true,attempt_at:F-1000};
 assert.deepEqual(decide(failedCheck,noMarks,null,F+PERIOD,digest,off()),{run:true,reason:'rescue'});
 // A new OFF copy (OFF, ON, OFF again) needs a new drain.
 assert.equal(decide(view(),noMarks,null,F+DRAIN_MARGIN-1,digest,off(F)).reason,'idle');
 assert.equal(decide(view(),noMarks,null,F+DRAIN_MARGIN,digest,off(F)).reason,'drain');
});

test('health while resting allows a week-old full look, never a failure, and ends with the next completed run',()=>{
 const marks={...noMarks,last_tick_at:F+23*HOUR};
 assert.equal(healthy(view(),marks,null,undefined,F+23*HOUR,F+23*HOUR),true);
 assert.equal(healthy(view(),marks,null,undefined,F+23*HOUR,null),false);
 assert.equal(healthy(view(),{...marks,last_tick_at:F+13*HOUR},null,undefined,F+13*HOUR),false);
 const at=F+DORMANT_CHECK+TICK_STALE,late={...marks,last_tick_at:at};
 assert.equal(healthy(view(),late,null,undefined,at,at-PERIOD),true);
 assert.equal(healthy(view(),late,null,undefined,at+1,at-PERIOD),false);
 assert.equal(healthy(view({failures:1}),marks,null,undefined,F+HOUR,F+HOUR),false);
 assert.equal(healthy(view({healthy:false}),marks,null,undefined,F+HOUR,F+HOUR),false);
 assert.equal(healthy(view(),{...marks,last_tick_at:F},null,undefined,F+TICK_STALE+1,F),false);
 // A non-numeric mark is ignored.
 assert.equal(healthy(view(),marks,null,undefined,F+23*HOUR,'x'),false);
});

// ---- The recovery object with a storage double, a scripted website and a scripted product-state object ----
function storage(db=new DatabaseSync(':memory:')) {
 return {db,sql:{exec(query,...values){
  const statement=db.prepare(query);
  if(/^\s*SELECT/i.test(query)) {const rows=statement.all(...values).map(row=>({...row}));return {toArray:()=>rows};}
  statement.run(...values);return {toArray:()=>[]};
 }},transactionSync(callback){db.exec('BEGIN');try{const value=callback();db.exec('COMMIT');return value;}catch(error){db.exec('ROLLBACK');throw error;}}};
}
const generation=randomUUID();
function website(script={}) {
 const site={calls:[],lanes:script.lanes || (()=>empty()),fail:script.fail || (()=>false)};
 site.fetch=async(url,options)=>{
  const path=new URL(url).pathname,body=JSON.parse(options.body);site.calls.push(path);
  if(site.fail(path)) return new Response('{}',{status:503,headers:{'content-type':'application/json'}});
  const base={contract:1,application:env.BOOKING_PROJECT_ID,environment:env.BOOKING_ENVIRONMENT,installation_id:env.BOOKING_INSTALLATION_ID,
   generation,release_digest:digest,run_id:body.run_id,evaluated_at:Date.now()};
  let value;
  if(path.endsWith('/plan')) value={...base,cursor:0,lanes:site.lanes(),attention:false};
  else if(path.endsWith('/end')) value={completed:true,generation,release_digest:digest,run_id:body.run_id,evaluated_at:Date.now(),lanes:site.lanes(),attention:false};
  else {const lane=path.split('/').at(-1);value={...base,lane,code:'completed-work',processed:1,remaining_due:0,next_due_at:null,attention:false};}
  return new Response(canonical(value),{headers:{'content-type':'application/json'}});
 };
 return site;
}
// The product-state double answers what the worker's own copy would; reads are counted.
function productBinding(answer) {
 const binding={reads:0,names:[],urls:[],idFromName(name){binding.names.push(name);return name;},
  get:()=>({fetch:async url=>{binding.reads++;binding.urls.push(String(url));return answer();}})};
 return binding;
}
function object(site,{product,db}={}) {
 const sent=[],store=storage(db);
 const bound={...env,BOOKING_WAKE_QUEUE:{send:async(body,options)=>{sent.push({body,options});}},
  ...(product===undefined?{}:{BOOKING_PRODUCT_STATE:product})};
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
  view(){return instance.view();},rest(){return instance.restingAt();},
  edit(change){const value={...instance.view(),...change};store.sql.exec('UPDATE recovery_view SET view=?',JSON.stringify(value));}};
}
async function logged(callback) {
 const lines=[],saved=console.log;console.log=line=>lines.push(JSON.parse(line));
 try {await callback(lines);return lines;} finally {console.log=saved;}
}
const reasons=lines=>lines.filter(line=>line.event==='booking_recovery_tick').map(line=>line.reason);
const answer=value=>()=>Response.json(value);

test('OFF: the ring run does not drain, the first tick after the margin does, then ticks rest with no call',()=>logged(async lines=>{
 let copy={idle:true,pending:false,published_at_ms:Date.now()-1000};
 const product=productBinding(()=>Response.json(copy)),o=object(website(),{product});
 await o.run('wake');assert.equal(o.site.calls.length,1);
 await o.tick();assert.equal(o.site.calls.length,1,'inside the margin the notebook rules apply');
 // The margin passes (the copy is moved back instead of waiting 150 s).
 copy={...copy,published_at_ms:o.view().full_started_at-DRAIN_MARGIN+1};
 await o.tick();assert.equal(o.site.calls.length,2);assert.ok(drained(o.view(),copy));
 for(let i=0;i<3;i++) await o.tick();
 assert.equal(o.site.calls.length,2);assert.equal(o.sent.length,0);
 assert.deepEqual(reasons(lines),['idle','drain','dormant','dormant','dormant']);
 assert.ok(o.rest()>0);assert.equal(await o.health(),200);
 // The same installation's product object, by name, read once per tick through its internal path.
 assert.deepEqual([...new Set(product.names)],['booking-product:'+env.BOOKING_INSTALLATION_ID+':test']);
 assert.equal(product.reads,5);assert.ok(product.urls.every(url=>new URL(url).pathname==='/internal/recovery-state'));
 // A day later the full look is 24 h old: green while resting, where the 12-hour rule alone would be red.
 o.edit({full_at:Date.now()-DAY});assert.equal(await o.health(),200);
 o.instance.markRest(null);assert.equal(await o.health(),503);
 await o.tick();assert.equal(await o.health(),200);assert.equal(o.site.calls.length,2);
 // ON: today's rescue runs at once, the rest mark ends with that run, and the next tick is idle.
 copy={idle:false,pending:false,published_at_ms:Date.now()};
 await o.tick();assert.equal(o.site.calls.length,3);assert.equal(o.rest(),null);assert.equal(await o.health(),200);
 await o.tick();assert.equal(o.site.calls.length,3);
 assert.deepEqual(reasons(lines).slice(-3),['dormant','rescue','idle']);
}));

test('while resting the weekly check runs; a failed check turns health red at once and retries every tick',()=>logged(async lines=>{
 let down=false;const copy={idle:true,pending:false,published_at_ms:Date.now()-DRAIN_MARGIN-60000};
 const o=object(website({fail:path=>down && path.endsWith('/plan')}),{product:productBinding(()=>Response.json(copy))});
 await o.tick();await o.tick();assert.deepEqual(reasons(lines),['unknown','dormant']);
 o.edit({full_at:Date.now()-DORMANT_CHECK});down=true;
 await o.tick();assert.equal(reasons(lines).at(-1),'dormant_check');
 assert.equal(o.view().failures,1);assert.ok(o.rest()>0,'a failed run keeps the mark');assert.equal(await o.health(),503);
 const calls=o.site.calls.length;await o.tick();assert.equal(reasons(lines).at(-1),'rescue');assert.equal(o.site.calls.length,calls+1);
 down=false;await o.tick();assert.equal(o.view().failures,0);assert.equal(o.rest(),null);assert.equal(await o.health(),200);
 await o.tick();assert.equal(reasons(lines).at(-1),'dormant');
}));

test('a resting site still runs known due work on time and books one hint for work due before the next tick',()=>logged(async lines=>{
 const copy={idle:true,pending:false,published_at_ms:Date.now()-DRAIN_MARGIN-60000};
 const o=object(website(),{product:productBinding(()=>Response.json(copy))});
 await o.tick();
 o.edit({lanes:{...o.view().lanes,notification_email:{remaining_due:0,next_due_at:Date.now()+600000,stall:0,clamp:0}}});
 await o.tick();assert.equal(reasons(lines).at(-1),'hint');assert.equal(o.sent.length,1);assert.ok(o.rest()>0);
 await o.tick();assert.equal(reasons(lines).at(-1),'hinted');assert.equal(o.sent.length,1);
 o.edit({lanes:{...o.view().lanes,notification_email:{remaining_due:0,next_due_at:Date.now()-1000,stall:0,clamp:0}}});
 const calls=o.site.calls.length;await o.tick();assert.equal(reasons(lines).at(-1),'due');assert.equal(o.site.calls.length,calls+1);
}));

test('an unreadable, slow, refused, malformed or pending copy, or no binding, keeps today\'s decisions',()=>logged(async lines=>{
 const late=()=>new Promise((_,reject)=>setTimeout(()=>reject(Error('synthetic late failure')),1700));
 const copy={idle:true,pending:false,published_at_ms:Date.now()-DRAIN_MARGIN-60000};
 const faults={missing:undefined,throws:productBinding(()=>{throw Error('synthetic state failure');}),
  slow:productBinding(late),never:productBinding(()=>new Promise(()=>{})),refused:productBinding(()=>Response.json({code:'state_unavailable'},{status:503})),
  html:productBinding(()=>new Response('<html></html>',{headers:{'content-type':'text/html'}})),
  extra:productBinding(answer({...copy,enabled:false})),pending:productBinding(answer({...copy,pending:true})),
  text:productBinding(answer({...copy,idle:'true'})),time:productBinding(answer({...copy,published_at_ms:-5})),
  array:productBinding(answer([copy]))};
 for(const [name,product] of Object.entries(faults)) {
  const o=object(website(),{product});
  await o.tick();o.edit({full_at:Date.now()-RESCUE});
  const calls=o.site.calls.length,started=Date.now();await o.tick();
  assert.equal(o.site.calls.length,calls+1,name);assert.equal(reasons(lines).at(-1),'rescue',name);assert.equal(o.rest(),null,name);
  assert.ok(Date.now()-started<4000,name);
 }
 // The late rejection must not surface as an unhandled rejection after the tick has moved on.
 await new Promise(resolve=>setTimeout(resolve,400));
}));

test('a run admitted or a wake note saved during the copy read is seen by the same tick',()=>logged(async lines=>{
 const copy={idle:true,pending:false,published_at_ms:Date.now()-DRAIN_MARGIN-60000};let during=()=>{};
 const o=object(website(),{product:productBinding(()=>{during();return Response.json(copy);})});
 await o.tick();await o.tick();assert.equal(reasons(lines).at(-1),'dormant');
 during=()=>o.store.sql.exec('INSERT INTO recovery_lease VALUES(1,?,?) ON CONFLICT(singleton) DO UPDATE SET until_ms=excluded.until_ms',randomUUID(),Date.now()+60000);
 await o.tick();assert.equal(reasons(lines).at(-1),'busy');
 o.store.sql.exec('DELETE FROM recovery_lease');
 during=()=>o.instance.mark('wake_pending_at',Date.now());
 const calls=o.site.calls.length;await o.tick();assert.equal(reasons(lines).at(-1),'wake_pending');assert.equal(o.site.calls.length,calls+1);
 during=()=>{};await o.tick();assert.equal(reasons(lines).at(-1),'dormant');
}));

test('a stale rest mark after a rollback and re-deploy is cleared by the first run; the tables are idempotent',()=>logged(async lines=>{
 const db=new DatabaseSync(':memory:');
 const copy={idle:false,pending:false,published_at_ms:Date.now()};
 const o=object(website(),{product:productBinding(()=>Response.json(copy)),db});
 await o.tick();o.instance.markRest(Date.now()-3*DAY);
 // Older code ran meanwhile and left an older release in the notebook.
 o.edit({release_digest:'b'.repeat(64),full_at:Date.now()-13*HOUR});
 const again=object(website(),{product:productBinding(()=>Response.json(copy)),db});
 assert.ok(again.rest()>0);
 await again.tick();assert.equal(reasons(lines).at(-1),'release');assert.equal(again.rest(),null);assert.equal(await again.health(),200);
 // A failed run does not clear it; only a completed one does.
 const failing=object(website({fail:path=>path.endsWith('/plan')}),{product:productBinding(()=>Response.json(copy))});
 failing.instance.markRest(Date.now());await failing.run('wake');assert.ok(failing.rest()>0);assert.equal(await failing.health(),503);
}));

test('a wake ring while resting runs at once; the next tick rests again; a busy tick leaves the mark alone',()=>logged(async lines=>{
 const copy={idle:true,pending:false,published_at_ms:Date.now()-DRAIN_MARGIN-60000};
 const o=object(website(),{product:productBinding(()=>Response.json(copy))});
 await o.tick();await o.tick();assert.equal(reasons(lines).at(-1),'dormant');const mark=o.rest();assert.ok(mark>0);
 const calls=o.site.calls.length;await o.run('wake');assert.equal(o.site.calls.length,calls+1);assert.equal(o.rest(),null);
 await o.tick();assert.equal(reasons(lines).at(-1),'dormant');assert.equal(o.site.calls.length,calls+1);assert.ok(o.rest()>0);
 o.instance.markRest(mark);
 o.store.sql.exec('INSERT INTO recovery_lease VALUES(1,?,?) ON CONFLICT(singleton) DO UPDATE SET until_ms=excluded.until_ms',randomUUID(),Date.now()+60000);
 await o.tick();assert.equal(reasons(lines).at(-1),'busy');assert.equal(o.rest(),mark);
}));

test('a run completed during the copy read keeps that tick from marking rest',()=>logged(async lines=>{
 const copy={idle:true,pending:false,published_at_ms:Date.now()-DRAIN_MARGIN-60000};let during=()=>{};
 const o=object(website(),{product:productBinding(()=>{during();return Response.json(copy);})});
 await o.tick();o.instance.markRest(null);o.edit({observed_at:Date.now()+10000});
 // A run that finished while the tick waited (newer than every earlier run, not newer than the notebook).
 during=()=>o.store.sql.exec("INSERT INTO recovery_runs(id,scheduled,source,completed,healthy) VALUES(?,?,?,?,1)",randomUUID(),Date.now(),'wake',Date.now()+5000);
 await o.tick();assert.equal(reasons(lines).at(-1),'dormant');assert.equal(o.rest(),null);
 during=()=>{};await o.tick();assert.ok(o.rest()>0);
}));
