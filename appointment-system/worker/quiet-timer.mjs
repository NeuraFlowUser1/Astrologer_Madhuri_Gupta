// Quiet timer: pure decisions for the quarter-hour tick, the notebook and health. No I/O, no clock reads.
// The worker's notebook ("view") is written by every run; marks are written by ticks, wake notes and hints.
export const PERIOD=900000,GRACE=60000,TOLERANCE=120000,RESCUE=43200000;
export const TICK_STALE=1200000,DUE_LATE=300000,WAKE_LATE=PERIOD+300000,CLAMP=899000,FOLLOW=15000;
export const QUICK_RETRIES=Object.freeze([30,60]);
export const VERSION=1;
const PUBLICATION='control_publication';
const finite=value=>Number.isSafeInteger(value);

export function backoff(count) {
 return Math.min(RESCUE,PERIOD*2**Math.max(0,Math.min(count,16)-1));
}

export function usable(view) {
 return !!view && typeof view==='object' && view.version===VERSION && finite(view.observed_at)
  && view.lanes && typeof view.lanes==='object' && !Array.isArray(view.lanes);
}

// A lane is stalled after two called turns in a row made no progress while its earliest due did not move later.
export const stalled=item=>item.stall>=2;
// The display-publication schedule is capped at 900 s from now and reports exactly that cap when nothing is
// pending (SQL least() ignores NULL); real publication retries are at most 480 s. A cap reading is idle: it is
// never a known due time, never a health concern and never a reason to re-check.
export const clamped=(lane,item)=>lane===PUBLICATION && item.clamp>=1;
const held=(lane,item)=>stalled(item) || clamped(lane,item);

export function known(view) {
 const times=[];let remaining=false;
 for(const [lane,item] of Object.entries(view.lanes)) {
  if(held(lane,item)) continue;
  if(item.remaining_due>0) remaining=true;
  if(item.next_due_at!==null) times.push(item.next_due_at-view.offset_ms);
 }
 return {remaining,earliest:times.length?Math.min(...times):null};
}

function figures(result,lane) {
 const ended=result.final?.lanes?.[lane],ack=result.acknowledgements[lane];
 if(ended) return {...ended,evaluated_at:result.final.evaluated_at};
 if(ack) return {remaining_due:ack.remaining_due,next_due_at:ack.next_due_at,evaluated_at:ack.evaluated_at};
 return {...result.plan.lanes[lane],evaluated_at:result.plan.evaluated_at};
}

export function summarise(previous,result,{startedAt,now,planAt,digest}) {
 const before=usable(previous)?previous:null,lanes={};
 for(const lane of Object.keys(result.plan.lanes)) {
  const prior=before?.lanes?.[lane] || {stall:0,clamp:0},item=figures(result,lane),planned=result.plan.lanes[lane];
  const ack=result.acknowledgements[lane],called=result.attempted.includes(lane);
  let stall=prior.stall;
  if(item.remaining_due===0) stall=0;
  else if(!called) stall=prior.stall;
  else if(ack?.processed===1) stall=0;
  else if(item.next_due_at!==null && planned.next_due_at!==null && item.next_due_at>planned.next_due_at) stall=0;
  else stall=prior.stall+1;
  const clamp=lane===PUBLICATION && item.next_due_at!==null && item.next_due_at>=item.evaluated_at+CLAMP?prior.clamp+1:0;
  lanes[lane]={remaining_due:item.remaining_due,next_due_at:item.next_due_at,stall,clamp};
 }
 const attention=(result.final || result.plan).attention,ok=result.healthy===true;
 // Without a final summary, lanes not called may hold work the run created (a confirmed payment adds emails);
 // an unhealthy run that is not explained by attention or a stall is checked again soon, not after 12 hours.
 const recheck=result.complete===false || !ok && !attention && !Object.values(lanes).some(stalled);
 return {version:VERSION,release_digest:digest,observed_at:Math.max(before?.observed_at ?? 0,now),run_started_at:startedAt,
  offset_ms:planAt===null?(before?.offset_ms ?? 0):result.plan.evaluated_at-planAt,lanes,
  attention,healthy:ok,recheck,full_started_at:startedAt,full_at:now,attempt_at:startedAt,failures:0};
}

export function failed(previous,{startedAt,now,digest}) {
 const before=usable(previous)?previous:null;
 return {version:VERSION,release_digest:digest,observed_at:Math.max(before?.observed_at ?? 0,now),run_started_at:startedAt,
  offset_ms:before?.offset_ms ?? 0,lanes:before?.lanes ?? {},attention:true,healthy:false,recheck:false,
  full_started_at:before?.full_started_at ?? null,full_at:before?.full_at ?? null,attempt_at:startedAt,
  failures:Math.min(1000,(before?.failures ?? 0)+1)};
}

// A run that started before the stored one must not overwrite newer figures; it only moves the observation forward.
export function merged(previous,next) {
 if(!usable(previous) || next.run_started_at>=(previous.run_started_at ?? 0)) return next;
 return {...previous,observed_at:Math.max(previous.observed_at,next.observed_at)};
}

export function decide(view,marks,latestRunAt,now,digest) {
 if(!usable(view) || latestRunAt!==null && latestRunAt>view.observed_at) return {run:true,reason:'unknown'};
 if(view.release_digest!==digest) return {run:true,reason:'release'};
 if(marks.wake_pending_at!==null) return {run:true,reason:'wake_pending'};
 if(view.full_at===null || now-view.full_at>=RESCUE-TOLERANCE) return {run:true,reason:'rescue'};
 const due=known(view);
 if(view.failures>0) {
  if(due.remaining || due.earliest!==null || now>=view.attempt_at+backoff(view.failures)) return {run:true,reason:'retry'};
  return {run:false,reason:'failing'};
 }
 if(view.recheck===true) return {run:true,reason:'recheck'};
 if(due.remaining) return {run:true,reason:'remaining'};
 if(due.earliest!==null && due.earliest<=now+GRACE) return {run:true,reason:'due'};
 const counts=Object.values(view.lanes).filter(stalled).map(item=>item.stall-1);
 if(counts.length && now>=view.full_at+backoff(Math.min(...counts))) return {run:true,reason:'held'};
 if(due.earliest!==null && due.earliest<now+PERIOD) {
  const covered=marks.hint_at!==null && marks.hint_at>=now && marks.hint_at<=due.earliest+GRACE;
  return covered?{run:false,reason:'hinted'}:{run:false,reason:'hint',hint_at:Math.max(now+FOLLOW,due.earliest)};
 }
 return {run:false,reason:'idle'};
}

// Follow-up after a run: quick retries after a failure, 15 s while known work remains or a re-check is needed
// (at most five in a row, as before), or one hint for work due soon (capped only when it is a minute or less away).
export function followUp(view,attempt,now,succeeded) {
 if(!succeeded) {
  const delay=QUICK_RETRIES[view.failures-1];
  return delay===undefined?null:{delay,attempt:Math.min(5,attempt+1)};
 }
 const due=known(view);
 if(due.remaining || view.recheck===true) return attempt>=5?null:{delay:FOLLOW/1000,attempt:attempt+1};
 if(due.earliest===null || due.earliest>now+PERIOD) return null;
 const delay=Math.max(FOLLOW/1000,Math.min(PERIOD/1000,Math.ceil((due.earliest-now)/1000)));
 // Short retries (a publication probe every 15 s) stay capped at five in a row; the next tick restarts them.
 if(attempt>=5 && delay*1000<=GRACE) return null;
 return {delay,attempt:Math.min(5,attempt+1)};
}

export function legacyHealthy(latest,now) {
 return !!latest && latest.healthy===1 && latest.completed!==null && latest.scheduled<=now
  && latest.completed<=now && now-latest.scheduled<=TICK_STALE;
}

export function healthy(view,marks,latestRunAt,legacy,now) {
 // Before the first tick of new code (a wake run may come first), and after a rollback, the old rule applies.
 if(!usable(view) || marks.last_tick_at===null || latestRunAt!==null && latestRunAt>view.observed_at) return legacyHealthy(legacy,now);
 if(now-marks.last_tick_at>TICK_STALE) return false;
 if(view.full_at===null || now-view.full_at>RESCUE+TICK_STALE) return false;
 if(view.healthy!==true || view.failures!==0) return false;
 for(const [lane,item] of Object.entries(view.lanes)) {
  if(stalled(item)) return false;
  if(clamped(lane,item) || item.next_due_at===null) continue;
  const due=item.next_due_at-view.offset_ms;
  if(due<now-DUE_LATE && due>view.full_at) return false;
 }
 return !(marks.wake_pending_at!==null && now-marks.wake_pending_at>WAKE_LATE);
}
