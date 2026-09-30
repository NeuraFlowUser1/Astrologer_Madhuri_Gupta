// Customer records and durable obligations stay in Neon. Queue messages only wake
// bounded consumers. The health route reads Cloudflare KV, never the website/DB.
const APP = '004-sarsa-jyotish-sansthan';
const ORIGIN = 'https://www.sarsajyotishsansthan.com';
const PERIOD = 900_000;
const LANES = Object.freeze({
  contact_email: ['/api/internal/contact/email', 'SARSA_EMAIL_WORKER_KEY'],
  payment_events: ['/api/internal/recovery/payment-events', 'SARSA_RECOVERY_WORKER_KEY'],
  payment: ['/api/internal/recovery/payment', 'SARSA_RECOVERY_WORKER_KEY'],
  google: ['/api/internal/google/run', 'SARSA_GOOGLE_WORKER_KEY'],
  email_events: ['/api/internal/email/events', 'SARSA_EMAIL_WORKER_KEY'],
  email: ['/api/internal/email/run', 'SARSA_EMAIL_WORKER_KEY'],
  contact_google: ['/api/internal/contact/google', 'SARSA_GOOGLE_WORKER_KEY'],
});
const secretValid = value => typeof value === 'string' && /^[A-Za-z0-9_-]{43}=$/.test(value);
const result = (value, status = 200) => Response.json(value, {status, headers: {'cache-control':'no-store'}});
const messageValid = value => value && Object.keys(value).sort().join(',') === 'remaining,version'
  && value.version === 1 && Number.isInteger(value.remaining) && value.remaining >= 0 && value.remaining <= 8;

// Diagnose a failed pass without logging credentials or provider response text.
const FAILURE_CODES = new Set(['configuration_missing', 'pass_deadline',
  'backend_identity', 'response_invalid', 'response_limit', 'plan_invalid',
  'lane_invalid', 'lane_unavailable', 'stale_schedule', 'backend_timeout',
  'backend_request_failed', 'heartbeat_write_failed', 'recovery_attention']);
function safeFailureCode(error) {
  const code = error?.message;
  if (typeof code === 'string' && (FAILURE_CODES.has(code)
      || /^backend_http_[1-5][0-9]{2}$/.test(code))) return code;
  return error?.name === 'AbortError' ? 'backend_timeout' : 'backend_request_failed';
}

async function boundedJSON(response, maximum) {
  if (!response.headers.get('content-type')?.toLowerCase().startsWith('application/json')) throw Error('response_invalid');
  if (!response.body) throw Error('response_invalid');
  const reader = response.body.getReader();
  let text = '', size = 0;
  const decoder = new TextDecoder('utf-8', {fatal:true});
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maximum) throw Error('response_limit');
      text += decoder.decode(value, {stream:true});
    }
    return JSON.parse(text + decoder.decode());
  } finally { await reader.cancel().catch(() => {}); }
}

export function checkedPlan(value) {
  if (!value || value.application !== APP || value.version !== 1 || typeof value.attention !== 'boolean'
      || !value.lanes || Object.keys(value.lanes).sort().join(',') !== Object.keys(LANES).sort().join(',')
      || Object.values(value.lanes).some(v => v !== null && (!Number.isInteger(v) || v < 0 || v > 900))) {
    throw Error('plan_invalid');
  }
  return value;
}

export function createWorker({fetcher = (...args) => fetch(...args), now = () => Date.now()} = {}) {
  async function call(path, key, env, deadline = Infinity) {
    if (!secretValid(env[key])) throw Error('configuration_missing');
    const remaining = Math.min(100_000, deadline-now());
    if (remaining <= 0) throw Error('pass_deadline');
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), remaining);
    try {
      // The edge runtime supports manual redirects; reject every non-200 below
      // so authorization is never forwarded to a redirect destination.
      const response = await fetcher(ORIGIN + path, {method:'POST', redirect:'manual',
        headers:{'content-type':'application/json','authorization':'Bearer ' + env[key]},
        body:'{}', signal:controller.signal});
      if (response.status !== 200) { await response.body?.cancel(); throw Error('backend_http_' + response.status); }
      const data = await boundedJSON(response, 8192);
      if (data.application !== APP) throw Error('backend_identity');
      return data;
    } catch (error) {
      throw Error(safeFailureCode(error));
    } finally { clearTimeout(timer); }
  }
  const plan = async (env, deadline) => checkedPlan(await call('/api/internal/recovery/plan', 'SARSA_RECOVERY_WORKER_KEY', env, deadline));

  async function authorized(request, env) {
    if (!secretValid(env.SARSA_WAKE_KEY)) return false;
    const supplied = request.headers.get('authorization') || '';
    if (supplied.length !== 51) return false;
    // Compare fixed-size digests without an early exit on differing bytes.
    const encoder = new TextEncoder();
    const [a,b] = await Promise.all([supplied,'Bearer ' + env.SARSA_WAKE_KEY].map(value =>
      crypto.subtle.digest('SHA-256',encoder.encode(value)).then(buffer => new Uint8Array(buffer))));
    let difference = 0;
    for (let i = 0; i < a.length; i++) difference |= a[i] ^ b[i];
    return difference === 0;
  }

  return {
    async fetch(request, env) {
      const url = new URL(request.url);
      if (url.pathname === '/health' && request.method === 'GET' && !url.search) {
        try {
          const time = now();
          const slot = Math.floor(time / PERIOD);
          // Per-slot keys avoid an old overlapping sweep overwriting a newer one.
          const records = await Promise.all([slot,slot-1,slot-2].map(n => env.HEARTBEATS.get('sweep:' + n, 'json')));
          const latest = records.filter(v => v && Number.isSafeInteger(v.scheduled_at)
            && v.scheduled_at <= time && Number.isSafeInteger(v.completed_at)
            && v.completed_at >= v.scheduled_at && v.completed_at <= time
            && typeof v.healthy === 'boolean').sort((a,b) => b.scheduled_at-a.scheduled_at)[0];
          const healthy = latest && latest.healthy && time-latest.scheduled_at <= 1_200_000;
          return result({status:healthy ? 'healthy':'attention'}, healthy ? 200:503);
        } catch { return result({status:'unavailable'},503); }
      }
      if (url.pathname !== '/wake' || request.method !== 'POST' || url.search) return result({code:'not_found'},404);
      if (!(await authorized(request,env))) return result({code:'unauthorized'},401);
      try {
        if (request.headers.get('content-encoding') && request.headers.get('content-encoding') !== 'identity') throw Error();
        const body = await boundedJSON(request,64);
        if (!body || Array.isArray(body) || Object.keys(body).length !== 0) throw Error();
      } catch { return result({code:'invalid_request'},400); }
      try {
        await env.WAKE_QUEUE.send({version:1,remaining:8});
        return result({application:APP,queued:true},202);
      } catch { return result({code:'wake_unavailable'},503); }
    },

    async scheduled(controller, env) {
      const scheduled = controller.scheduledTime;
      if (!Number.isSafeInteger(scheduled) || scheduled > now() || now()-scheduled > PERIOD) throw Error('stale_schedule');
      let healthy = false;
      try {
        const state = await plan(env);
        // Idle system: one DB read per rescue sweep and no queue invocations.
        if (Object.values(state.lanes).some(v => v !== null && v < 900)) {
          await env.WAKE_QUEUE.send({version:1,remaining:8});
        }
        healthy = !state.attention;
      } catch (error) {
        throw Error(safeFailureCode(error));
      } finally {
        // Success means the durable queue was inspected and necessary wake-up
        // publication accepted. It is NOT a claim that all obligations finished.
        try {
          await env.HEARTBEATS.put('sweep:' + Math.floor(scheduled/PERIOD),
            JSON.stringify({scheduled_at:scheduled,completed_at:now(),healthy}), {expirationTtl:86400});
        } catch { throw Error('heartbeat_write_failed'); }
      }
      if (!healthy) throw Error('recovery_attention');
    },

    async queue(batch, env) {
      for (const message of batch.messages) {
        if (!messageValid(message.body)) {
          message.ack(); // No work identifiers here; DB rescue remains authority.
          console.warn('invalid_recovery_wake');
          continue;
        }
        try {
          const deadline = now()+90_000;
          const before = await plan(env,deadline);
          let failed = false, processed = 0;
          // At most seven invocations, sequentially; events process at most one
          // booking and one enquiry report. Errors do not stop later lanes
          // while the pass still has time; durable work survives the deadline.
          for (const [lane,[path,key]] of Object.entries(LANES)) {
            if (before.lanes[lane] !== 0) continue;
            try {
              if (now() >= deadline-1_000) { failed = true; break; }
              const response = await call(path,key,env,deadline);
              if (!Number.isInteger(response.processed) || response.processed < 0 || response.processed > (lane === 'email_events' ? 2 : 1)) throw Error('lane_invalid');
              processed += response.processed;
              if (response.retry === true) failed = true;
            } catch (error) {
              failed = true;
              console.warn('recovery_lane_failure', lane, safeFailureCode(error));
            }
          }
          if (failed) throw Error('lane_unavailable');
          const after = await plan(env,deadline);
          const pending = Object.values(after.lanes).filter(v => v !== null && v < 900);
          if (pending.length && message.body.remaining > 0) {
            // Bounded continuation: no infinite self-publishing loop. A due
            // future retry uses DB timing, never an invented new job identity.
            await env.WAKE_QUEUE.send({version:1,remaining:message.body.remaining-1},
              {delaySeconds:Math.max(Math.min(...pending) === 0 ? (processed ? 5:60):1,Math.min(...pending))});
          }
          message.ack();
        } catch (error) {
          // Retry only the wake-up. Provider ambiguity stays in durable SQL jobs.
          message.retry({delaySeconds:60});
          console.warn('recovery_wake_retry', safeFailureCode(error));
        }
      }
    },
  };
}
export default createWorker();
