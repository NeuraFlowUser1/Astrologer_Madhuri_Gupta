(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const journal = window.PracticeCompanyCommands;
  const storageMessage = 'This browser could not safely save or read the change reference. Allow site storage, then refresh before trying again.';
  let current = null;
  let accessEpoch = 0;
  let csrf = null;
  let pending = null;
  let business = null;
  let pendingBusiness = null;
  async function request(path, body) {
    const epoch = accessEpoch;
    const response = await fetch(path, { method: body === undefined ? 'GET' : 'POST',
      credentials: 'same-origin', cache: 'no-store', redirect: 'error',
      headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-Company-CSRF': csrf } : {}) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(15000) });
    if ([401,403].includes(response.status) && !['/api/company/sign-in/start','/api/company/reauthenticate','/api/company/password'].includes(path)) {
      if (epoch === accessEpoch) { ++accessEpoch; hidePrivate(); $('status').textContent = 'Please sign in again to continue.'; }
      throw Object.assign(new Error('company_session_required'), {status:response.status});
    }
    const value = await response.json();
    if (epoch !== accessEpoch) throw new Error('company_session_changed');
    if (!response.ok) throw Object.assign(new Error(value.code || 'request_failed'), { status: response.status });
    return value;
  }
  function remember(value) {
    pending = journal.save('mode',value);
  }
  function hidePrivate() {
    current = null; csrf = null; business = null; pending = null; pendingBusiness = null;
    for (const id of ['signed-in','diagnostics','business-section','credentials-section','google-section','business-form']) $(id).hidden = true;
    $('signed-out').hidden = false;
    for (const id of ['google-pending','record-list','incident-list','business-services','business-windows']) $(id).replaceChildren();
    for (const id of ['google-status','record-status','incident-status','business-status','credential-status','reference']) $(id).textContent = '';
    for (const id of ['business-reason','reauth-password','old-password','new-password']) $(id).value = '';
  }
  function show(value) {
    const receipt = value.receipt;
    value = value.current || value;
    current = value.snapshot; csrf = value.csrf_token || csrf;
    $('signed-in').hidden = false; $('signed-out').hidden = true; $('diagnostics').hidden = false;
    $('business-section').hidden = false; $('credentials-section').hidden = false;
    $('google-section').hidden = false;
    $('mode').textContent = current.enabled ? 'On' : 'Off';
    $('publication').textContent = value.progress === 'effective' ? 'Website checked' : 'Website update pending';
    let storageReady = true;
    try {
      pending = journal.read('mode') || pending;
      if (pending && (value.operation_id === pending.operation_id || receipt?.operation_id === pending.operation_id)) remember(null);
    } catch { storageReady = false; }
    $('change').textContent = pending ? 'Check the saved change' : current.enabled ? 'Turn booking off' : 'Turn booking on';
    $('change').disabled = !storageReady;
    $('reference').textContent = value.operation_id ? `Saved change: ${value.operation_id}` : '';
    $('status').textContent = value.progress === 'effective'
      ? current.enabled ? 'Booking is on and the website is updated.' : 'New bookings are off and the website is updated.'
      : current.enabled ? 'Turning booking on. New bookings wait for the website update.' : 'New bookings have stopped. The website update is pending.';
    if (!storageReady) $('status').textContent = storageMessage;
  }
  async function refresh() {
    const epoch=accessEpoch;
    try { const value=await request('/api/company/control/status'); if(epoch===accessEpoch)show(value); }
    catch (error) {
      if(epoch!==accessEpoch)return;
      $('status').textContent = 'The company tool could not check its saved state. Please try again.';
    }
  }
  $('login-form').addEventListener('submit', async event => {
    event.preventDefault();
    $('login').disabled = true;
    try { await request('/api/company/sign-in/start', {username:$('username').value,password:$('password').value}); $('password').value=''; accessEpoch++; await refresh(); }
    catch { $('password').value=''; $('status').textContent = 'Sign-in failed. Check your username and password, or wait before trying again.'; }
    finally { $('login').disabled = false; }
  });
  $('refresh').addEventListener('click', refresh);
  $('logout').addEventListener('click', async () => {
    ++accessEpoch;
    try { await request('/api/company/sign-out', {}); hidePrivate(); $('status').textContent = 'You are signed out.'; }
    catch { $('status').textContent = 'Sign-out could not be confirmed. Please try again.'; }
  });
  $('change').addEventListener('click', async () => {
    if (!current || !csrf) return;
    const epoch=accessEpoch;
    $('change').disabled = true; $('status').textContent = 'Saving this change…';
    try {
      pending = journal.read('mode') || pending;
      remember(pending || { operation_id: crypto.randomUUID(), generation: current.restore_generation,
        revision: current.revision, enabled: !current.enabled, reason: 'Company appointment service configuration' });
      const value = await request('/api/company/control/change', pending);
      if(epoch!==accessEpoch)return;
      if ((value?.receipt?.operation_id || value?.operation_id) !== pending.operation_id
          || typeof (value.current || value).snapshot?.enabled !== 'boolean') throw new Error();
      remember(null); show(value);
    } catch (error) {
      if(epoch!==accessEpoch)return;
      if (error.code === 'company_command_storage_unavailable') { $('status').textContent = storageMessage; }
      else if (error.status === 409) {
        try { remember(null); await refresh(); $('status').textContent = 'Another change was saved first. Please review the current state before changing it.'; }
        catch { $('status').textContent = storageMessage; }
      }
      else { $('status').textContent = 'The response was interrupted. Check the saved change again; it will not create a second change.'; $('change').textContent = 'Check the saved change'; $('change').disabled = false; }
    }
  });
  $('load-incidents').addEventListener('click', async () => {
    const access = csrf;
    if (!access) return;
    $('load-incidents').disabled = true;
    $('incident-status').textContent = 'Checking recent service issues…';
    const areas = {control: 'Company controls', provider_event: 'Service notifications', recovery: 'Background work', verification: 'Contact confirmation', enquiry: 'Enquiries', staff: 'Appointment support', checkout: 'Payment', booking: 'Booking', availability: 'Available times', site: 'Website'};
    const issues = {service_unavailable: 'Service temporarily unavailable', storage_unavailable: 'Saved records unavailable', time_budget: 'Request took too long', unexpected_failure: 'Unexpected interruption', provider_rejected: 'Connected service rejected the request', result_invalid: 'Connected service returned an invalid result'};
    try {
      const value = await request('/api/company/operations/incidents');
      if (csrf !== access) return;
      if (value.version !== 1 || value.project !== document.body.dataset.project || !Array.isArray(value.incidents) || value.incidents.length > 100) throw new Error();
      const rows = value.incidents.slice(0, 20).map(item => {
        if (!Object.hasOwn(areas, item.operation) || !Object.hasOwn(issues, item.code) || !/^[a-f0-9-]{36}$/i.test(item.last_reference) || !Number.isSafeInteger(item.occurrences) || item.occurrences < 1 || !Number.isFinite(Date.parse(item.last_seen_at))) throw new Error();
        const row = document.createElement('article'); row.className = 'incident-row';
        const area = document.createElement('strong'); area.textContent = areas[item.operation];
        const issue = document.createElement('p'); issue.textContent = issues[item.code];
        const detail = document.createElement('p'); detail.className = 'caption';
        detail.textContent = `${new Date(item.last_seen_at).toLocaleString()} · ${item.occurrences} saved occurrence(s) · Reference: ${item.last_reference}`;
        row.append(area, issue, detail); return row;
      });
      $('incident-list').replaceChildren(...rows);
      $('incident-status').textContent = rows.length ? 'These are saved issue references, not a complete service history. The latest 20 groups are shown.' : 'No issue references are saved. This does not prove that every connected service is working.';
    } catch (error) {
      if (csrf !== access) return;
      $('incident-list').replaceChildren();
      $('incident-status').textContent = 'Issue references could not be loaded. Please try again.';
    } finally { $('load-incidents').disabled = false; }
  });
  function field(text, value, type = 'text', attributes = {}) {
    const label = document.createElement('label'); label.append(document.createTextNode(text));
    const input = document.createElement('input'); input.type = type;
    if (type === 'checkbox') input.checked = value; else input.value = value;
    for (const [name, setting] of Object.entries(attributes)) input.setAttribute(name, setting);
    label.append(input); return {label, input};
  }
  function rememberBusiness(value) {
    pendingBusiness = journal.save('business',value);
  }
  function windowRow(window) {
    const row = document.createElement('div'); row.className = 'window-row';
    const label = document.createElement('label'); label.append(document.createTextNode('Day'));
    const day = document.createElement('select');
    ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'].forEach((name, index) => {
      const option = document.createElement('option'); option.value = index; option.textContent = name; day.append(option);
    }); day.value = window.weekday; label.append(day);
    const start = field('From', window.start, 'text', {required:'',pattern:'(?:[01][0-9]|2[0-3]):[0-5][0-9]',maxlength:'5'});
    const end = field('Until', window.end, 'text', {required:'',pattern:'(?:(?:[01][0-9]|2[0-3]):[0-5][0-9]|24:00)',maxlength:'5'});
    start.input.dataset.part = 'start'; end.input.dataset.part = 'end'; day.dataset.part = 'weekday';
    const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'secondary'; remove.textContent = 'Remove';
    remove.addEventListener('click', () => row.remove()); row.append(label, start.label, end.label, remove); return row;
  }
  function showBusiness(value) {
    if (!/^[1-9][0-9]{0,18}$/.test(value.revision) || !Array.isArray(value.settings?.services) || !Array.isArray(value.settings?.weekly_windows)) throw new Error();
    business = value; const spec = value.settings;
    let storageReady = true;
    try { pendingBusiness = journal.read('business') || pendingBusiness; } catch { storageReady = false; }
    for (const [id, key] of [['timezone','timezone'],['step','slot_step_minutes'],['notice','notice_minutes'],['horizon','horizon_days'],['before','buffer_before_minutes'],['after','buffer_after_minutes'],['meeting','meeting']]) $('business-'+id).value = spec[key];
    $('business-otp').checked = spec.booking_verification.email;
    const services = spec.services.map(service => {
      const row = document.createElement('div'); row.className = 'service-row'; row.dataset.service = service.id;
      const name = field('Service', service.name, 'text', {required:'',maxlength:'150'});
      const enabled = field('Offer this service', service.enabled, 'checkbox');
      const duration = field('Minutes', service.duration_minutes, 'number', {required:'',min:'5',max:'480',step:'5'});
      const price = field(service.pricing.kind === 'per_question' ? 'Price per question (₹)' : 'Price (₹)', (service.pricing.amount_paise/100).toFixed(2), 'text', {required:'',inputmode:'decimal',pattern:'[0-9]{1,8}(?:\\.[0-9]{1,2})?'});
      name.input.dataset.part = 'name'; enabled.input.dataset.part = 'enabled'; duration.input.dataset.part = 'duration'; price.input.dataset.part = 'price';
      row.append(name.label,enabled.label,duration.label,price.label);
      if (service.pricing.kind === 'per_question') {
        const questions = field('Maximum questions',service.pricing.maximum_questions,'number',{required:'',min:'1',max:'10',step:'1'});
        questions.input.dataset.part = 'questions'; row.append(questions.label);
      } return row;
    });
    $('business-services').replaceChildren(...services);
    $('business-windows').replaceChildren(...spec.weekly_windows.map(windowRow));
    $('business-form').hidden = false;
    $('save-business').textContent = pendingBusiness ? 'Check the saved settings change' : 'Save settings';
    $('business-status').textContent = pendingBusiness ? 'A previous save needs checking. It will keep the same change reference.' : 'Current settings loaded.';
    $('save-business').disabled = !storageReady;
    if (!storageReady) $('business-status').textContent = storageMessage;
  }
  $('load-business').addEventListener('click', async () => {
    const epoch = accessEpoch; $('load-business').disabled = true;
    try { const value = await request('/api/company/settings'); if (epoch === accessEpoch) showBusiness(value); }
    catch { if (epoch === accessEpoch) $('business-status').textContent = 'Settings could not be loaded. Please sign in or try again.'; }
    finally { $('load-business').disabled = false; }
  });
  $('add-window').addEventListener('click', () => {
    if ($('business-windows').children.length < 28) $('business-windows').append(windowRow({weekday:0,start:'09:00',end:'17:00'}));
  });
  $('business-form').addEventListener('submit', async event => {
    event.preventDefault(); if (!business || !csrf) return;
    const epoch = accessEpoch; $('save-business').disabled = true;
    try {
      pendingBusiness = journal.read('business') || pendingBusiness;
      if (!pendingBusiness) {
        const spec = structuredClone(business.settings);
        for (const [id, key] of [['step','slot_step_minutes'],['notice','notice_minutes'],['horizon','horizon_days'],['before','buffer_before_minutes'],['after','buffer_after_minutes']]) spec[key] = Number($('business-'+id).value);
        spec.timezone = $('business-timezone').value; spec.meeting = $('business-meeting').value;
        spec.booking_verification.email = $('business-otp').checked;
        spec.required_contacts = (spec.booking_verification.email ? ['email'] : []).concat(spec.required_contacts.filter(item => item !== 'email'));
        for (const row of $('business-services').children) {
          const service = spec.services.find(item => item.id === row.dataset.service);
          const input = part => row.querySelector(`[data-part="${part}"]`);
          const money = input('price').value;
          if (!/^[0-9]{1,8}(?:\.[0-9]{1,2})?$/.test(money)) throw new Error();
          const [whole, cents = ''] = money.split('.'); service.pricing.amount_paise = Number(whole)*100+Number(cents.padEnd(2,'0'));
          service.name = input('name').value; service.enabled = input('enabled').checked; service.duration_minutes = Number(input('duration').value);
          if (input('questions')) service.pricing.maximum_questions = Number(input('questions').value);
        }
        spec.weekly_windows = [...$('business-windows').children].map(row => ({weekday:Number(row.querySelector('[data-part="weekday"]').value),start:row.querySelector('[data-part="start"]').value,end:row.querySelector('[data-part="end"]').value}));
        rememberBusiness({operation_id:crypto.randomUUID(),revision:business.revision,settings:spec,reason:$('business-reason').value});
      }
      else rememberBusiness(pendingBusiness);
      const result = await request('/api/company/settings', pendingBusiness);
      if (epoch !== accessEpoch) return;
      if (result?.saved !== true || result.revision !== String(BigInt(pendingBusiness.revision) + 1n)
          || typeof result.quote_version !== 'string' || !/^[a-f0-9]{64}$/.test(result.quote_version)) throw new Error();
      rememberBusiness(null);
      const saved = await request('/api/company/settings');
      if (epoch !== accessEpoch) return;
      showBusiness(saved); $('business-status').textContent = 'Settings saved. Existing accepted appointments are unchanged.';
    } catch (error) {
      if (epoch !== accessEpoch) return;
      let storageFailed = error.code === 'company_command_storage_unavailable';
      if (error.status === 409 || error.status === 422) { try { rememberBusiness(null); } catch { storageFailed = true; } }
      $('business-status').textContent = storageFailed ? storageMessage : error.status === 409 ? 'Another change was saved first. Load current settings before editing again.' : error.status === 422 ? 'Check the prices, durations and open periods. No change was saved.' : 'The save could not be confirmed. Check the same change again.';
      $('save-business').textContent = pendingBusiness ? 'Check the saved settings change' : 'Save settings';
    } finally { $('save-business').disabled = false; }
  });
  for (const action of ['reauth','password']) $(action+'-form').addEventListener('submit', async event => {
    event.preventDefault(); const epoch = accessEpoch; $(action+'-submit').disabled = true;
    const body = {password:$(action === 'reauth' ? 'reauth-password' : 'old-password').value};
    if (action === 'password') body.new_password = $('new-password').value;
    $('reauth-password').value = ''; $('old-password').value = ''; $('new-password').value = '';
    try {
      await request(action === 'reauth' ? '/api/company/reauthenticate' : '/api/company/password',body);
      if (epoch !== accessEpoch) return; accessEpoch++; await refresh();
      $('credential-status').textContent = action === 'reauth' ? 'Password confirmed. You can save protected changes.' : 'Password changed. Previous sessions have ended.';
    } catch {
      if (epoch === accessEpoch) $('credential-status').textContent = action === 'password' ? 'The password change could not be confirmed. Try signing in with the new password before trying the old password again.' : 'Confirmation failed. Check your password or sign in again.';
    } finally { delete body.password; delete body.new_password; $(action+'-submit').disabled = false; }
  });
  async function googleConnections() {
    const epoch = accessEpoch;
    try {
      const result = await request('/api/company/resources/status');
      if (epoch !== accessEpoch) return;
      const labels = {calendar:'Client Calendar',client_sheet:'Client records',agency_sheet:'NeuraFlow record copy'};
      $('google-status').textContent = result.resources.map(item => `${labels[item.resource]}: ${item.reconnect_required ? 'approval needed' : item.connected ? 'connected' : 'not connected'}`).join(' · ');
      $('google-pending').replaceChildren();
      for (const item of result.pending) {
        const button = document.createElement('button'); button.type = 'button';
        button.textContent = `Finish ${labels[item.resource]} connection`;
        button.addEventListener('click', async () => {
          button.disabled = true;
          try {
            const saved = await request('/api/company/resources/finish', {attempt_id:item.attempt_id});
            if (epoch !== accessEpoch) return;
            if (saved.code !== 'saved') throw new Error();
            await googleConnections();
          } catch { if (epoch === accessEpoch) $('google-status').textContent = 'The approval could not be installed. Check your sign-in and start a new approval if it has expired.'; button.disabled = false; }
        }); $('google-pending').append(button);
      }
    } catch { if (epoch === accessEpoch) $('google-status').textContent = 'Connections could not be checked. Confirm your password or check the saved setup.'; }
  }
  $('google-refresh').addEventListener('click',googleConnections);
  async function recordUpdates() {
    const epoch=accessEpoch;
    $('record-list').replaceChildren();$('record-status').textContent='Checking saved spreadsheet updates…';
    try {
      const result=await request('/api/company/records/status');
      if(epoch!==accessEpoch)return;
      $('record-status').textContent=result.total ? `${result.total} spreadsheet updates need checking.${result.limited?' The first 50 are shown. Check again after resolving them.':''}` : 'No spreadsheet update problems are currently recorded.';
      const explanations={google_row_conflict:'The row contains different information. Check it before retrying; the system will not overwrite unfamiliar content.',
        google_workbook_owner_mismatch:'The saved spreadsheet owner could not be confirmed.',
        google_workbook_layout_changed:'A saved spreadsheet tab or heading has changed.',
        google_sheet_readback_unresolved:'The saved result could not be confirmed. Another check will compare the same row.'};
      for(const item of result.records) {
        const panel=document.createElement('div'),description=document.createElement('p'),button=document.createElement('button');
        description.textContent=`${item.record_kind==='booking'?'Appointment':'Enquiry'} ${item.reference} · ${item.role==='client'?'Client copy':'NeuraFlow copy'}. ${explanations[item.last_error_code]||'The latest update could not yet be confirmed.'}`;
        button.type='button';button.className='secondary';button.disabled=item.busy===true;
        button.textContent=item.busy?'A check is running':'Check this record again';
        const command={operation_id:crypto.randomUUID(),record_id:item.record_id,role:item.role,record_kind:item.record_kind,sequence:item.sequence,reason:'Requested another protected spreadsheet check.'};
        button.addEventListener('click',async()=>{
          button.disabled=true;
          try {
            const saved=await request('/api/company/records/recheck',command);
            if(epoch!==accessEpoch)return;
            if(saved.code==='check_queued') {button.textContent='Check queued';$('record-status').textContent='The saved row will be checked during background processing. This does not overwrite unfamiliar content.';}
            else {await recordUpdates();}
          }catch {if(epoch===accessEpoch){button.disabled=false;button.textContent='Check this request again';$('record-status').textContent='The reply was interrupted. Retry the same request to check its saved result.';}}
        });
        panel.append(description,button);$('record-list').append(panel);
      }
    }catch {if(epoch===accessEpoch)$('record-status').textContent='Spreadsheet updates could not be checked. Please check your company sign-in.';}
  }
  $('record-refresh').addEventListener('click',recordUpdates);
  for (const button of document.querySelectorAll('[data-google-resource]')) button.addEventListener('click',async () => {
    const epoch = accessEpoch;
    button.disabled = true;
    try {
      const result = await request('/api/company/resources/start',{resource:button.dataset.googleResource});
      if (epoch !== accessEpoch) return;
      const target = new URL(result.authorization_url);
      if (target.origin !== 'https://accounts.google.com' || target.pathname !== '/o/oauth2/v2/auth') throw new Error();
      location.assign(target.href);
    } catch { if (epoch === accessEpoch) $('google-status').textContent = 'The connection could not start. Confirm your password, then try again.'; }
    finally { button.disabled = false; }
  });
  if (/^#google-consent=[0-9a-f-]{36}\.(pending|failed)$/.test(location.hash)) {
    history.replaceState(null,'',location.pathname);
    refresh().then(googleConnections);
  } else refresh();
})();
