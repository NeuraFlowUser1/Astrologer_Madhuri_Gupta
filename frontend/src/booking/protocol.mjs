/** Same-origin booking boundary. No sample data, external API fallback or local payment authority. */
export const SERVICE_IDS = ['kundli-prediction', 'kundli-matching', 'vastu-consultation', 'numerology'];
export const STORAGE_KEY = 'sarsa:004:booking-receipt:v1';
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const secret = /^[A-Za-z0-9_-]{43}$/;
const integer = value => Number.isSafeInteger(value) && value >= 0;
const text = (value, max = 200) => typeof value === 'string' && value.length > 0 && value.length <= max;
const instant = value => typeof value === 'string' && /(?:Z|[+-]\d\d:\d\d)$/.test(value) && Number.isFinite(Date.parse(value));
export class BookingError extends Error {
  constructor(code = 'temporarily_unavailable', retryAfter = 0) { super(code); this.code = code; this.retryAfter = retryAfter; }
}
function requireValue(valid) { if (!valid) throw new BookingError('invalid_response'); }
export function checkedPolicy(data) {
  const p = data?.policy;
  requireValue(p?.project === '004-sarsa-jyotish-sansthan' && p.timezone === 'Asia/Kolkata'
    && /^[a-f0-9]{64}$/.test(data.quote_version) && Array.isArray(p.services) && p.services.length === 4
    && integer(p.advance_days) && p.advance_days <= 31);
  requireValue(new Set(p.services.map(s => s.id)).size === 4);
  for (const s of p.services) requireValue(SERVICE_IDS.includes(s.id) && text(s.name, 100)
    && integer(s.amount_paise) && s.amount_paise > 0 && s.amount_paise <= 100000000
    && integer(s.duration_minutes) && s.duration_minutes > 0 && s.duration_minutes <= 480
    && s.currency === 'INR' && s.meeting_platform === 'Google Meet');
  return data;
}
export function checkedAvailability(data, service, day, version) {
  requireValue(data?.date === day && data?.service?.id === service && data.service.quote_version === version
    && data.service.timezone === 'Asia/Kolkata' && instant(data.server_now)
    && Array.isArray(data.slots) && data.slots.length <= 96);
  requireValue(new Set(data.slots.map(s => s.starts_at)).size === data.slots.length);
  for (const slot of data.slots) requireValue(instant(slot.starts_at) && instant(slot.ends_at)
    && Date.parse(slot.ends_at) > Date.parse(slot.starts_at) && Date.parse(slot.starts_at) > Date.parse(data.server_now));
  return data;
}
export function checkedReceipt(data, id) {
  requireValue(data?.request_id === id && ['held','expired','confirmed','cancelled','payment_review'].includes(data.appointment_state)
    && ['not_attempted','creating','creation_unknown','ready','failed'].includes(data.order_state)
    && ['unobserved','pending','captured','failed_observed','refunded','partially_refunded','needs_attention'].includes(data.payment_state)
    && text(data.service_name, 100) && data.currency === 'INR' && data.timezone === 'Asia/Kolkata'
    && integer(data.amount_paise) && data.amount_paise > 0 && integer(data.captured_paise) && integer(data.refunded_paise)
    && data.refunded_paise <= data.captured_paise && instant(data.starts_at) && instant(data.ends_at)
    && Date.parse(data.ends_at) > Date.parse(data.starts_at)
    && instant(data.server_now) && instant(data.hold_expires_at) && Array.isArray(data.next_actions)
    && data.next_actions.every(a => ['check_status','check_payment','resume_payment','contact_support','choose_new_time'].includes(a))
    && ['not_created','preparing','ready','needs_attention','cancelled'].includes(data.meeting_state));
  requireValue(data.meet_url === null || (data.appointment_state === 'confirmed' && data.meeting_state === 'ready'
    && /^https:\/\/meet\.google\.com\/[a-z]{3}-[a-z]{4}-[a-z]{3}$/.test(data.meet_url)));
  return data;
}
export function checkedCheckout(data, id) {
  checkedReceipt(data?.receipt, id);
  if (data.checkout !== null && data.checkout !== undefined) {
    const c = data.checkout;
    requireValue(/^rzp_live_[A-Za-z0-9]+$/.test(c.key_id) && /^order_[A-Za-z0-9]{1,64}$/.test(c.order_id)
      && c.amount_paise === data.receipt.amount_paise && c.currency === 'INR'
      && data.receipt.appointment_state === 'held' && data.receipt.next_actions.includes('resume_payment')
      && Date.parse(data.receipt.hold_expires_at) > Date.parse(data.receipt.server_now));
  }
  return data;
}
export function readReceipt(storage) {
  const raw = storage.getItem(STORAGE_KEY);
  if (raw === null) return null;
  let value;
  try { value = JSON.parse(raw); } catch { throw new BookingError('receipt_unavailable'); }
  requireValue(value?.version === 1 && uuid.test(value.request_id) && secret.test(value.secret)
    && Object.keys(value).length === 3);
  return value;
}
export function prepareReceipt(storage, cryptoSource = globalThis.crypto) {
  const bytes = cryptoSource.getRandomValues(new Uint8Array(32));
  const value = { version: 1, request_id: cryptoSource.randomUUID(),
    secret: btoa(String.fromCharCode(...bytes)).replaceAll('+','-').replaceAll('/','_').replaceAll('=','') };
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(value));
    const saved = readReceipt(storage);
    if (saved?.request_id !== value.request_id || saved?.secret !== value.secret) throw new Error();
  } catch { throw new BookingError('storage_unavailable'); }
  return value;
}
export function clearReceipt(storage, value) {
  const current = readReceipt(storage);
  if (current && current.request_id !== value.request_id) throw new BookingError('receipt_unavailable');
  storage.removeItem(STORAGE_KEY);
  if (storage.getItem(STORAGE_KEY) !== null) throw new BookingError('storage_unavailable');
}
export async function api(path, { body, credential, signal } = {}) {
  requireValue(/^\/api\/(booking-policy|availability\?[^#]*|checkout-context|checkout(?:\/(status|resume|verify-payment))?)$/.test(path));
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) abort();
  signal?.addEventListener('abort', abort, { once: true });
  const timer = setTimeout(abort, 60000);
  try {
    const response = await fetch(path, { method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin',
      cache: 'no-store', redirect: 'error', signal: controller.signal,
      headers: { Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type':'application/json' }),
        ...(credential ? { 'X-Booking-Receipt': credential.secret } : {}) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    const retry = Math.min(3600, Math.max(0, Number(response.headers.get('retry-after')) || 0));
    if (!response.headers.get('content-type')?.includes('application/json')) throw new BookingError('temporarily_unavailable');
    const reader = response.body.getReader(); let length = 0; const parts = [];
    while (true) { const { done, value } = await reader.read(); if (done) break;
      length += value.length; if (length > 65536) { await reader.cancel(); throw new BookingError('invalid_response'); } parts.push(value); }
    const bytes = new Uint8Array(length); let offset = 0; for (const part of parts) { bytes.set(part, offset); offset += part.length; }
    const data = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
    if (!response.ok) throw new BookingError(typeof data?.code === 'string' ? data.code : 'temporarily_unavailable', retry);
    return data;
  } catch (error) { if (error instanceof BookingError) throw error; throw new BookingError('temporarily_unavailable'); }
  finally { clearTimeout(timer); signal?.removeEventListener('abort', abort); }
}
export const money = paise => new Intl.NumberFormat('en-IN', { style:'currency', currency:'INR', maximumFractionDigits:paise % 100 ? 2 : 0 }).format(paise / 100);
export const indiaDate = (value = new Date()) => new Intl.DateTimeFormat('en-CA', { timeZone:'Asia/Kolkata', year:'numeric', month:'2-digit', day:'2-digit' }).format(value);
export const appointmentLabel = value => new Intl.DateTimeFormat('en-IN', { timeZone:'Asia/Kolkata', dateStyle:'medium', timeStyle:'short' }).format(new Date(value));
export const timeLabel = value => new Intl.DateTimeFormat('en-IN', { timeZone:'Asia/Kolkata', hour:'numeric', minute:'2-digit' }).format(new Date(value));
const messages = {
  booking_unavailable:'Online booking is not available at the moment. Please contact us for help.',
  intake_closed:'Online booking is not available at the moment. Please contact us for help.',
  please_wait:'Please wait before trying again. Your saved booking has not been reset.',
  rate_limited:'Please wait before trying again.',
  invalid_request:'Please check your details, including the mobile number and country code, and try again.',
  quote_changed:'The consultation details have changed. Please reload the consultation list and review your choice.',
  time_unavailable:'That time is no longer available. Please choose another time.',
  context_expired:'Please refresh this page. If you already started payment, keep your saved booking and check its status.',
  checkout_in_progress:'Another booking is already in progress in this browser. Return to its original tab or contact us.',
  request_conflict:'These details differ from the saved booking request. Please check its status or contact us.',
  access_unavailable:'We cannot open this saved booking here. Please use the original browser tab or contact us. Do not pay again to resolve this.',
  receipt_unavailable:'Your saved booking could not be read. Please contact us before trying another payment.',
  storage_unavailable:'This browser cannot safely save your booking receipt. Allow site storage before starting payment.',
  invalid_response:'We could not safely read the booking response. Please try checking again.',
  payment_not_configured:'We could not start payment. No appointment has been confirmed. Please try again later or contact the practice.',
  payment_unavailable:'The secure payment window could not load. Your booking has not been replaced. Please try again.',
};
export const messageFor = error => messages[error?.code] || 'We could not complete that check. Please try again shortly. If you started payment, check its status before paying again.';
export const rejectedWithoutBooking = code => ['payment_not_configured','invalid_request','intake_closed','quote_changed','service_unavailable','invalid_time','time_unavailable','request_rejected'].includes(code);
