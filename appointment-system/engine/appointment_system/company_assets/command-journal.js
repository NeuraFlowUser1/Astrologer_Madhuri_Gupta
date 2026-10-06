(() => {
  'use strict';
  const scope = /*COMPANY_BROWSER_CONFIGURATION*/null;
  const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(value) && value !== '00000000-0000-0000-0000-000000000000';
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const fail = () => { throw Object.assign(new Error('company_command_storage_unavailable'), {code:'company_command_storage_unavailable'}); };
  function key(purpose) {
    if (!object(scope) || !uuid(scope.installation_id) || !['production','development','test'].includes(scope.environment)
        || !['mode','business'].includes(purpose)) return fail();
    return `appointment-system:${scope.installation_id}:${scope.environment}:company:${purpose}:v1`;
  }
  function valid(purpose, value) {
    if (!object(value) || !uuid(value.operation_id) || !/^[1-9][0-9]{0,18}$/.test(value.revision)
        || typeof value.revision !== 'string' || typeof value.reason !== 'string' || value.reason.length < 5 || value.reason.length > 300) return false;
    const fields = purpose === 'mode' ? ['operation_id','generation','revision','enabled','reason'] : ['operation_id','revision','settings','reason'];
    if (Object.keys(value).length !== fields.length || fields.some(name => !Object.hasOwn(value,name))) return false;
    return purpose === 'mode' ? uuid(value.generation) && typeof value.enabled === 'boolean' : object(value.settings);
  }
  function decode(purpose, raw) {
    if (raw === null) return null;
    if (typeof raw !== 'string' || raw.length > 65536) return fail();
    let saved; try { saved = JSON.parse(raw); } catch { return fail(); }
    if (!object(saved) || Object.keys(saved).length !== 5 || saved.version !== 1
        || saved.installation_id !== scope.installation_id || saved.environment !== scope.environment
        || saved.purpose !== purpose || !valid(purpose,saved.command)) return fail();
    return saved.command;
  }
  function read(purpose) {
    const name = key(purpose);
    try { return decode(purpose, sessionStorage.getItem(name)); } catch { return fail(); }
  }
  function save(purpose, command) {
    const name = key(purpose);
    if (command !== null && !valid(purpose,command)) return fail();
    try {
      if (command === null) {
        sessionStorage.removeItem(name);
        if (sessionStorage.getItem(name) !== null) return fail();
        return null;
      }
      const raw = JSON.stringify({version:1,installation_id:scope.installation_id,environment:scope.environment,purpose,command});
      decode(purpose,raw);
      sessionStorage.setItem(name,raw);
      if (sessionStorage.getItem(name) !== raw) return fail();
      return decode(purpose,raw);
    } catch { return fail(); }
  }
  // Per-tab storage plus the server's expected revision handles separate tabs.
  // There is deliberately no memory-only substitute for a durable retry record.
  window.PracticeCompanyCommands = Object.freeze({read,save});
})();
