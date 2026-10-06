// Persist opaque operation IDs only. Never persist notes, contacts or access codes.
(() => {
 'use strict';
 const config = /*STAFF_BROWSER_CONFIGURATION*/null;
 const valid = value => /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(value || '') && value !== '00000000-0000-0000-0000-000000000000';
 if (!config || !valid(config.installation_id) || !['development','test','production'].includes(config.environment)) throw Error('Invalid staff storage configuration');
 const stores = new Map();
 const message = 'Your browser could not safely save this action. Allow website storage, then check earlier saved actions before making a change.';
 window.PracticeStaffActions = purpose => {
  if (!['client','company','calendar','inbox','enquiry'].includes(purpose)) throw Error('Invalid staff purpose');
  if (stores.has(purpose)) return stores.get(purpose);
  const key = `appointment-system:${config.installation_id}:${config.environment}:staff:${purpose}:v1`;
  const legacy = config.legacy[purpose];
  let last = [], problem = null;
  const copy = rows => rows.map(({operation_id,created_at}) => ({operation_id,created_at}));
  function read() {
   const snapshots = new Map(), merged = new Map();
   for (const name of [key,...legacy]) {
    const raw = localStorage.getItem(name); snapshots.set(name,raw);
    if(raw!==null && (typeof raw!=='string' || raw.length>8192))throw Error(message);
    const rows = raw === null ? [] : JSON.parse(raw);
    if (!Array.isArray(rows) || rows.length > 32 || rows.some(row => !row || Object.keys(row).sort().join(',') !== 'created_at,operation_id' || !valid(row.operation_id) || !Number.isSafeInteger(row.created_at) || row.created_at < 0)) throw Error(message);
    for (const row of rows) {
     const old = merged.get(row.operation_id);
     // Keep the later age when legacy copies disagree: never prematurely
     // discard an in-flight operation because another tab saved an older age.
     merged.set(row.operation_id,{operation_id:row.operation_id,created_at:Math.max(old?.created_at || 0,row.created_at)});
    }
   }
   const rows = [...merged.values()];
   if (rows.length > 32) throw Error(message);
   return {rows,snapshots};
  }
  function get() {
   try { last = read().rows; problem = null; } catch { problem = message; }
   return copy(last);
  }
  async function change(update) {
   try {
    if (!navigator.locks?.request) throw Error(message);
    return await navigator.locks.request(key,{mode:'exclusive'},() => {
     const {rows,snapshots} = read(), next = update(rows);
     const encoded = JSON.stringify(next);
     localStorage.setItem(key,encoded);
     if (localStorage.getItem(key) !== encoded) throw Error(message);
     // Only retire the exact old bytes that were merged. New old-tab writes
     // remain visible on the next read rather than being silently erased.
     for (const name of legacy) if (snapshots.get(name) !== null && localStorage.getItem(name) === snapshots.get(name)) localStorage.removeItem(name);
     last = copy(next); problem = null; return copy(last);
    });
   } catch { problem = message; throw Error(message); }
  }
  const store = {
   get, get error() { return problem; },
   remember(id) {
    if (!valid(id)) return Promise.reject(Error('Invalid action reference'));
    return change(rows => {
     if (rows.some(row => row.operation_id === id)) return rows;
     if (rows.length >= 32) throw Error(message);
     return [...rows,{operation_id:id,created_at:Date.now()}];
    });
   },
   forget(id) {
    if (!valid(id)) return Promise.reject(Error('Invalid action reference'));
    return change(rows => rows.filter(row => row.operation_id !== id));
   },
   async check(request, accepted, current = () => true) {
    const saved = get(), results = [];
    if (problem) throw Error(problem);
    for (const item of saved) {
     if (!current()) return null;
     const result = await request({operation_id:item.operation_id});
     if (!current()) return null;
     if (!result || result.operation_id !== item.operation_id) throw Error('The earlier result still needs checking.');
     if (result.code === 'operation_not_found') {
      if (Date.now() - item.created_at < 300000) throw Error('An earlier action may still be finishing. Please check it again shortly.');
     } else if (!accepted.includes(result.code)) throw Error('The earlier result still needs checking.');
     await store.forget(item.operation_id);
     if (!current()) return null;
     results.push(result);
    }
    return results;
   },
  };
  stores.set(purpose,store); return store;
 };
})();
