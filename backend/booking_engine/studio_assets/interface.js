'use strict';
const statusLine = document.querySelector('#status');
const signInPanel = document.querySelector('#signin-panel');
const connectionPanel = document.querySelector('#connection-panel');
const retry = document.querySelector('#retry');
let busy = false;

function setBusy(value) {
  busy = value;
  document.querySelectorAll('button').forEach(button => { button.disabled = value; });
  if (typeof calendarSyncBusy === 'function') calendarSyncBusy();
  document.dispatchEvent(new Event('studio-busy'));
}

async function api(path, body, timeout = 15000) {
  const response = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(timeout),
  });
  if (response.status === 401 && path === '/api/studio/status') return { signed_in: false };
  if (!response.ok) throw new Error('Request unavailable');
  return response.json();
}

async function load() {
  if (busy) return;
  setBusy(true);
  retry.hidden = true;
  signInPanel.hidden = connectionPanel.hidden = true;
  document.querySelector('#calendar-panel').hidden = true;
  document.dispatchEvent(new Event('studio-calendar-hide'));
  document.dispatchEvent(new Event('studio-inbox-hide'));
  try {
    const result = await api('/api/studio/status');
    if (result.signed_in === true && ['client', 'agency'].includes(result.role)) {
      connectionPanel.hidden = false;
      document.querySelector('#account').textContent = result.email;
      document.querySelector('#purpose').textContent = result.role === 'client'
        ? 'This account owns the practice calendar and the client’s booking spreadsheet.'
        : 'This account owns NeuraFlow’s separate booking spreadsheet. Calendar access is not requested.';
      document.querySelector('#connection-status').textContent = result.reconnect_required
        ? 'The saved permission has expired. Please connect Google again.'
        : result.authorization_saved ? 'Google permission has been saved for this account.' : 'Google permission has not been saved yet.';
      document.querySelector('#connect').textContent = result.authorization_saved ? 'Reconnect Google' : 'Connect Google';
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
    history.replaceState(null, '', '/studio');
  } catch {
    statusLine.textContent = 'We cannot check your connection right now. Please try again shortly.';
    retry.hidden = false;
  } finally { setBusy(false); }
}

async function navigateToGoogle(path, body) {
  if (busy) return;
  setBusy(true);
  statusLine.textContent = 'Opening Google securely…';
  try {
    const result = await api(path, body);
    const url = new URL(result.authorization_url);
    if (url.origin !== 'https://accounts.google.com' || url.pathname !== '/o/oauth2/v2/auth') throw new Error('Invalid destination');
    location.assign(url.href);
  } catch {
    statusLine.textContent = 'We could not start the connection. Please check your sign-in and try again.';
    retry.hidden = false;
    setBusy(false);
  }
}

document.querySelectorAll('[data-role]').forEach(button => {
  button.addEventListener('click', () => navigateToGoogle('/api/studio/sign-in/start', { role: button.dataset.role }));
});
document.querySelector('#connect').addEventListener('click', () => navigateToGoogle('/api/studio/google/start', {}));
document.querySelector('#logout').addEventListener('click', async () => {
  if (busy) return;
  setBusy(true);
  try {
    await api('/api/studio/logout', {});
    document.dispatchEvent(new CustomEvent('studio-role', {detail:null}));
    setBusy(false);
    await load();
  } catch {
    statusLine.textContent = 'Sign-out could not be confirmed. Please try again.';
    setBusy(false);
  }
});
document.querySelector('#prepare-workbook').addEventListener('click', async () => {
  if (busy) return;
  setBusy(true);
  statusLine.textContent = 'Preparing your spreadsheet. This can take a moment…';
  try {
    await api('/api/studio/workbook/prepare', {}, 110000);
    setBusy(false);
    await load();
  } catch {
    statusLine.textContent = 'We could not confirm that setup finished. Check again shortly; we will look for the existing spreadsheet before making any changes.';
    retry.hidden = false;
    setBusy(false);
  }
});
retry.addEventListener('click', load);
// All deferred feature scripts must subscribe before role state is published.
if (document.readyState !== 'complete') document.addEventListener('DOMContentLoaded', load, { once: true });
else load();
