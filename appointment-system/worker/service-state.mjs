// Minimal durable display projection. This module never calls the website or
// Neon and never receives customer records, controller sessions or API keys.
import {facts} from './installation.mjs';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const identifier = value => typeof value === 'string' && UUID.test(value) && value !== '00000000-0000-0000-0000-000000000000';
const HEX = /^[a-f0-9]{64}$/;
const MAXIMUM = 4096;
const MAX_INTEGER = 9223372036854775807n;
const encoder = new TextEncoder();
const object = value => value && typeof value === 'object' && !Array.isArray(value);
const keys = (value, names) => object(value) && Object.keys(value).sort().join(',') === names.split(',').sort().join(',');
export const canonical = value => JSON.stringify(object(value)
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, JSON.parse(canonical(value[key]))]))
  : Array.isArray(value) ? value.map(item => JSON.parse(canonical(item))) : value);
const failure = (code, status = 503) => Response.json({code}, {status, headers: {'cache-control':'no-store'}});
const positive = value => typeof value === 'string' && /^[1-9][0-9]{0,18}$/.test(value) && BigInt(value) <= MAX_INTEGER;

export function checkedSnapshot(value, env, barrier = false) {
  const declared=facts(env);
  if (!keys(value, 'version,installation_id,project,environment,origin,enabled,restore_generation,generation_sequence,revision,activation_epoch')
      || value.version !== 1 || value.installation_id !== declared.installation_id || value.project !== declared.project || value.environment !== declared.environment
      || value.origin !== declared.origin || typeof value.enabled !== 'boolean'
      || typeof value.restore_generation !== 'string' || typeof value.activation_epoch !== 'string'
      || !identifier(value.restore_generation) || !identifier(value.activation_epoch)
      || !positive(value.generation_sequence) || !(positive(value.revision) || (barrier && value.revision === '0' && !value.enabled))) {
    throw Error('state_invalid');
  }
  return value;
}

async function digest(value) {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(canonical(value))))]
    .map(byte => byte.toString(16).padStart(2,'0')).join('');
}
async function signingKey(env, name) {
  const value = env['BOOKING_CONTROL' + name];
  if (typeof value !== 'string' || !/^[A-Za-z0-9_-]{43}=$/.test(value)) throw Error('state_configuration');
  const bytes = Uint8Array.from(atob(value.replaceAll('-','+').replaceAll('_','/')), c => c.charCodeAt(0));
  if (bytes.length !== 32 || btoa(String.fromCharCode(...bytes)).replaceAll('+','-').replaceAll('/','_') !== value) throw Error('state_configuration');
  return crypto.subtle.importKey('raw', bytes, {name:'HMAC', hash:'SHA-256'}, false, ['sign','verify']);
}
const signedBytes = (env,purpose,value) => encoder.encode('booking-product:'+facts(env).installation_id+':'+facts(env).environment+':v1:'+purpose+':' + canonical(value));
async function signature(env, name, purpose, value) {
  return [...new Uint8Array(await crypto.subtle.sign('HMAC', await signingKey(env,name), signedBytes(env,purpose,value)))]
    .map(byte => byte.toString(16).padStart(2,'0')).join('');
}
async function verified(env, name, purpose, value, supplied) {
  if (!HEX.test(supplied || '')) return false;
  const bytes = Uint8Array.from(supplied.match(/../g), byte => Number.parseInt(byte,16));
  return crypto.subtle.verify('HMAC', await signingKey(env,name), bytes, signedBytes(env,purpose,value));
}
async function readBody(request) {
  if (request.headers.get('content-type')?.split(';')[0].trim() !== 'application/json'
      || ![null,'identity'].includes(request.headers.get('content-encoding')) || !request.body) throw Error('state_invalid');
  const reader = request.body.getReader(); let text = '', size = 0; const deadline=Date.now()+2000;
  const decoder = new TextDecoder('utf-8', {fatal:true});
  try {
    while (true) {
      let timer;
      const {done,value} = await Promise.race([reader.read(),new Promise((_,reject)=>{
        timer=setTimeout(()=>reject(Error('state_invalid')),Math.max(1,deadline-Date.now()));
      })]).finally(()=>clearTimeout(timer)); if (done) break;
      size += value.byteLength; if (size > MAXIMUM) throw Error('state_invalid');
      text += decoder.decode(value,{stream:true});
    }
    text += decoder.decode(); const value = JSON.parse(text);
    // Canonical signed requests also reject duplicate keys and ambiguous input.
    if (text !== canonical(value)) throw Error('state_invalid');
    return value;
  } catch { throw Error('state_invalid'); }
  finally { await reader.cancel().catch(() => {}); }
}
const fresh = time => Number.isSafeInteger(time) && Math.abs(Date.now()-time) <= 60_000;

export class BookingProductState {
  constructor(ctx, env) {
    this.ctx = ctx; this.env = env;
    ctx.storage.sql.exec('CREATE TABLE IF NOT EXISTS product_state (singleton INTEGER PRIMARY KEY CHECK(singleton=1), snapshot TEXT NOT NULL, body_hash TEXT NOT NULL, restore_pending INTEGER NOT NULL CHECK(restore_pending IN (0,1)), published_at_ms INTEGER NOT NULL)');
    ctx.storage.sql.exec('CREATE TABLE IF NOT EXISTS maintenance_operations (id TEXT PRIMARY KEY, body_hash TEXT NOT NULL, generation TEXT NOT NULL, sequence TEXT NOT NULL)');
  }
  load() {
    const rows = this.ctx.storage.sql.exec('SELECT snapshot,body_hash,restore_pending,published_at_ms FROM product_state WHERE singleton=1').toArray();
    if (!rows.length) return null;
    return {snapshot:checkedSnapshot(JSON.parse(rows[0].snapshot), this.env, Boolean(rows[0].restore_pending)),
      digest:rows[0].body_hash, pending:Boolean(rows[0].restore_pending), published_at_ms:rows[0].published_at_ms};
  }
  save(value, hash, pending = false) {
    this.ctx.storage.sql.exec('INSERT INTO product_state(singleton,snapshot,body_hash,restore_pending,published_at_ms) VALUES(1,?,?,?,?) ON CONFLICT(singleton) DO UPDATE SET snapshot=excluded.snapshot,body_hash=excluded.body_hash,restore_pending=excluded.restore_pending,published_at_ms=excluded.published_at_ms', canonical(value), hash, pending ? 1 : 0,Date.now());
  }
  async response(purpose, operation, state, keyName, nonce = null) {
    const declared=facts(this.env);
    const value = {version:1,installation_id:declared.installation_id,project:declared.project,
      environment:declared.environment,purpose,operation_id:operation,
      issued_at_ms:Date.now(),published_at_ms:state.published_at_ms,snapshot:state.snapshot,snapshot_hash:state.digest,reconcile_pending:state.pending};
    if (nonce !== null) value.nonce = nonce;
    return Response.json({...value,signature:await signature(this.env,keyName,purpose,value)},
      {headers:{'cache-control':'no-store','x-content-type-options':'nosniff'}});
  }
  async fetch(request) {
    try {
      const url = new URL(request.url);
      if (url.search) return failure('state_request_invalid',400);
      if (url.pathname === '/service-state' && request.method === 'GET') {
        const nonce = request.headers.get('x-booking-state-nonce');
        if (!HEX.test(nonce || '')) return failure('state_request_invalid',400);
        const state = this.load();
        if (!state || state.pending) return failure('state_reconciliation_required');
        return await this.response('read',null,state,'_READ_KEY',nonce);
      }
      const publishing = url.pathname === '/service-control/publish';
      const reconcile = url.pathname === '/service-control/reconcile';
      if (request.method !== 'POST' || (!publishing && !reconcile)) return failure('not_found',404);
      const body = await readBody(request); const declared=facts(this.env);
      const names = publishing ? 'version,installation_id,project,environment,purpose,operation_id,issued_at_ms,snapshot'
        : 'version,installation_id,project,environment,purpose,operation_id,issued_at_ms,snapshot,action,expected_generation';
      if (!keys(body,names) || body.version !== 1 || body.installation_id !== declared.installation_id || body.project !== declared.project || body.environment !== declared.environment
          || body.purpose !== (publishing ? 'publish':'reconcile') || !identifier(body.operation_id)
          || !fresh(body.issued_at_ms)) return failure('state_request_invalid',400);
      const keyName = publishing ? '_PUBLISH_KEY':'_RECONCILE_KEY';
      if (!(await verified(this.env,keyName,body.purpose,body,request.headers.get('x-booking-control-signature')))) return failure('state_unauthorized',401);
      checkedSnapshot(body.snapshot,this.env,reconcile && body.action === 'advance_generation');
      const hash = await digest(body.snapshot);
      const operationHash = await digest({...body,issued_at_ms:0});
      const state = this.ctx.storage.transactionSync(() => {
        const current = this.load();
        if (publishing) {
          if (!current) throw Error('state_reconciliation_required');
          if (current.snapshot.restore_generation !== body.snapshot.restore_generation
              || current.snapshot.generation_sequence !== body.snapshot.generation_sequence) throw Error('state_generation_conflict');
          const oldRevision = BigInt(current.snapshot.revision), revision = BigInt(body.snapshot.revision);
          if (revision < oldRevision || (revision === oldRevision && current.digest !== hash)) throw Error('state_revision_conflict');
          if (current.pending && (body.snapshot.revision !== '1' || body.snapshot.enabled)) throw Error('state_reconciliation_required');
          if (revision > oldRevision) this.save(body.snapshot,hash);
          return this.load();
        }
        const previous = this.ctx.storage.sql.exec('SELECT body_hash,generation,sequence FROM maintenance_operations WHERE id=?',body.operation_id).toArray()[0];
        if (previous) {
          if (previous.body_hash !== operationHash || !current || previous.generation !== current.snapshot.restore_generation
              || previous.sequence !== current.snapshot.generation_sequence) throw Error('state_operation_conflict');
          return current;
        }
        if (body.action === 'initialize') {
          if (current || body.expected_generation !== null || body.snapshot.generation_sequence !== '1'
              || body.snapshot.revision !== '1' || body.snapshot.enabled) throw Error('state_generation_conflict');
          this.save(body.snapshot,hash);
        } else if (body.action === 'advance_generation') {
          if (!current || body.expected_generation !== current.snapshot.restore_generation
              || body.snapshot.restore_generation === current.snapshot.restore_generation
              || BigInt(body.snapshot.generation_sequence) !== BigInt(current.snapshot.generation_sequence)+1n
              || body.snapshot.enabled || body.snapshot.revision !== '0') throw Error('state_generation_conflict');
          this.save(body.snapshot,hash,true);
        } else throw Error('state_request_invalid');
        this.ctx.storage.sql.exec('INSERT INTO maintenance_operations VALUES(?,?,?,?)',body.operation_id,operationHash,body.snapshot.restore_generation,body.snapshot.generation_sequence);
        return this.load();
      });
      return await this.response(publishing ? 'publish-ack':'reconcile-ack',body.operation_id,state,keyName);
    } catch (error) {
      const known = new Set(['state_invalid','state_configuration','state_reconciliation_required','state_generation_conflict',
        'state_revision_conflict','state_operation_conflict','state_request_invalid']);
      const code = known.has(error?.message) ? error.message : 'state_unavailable';
      return failure(code, code.endsWith('conflict') ? 409 : code === 'state_invalid' || code === 'state_request_invalid' ? 400 : 503);
    }
  }
}

export async function serviceState(request, env) {
  const path = new URL(request.url).pathname;
  if (path !== '/service-state' && !path.startsWith('/service-control/')) return null;
  try {
    if (!env.BOOKING_PRODUCT_STATE) return failure('state_configuration');
    // The caller cannot select an object, client, origin or environment.
    const declared=facts(env); const id = env.BOOKING_PRODUCT_STATE.idFromName('booking-product:'+declared.installation_id+':'+declared.environment);
    return await env.BOOKING_PRODUCT_STATE.get(id).fetch(request);
  } catch { return failure('state_unavailable'); }
}
