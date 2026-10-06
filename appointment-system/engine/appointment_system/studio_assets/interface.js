'use strict';
const statusLine = document.querySelector('#status');
const signInPanel = document.querySelector('#signin-panel');
const connectionPanel = document.querySelector('#connection-panel');
const retry = document.querySelector('#retry');
let busy = false;
let studioEnabled=false,studioEpoch=null,studioGeneration=0,studioReady=false;
const managementPath = '/studio';
const endpoint = path => path;
let pendingConsent = /^#google-consent=([0-9a-f-]{36})\.(pending|failed)$/.exec(location.hash);

function setBusy(value) {
  busy = value;
  document.querySelectorAll('button').forEach(button => { button.disabled = value; });
  if (typeof calendarSyncBusy === 'function') calendarSyncBusy();
  document.dispatchEvent(new Event('studio-busy'));
}

// Permission is a page-wide boundary. Check the HTTP status before parsing
// the body: an upstream service may return HTML or incomplete JSON on denial.
function studioCheckAccess(response) {
  if(response.status!==401 && response.status!==403)return;
  ++studioGeneration;
  connectionPanel.hidden=true;signInPanel.hidden=false;
  document.querySelector('#account').textContent='';
  document.querySelector('#open-workbook').removeAttribute('href');
  document.querySelector('#open-workbook').hidden=true;
  document.querySelector('#calendar-panel').hidden=true;
  document.dispatchEvent(new Event('studio-calendar-hide'));
  document.dispatchEvent(new Event('studio-inbox-hide'));
  document.dispatchEvent(new CustomEvent('studio-role',{detail:null}));
  setBusy(false);
  statusLine.textContent='Your access could not be confirmed. Sign in again.';
  retry.hidden=false;
  const error=Error('Access unavailable');error.status=response.status;throw error;
}

async function api(path, body, timeout = 15000) {
  if(!studioEnabled)throw new Error('Page unavailable');
  const response = await fetch(endpoint(path), {
    method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(timeout),
  });
  if (response.status === 401 && path === '/api/studio/status') return { signed_in: false };
  studioCheckAccess(response);
  if (!response.ok) throw new Error('Request unavailable');
  return response.json();
}

async function load() {
  if (busy || !studioEnabled) return;
  const ticket=studioGeneration;
  setBusy(true);
  retry.hidden = true;
  signInPanel.hidden = connectionPanel.hidden = true;
  document.querySelector('#calendar-panel').hidden = true;
  document.dispatchEvent(new Event('studio-calendar-hide'));
  document.dispatchEvent(new Event('studio-inbox-hide'));
  try {
    const result = await api('/api/studio/status');
    if(ticket!==studioGeneration || !studioEnabled)return;
    if (result.signed_in === true && result.role === 'client') {
      if (pendingConsent && pendingConsent[2] === 'pending') {
        const finish = await api('/api/studio/resources/finish', {attempt_id:pendingConsent[1]});
        if(ticket!==studioGeneration || !studioEnabled)return;
        history.replaceState(null, '', managementPath);
        if (finish.code !== 'saved') throw new Error('Permission was not saved');
        pendingConsent = null;
        setBusy(false); return load();
      }
      connectionPanel.hidden = false;
      document.querySelector('#account').textContent = result.email;
      document.querySelector('#purpose').textContent = 'Use your Google account for your appointments and your records.';
      document.querySelector('#connection-status').textContent = result.reconnect_required
        ? 'The saved permission has expired. Please connect Google again.'
        : result.authorization_saved ? 'Google permission has been saved for this account.' : 'Google permission has not been saved yet.';
      const calendar = (result.resources || []).find(item => item.resource === 'calendar');
      document.querySelector('#connect').textContent = calendar?.connected ? 'Reconnect Calendar' : 'Connect Calendar';
      document.querySelector('#connect-records').textContent = result.authorization_saved ? 'Reconnect my records' : 'Connect my records';
      const link = document.querySelector('#open-workbook');
      link.hidden = true;
      document.querySelector('#prepare-workbook').hidden = !result.authorization_saved || result.reconnect_required || Boolean(result.workbook_url);
      document.querySelector('#workbook-status').textContent = result.workbook_url
        ? 'Your spreadsheet has been prepared.' : result.authorization_saved && !result.reconnect_required
          ? 'Create your separate booking record copy in this Google account.' : 'Connect Google before preparing your spreadsheet.';
      if (result.workbook_url) {
        const url = new URL(result.workbook_url);
        if (url.origin !== 'https://docs.google.com' || !/^\/spreadsheets\/d\/[A-Za-z0-9_-]{1,200}$/.test(url.pathname) || url.search || url.hash) throw new Error('Unexpected spreadsheet');
        link.href = url.href;
        link.hidden = false;
      }
      statusLine.textContent = 'You are signed in.';
      document.querySelector('#calendar-panel').hidden = result.role !== 'client';
      document.dispatchEvent(new CustomEvent('studio-role', {detail:result.role}));
    } else if (result.signed_in === false) {
      document.dispatchEvent(new CustomEvent('studio-role', {detail:null}));
      signInPanel.hidden = false;
      statusLine.textContent = 'Start by signing in to your account.';
    } else throw new Error('Unexpected status');
    if (new URLSearchParams(location.search).get('connection') === 'failed') {
      statusLine.textContent = 'That connection was not completed. Your previously saved connection has not been replaced. Please try again.';
    }
    if (new URLSearchParams(location.search).get('connection') === 'check') {
      statusLine.textContent = 'The connection was interrupted. Please check the saved status shown here before trying again.';
    }
    history.replaceState(null, '', managementPath);
  } catch {
    if(ticket!==studioGeneration || !studioEnabled)return;
    statusLine.textContent = 'We cannot check your connection right now. Please try again shortly.';
    retry.hidden = false;
  } finally { if(ticket===studioGeneration)setBusy(false); }
}

async function navigateToGoogle(path, body) {
  if (busy || !studioEnabled) return;
  const ticket=studioGeneration;
  setBusy(true);
  statusLine.textContent = 'Opening Google securely…';
  try {
    const result = await api(path, body);
    if(ticket!==studioGeneration || !studioEnabled)return;
    const url = new URL(result.authorization_url);
    if (url.origin !== 'https://accounts.google.com' || url.pathname !== '/o/oauth2/v2/auth') throw new Error('Invalid destination');
    location.assign(url.href);
  } catch {
    if(ticket!==studioGeneration || !studioEnabled)return;
    statusLine.textContent = 'We could not start the connection. Please check your sign-in and try again.';
    retry.hidden = false;
    setBusy(false);
  }
}

document.querySelectorAll('[data-role]').forEach(button => {
  button.addEventListener('click', () => navigateToGoogle('/api/studio/sign-in/start', { role: button.dataset.role }));
});
document.querySelector('#connect').addEventListener('click', () => navigateToGoogle('/api/studio/resources/start', {resource:'calendar'}));
document.querySelector('#connect-records').addEventListener('click', () => navigateToGoogle('/api/studio/resources/start', {resource:'client_sheet'}));
document.querySelector('#logout').addEventListener('click', async () => {
  if (busy) return;
  const ticket=studioGeneration;
  setBusy(true);
  try {
    await api('/api/studio/logout', {});
    if(ticket!==studioGeneration || !studioEnabled)return;
    document.dispatchEvent(new CustomEvent('studio-role', {detail:null}));
    setBusy(false);
    await load();
  } catch {
    if(ticket!==studioGeneration || !studioEnabled)return;
    statusLine.textContent = 'Sign-out could not be confirmed. Please try again.';
    setBusy(false);
  }
});
document.querySelector('#prepare-workbook').addEventListener('click', async () => {
  if (busy) return;
  const ticket=studioGeneration;
  setBusy(true);
  statusLine.textContent = 'Preparing your spreadsheet. This can take a moment…';
  try {
    await api('/api/studio/workbook/prepare', {}, 110000);
    if(ticket!==studioGeneration || !studioEnabled)return;
    setBusy(false);
    await load();
  } catch {
    if(ticket!==studioGeneration || !studioEnabled)return;
    statusLine.textContent = 'We could not confirm that setup finished. Check again shortly; we will look for the existing spreadsheet before making any changes.';
    retry.hidden = false;
    setBusy(false);
  }
});
retry.addEventListener('click', load);
document.addEventListener('studio-availability',event=>{
  const {enabled,epoch}=event.detail;
  if(enabled===studioEnabled && epoch===studioEpoch)return;
  studioEnabled=enabled;studioEpoch=epoch;++studioGeneration;if(!studioReady)return;setBusy(false);
  if(!enabled){
    signInPanel.hidden=connectionPanel.hidden=true;
    document.querySelector('#calendar-panel').hidden=true;
    document.dispatchEvent(new Event('studio-calendar-hide'));
    document.dispatchEvent(new Event('studio-inbox-hide'));
    document.dispatchEvent(new CustomEvent('studio-role',{detail:null}));
  }else void load();
});
// All deferred feature scripts must subscribe before role state is published.
function initialize(){studioReady=true;const state=window.bookingVisibility?.getSnapshot();if(state?.enabled===true){studioEnabled=true;studioEpoch=state.activation_epoch;void load();}}
if (document.readyState !== 'complete') document.addEventListener('DOMContentLoaded', initialize, { once: true });
else initialize();
