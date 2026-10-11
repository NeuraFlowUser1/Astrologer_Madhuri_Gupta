# Find existing bookings with full name and saved phone

The current customer access rule is the complete saved full name AND saved mobile number. No reference, eight-digit code, email, OTP or private staff approval is requested. Several matching retained bookings are listed, including earlier, cancelled and expired bookings. Email remains optional when booking email verification is OFF; phone remains required.

## Shared contract

`POST /api/booking/details` accepts exactly `full_name`, canonical E.164 `phone`, optional opaque `cursor`, or optional selected `request_id`. Selection and cursor are mutually exclusive. The customer does not type a reference; the browser sends the selected returned identifier and repeats the identity pair. Every read re-applies the complete name/phone match in the current installation. Identity pairs stay in memory and POST bodies only.

The database owns NFC name normalization, the precise Unicode whitespace set, trim/collapse and locale-aware lowercase. Spelling, accents, punctuation and word order remain significant. Current mobile validation is reused; India is the initial prefix and a pasted complete +country number is preserved. The compound non-unique index matches phone/name/start/reference. Each list page contains at most 20 summaries with one extra row to decide pagination. Two bounded indexed ranges place future appointments first ascending, then prior appointments descending. The cursor keeps its original ordering instant and exact microsecond start; it expires after 24 hours. Changed records can require another search.

Registered web access and fresh booking ON/activation are required. Exact Origin and both committed source-address quotas (10 per minute, 60 per 15 minutes) are checked before JSON parsing, including malformed requests. No name or phone is stored in those quota counters. Errors omit private input. All responses are private/no-store, no-referrer and noindex. The database read exposes no contacts, birth data, notes, credentials or broad table permissions.

Name and phone are knowledge matches, not proof of control of the phone. Anyone who knows both can view matching appointment and ready meeting details. This is the owner's expressly chosen rule. Rate limits reduce guessing; they do not prove identity.

## Details and browser ownership

The independent browser controller never initializes checkout, changes receipt storage, rotates a secret or creates an email/payment/customer action. It clears data on pagehide/BFCache, OFF, activation change and disposal; input is retained only across the two visible access selections. Requests have abort and stale-generation guards. There is no lookup polling. A failed detail refresh marks the retained facts stale and disables meeting/PDF use.

Shared pure SQL/Python/JavaScript receipt facts keep the existing payment/refund and ready-current-meeting interpretation. The original saved-browser receipt adds its original authorization and permitted actions independently. The name/phone page offers refresh and confirmed-only local PDF. The PDF shares the two-fresh-read fact comparison, lazy libraries/font and five-second object URL lifecycle; lookup never sends an email copy. No stronger existing saved-browser customer permission is granted through lookup.

Both Contact and Booking link to `/booking/receipt` through existing booking visibility. `/booking-help` on both sites and AstroAdvice `/booking/access` replace browser history with the canonical page, dropping query/hash. Sarsa's footer no longer has a separate recovery item. Booking OFF keeps the ordinary enquiry route while hiding lookup and booking assets.

## One forward changeover

Migration 037 follows byte-identical migrations 001–036. The runner takes lock 4004001; this migration takes exclusive maintenance barrier (83124,5), then booking barrier (83124,4), with existing 2-second lock and 30-second statement bounds. New read/correction functions acquire shared barriers in that order. A lock/index/schema failure rolls back the entire migration and ledger entry. It runs separately per installation.

All old public issuers/redeemers and staff/company code generation/reconstruction are removed, including obsolete overloads and grants. `receipt_recoveries` keeps its name and audit rows, original issue/redemption/expiry/attempt facts, actor, reason, payment/verification provenance and before/after revisions/contacts. Usable code/replacement-receipt digests and code-key selectors are removed. New writes are direct authenticated contact corrections; they retain existing payment evidence, frozen email policy, revision/operation replay, receipt revocation, queues and records. Historical old-code action results say `operation_retired` and convey no code. Unknown never-committed private journal operations retain the existing bounded five-minute reconciliation rule.

Offline historical conversion verifies original code provenance in `tools/conversion/recovery.py` only, using declared historical material held in memory. Imported audit is inert; no runtime reader or active recovery credential is restored. Historical source layout pins, schema fixtures and original migration checksums remain unchanged. Superseded code-only test sources are retained in programme evidence; surviving correction/import/browser contracts are aligned but were not executed in this owner-requested no-tests run.

Prepare the complete candidate, preserve the latest requested ON/OFF state, use the existing company switch for a brief incompatible transition, apply 037 with the standard runner, update exact release bindings and publish the existing Git/Vercel/worker connections. Restore ON only if this release's OFF operation still wins; a newer owner command takes priority. No customer forms, real lookup identities, payments, emails or refunds are part of publication. After committed cleanup, repair forward with a compatible runtime; never automatically revive the removed code process.

## Current evidence boundary

Source review, packaging and local rendered inspection are separate from publication. No automated test, lint, coverage, CI gate or real customer acceptance is claimed for the 11 October programme. Per-installation publication results are recorded in the programme's execution record.
